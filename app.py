import os
import subprocess
import threading
import time

import AppKit
import rumps
import setproctitle

setproctitle.setproctitle('Wisper')

# Hide from Dock. Must be set before rumps touches NSApplication.
# The Info.plist LSUIElement key is ignored because NSBundle.mainBundle()
# resolves to the Python framework, not Wisper.app, with a shell launcher.
AppKit.NSApplication.sharedApplication().setActivationPolicy_(
    AppKit.NSApplicationActivationPolicyProhibited
)

from config import APP_DIR, MODELS, REPO_DIR, Config
from history import HistoryDB
from hotkey import HotkeyManager
from overlay import create_recording_overlay
from recorder import AudioRecorder
from transcriber import Transcriber
from updater import check_for_updates, install_update
from utils import format_age

ICON_IDLE = '🎤'
ICON_RECORDING = '🔴'
ICON_THINKING = '⏳'

MIN_AUDIO_MS = 300  # ignore taps shorter than this


class WisperApp(rumps.App):
    def __init__(self):
        super().__init__(ICON_IDLE, quit_button=None)
        self.config = Config.load()

        self.recorder = AudioRecorder()
        self.transcriber = Transcriber(self.config.model)
        self.db = HistoryDB(APP_DIR / 'history.db')
        self.overlay = create_recording_overlay(self.recorder.get_waveform)

        # Flag set by background threads; consumed by main-thread timer.
        self._needs_history_refresh = False

        # Update state: None | 'checking' | int (0=up-to-date, N=available) | 'installing' | 'error'
        self._update_state = None

        self._build_menu()
        self._setup_hotkey()

        # Pump UI updates on the main thread so we never touch NSMenu from a
        # background thread (AppKit requirement).
        self._timer = rumps.Timer(self._ui_tick, 0.3)
        self._timer.start()

        self.transcriber.preload()

        # Background update check 5s after launch (non-blocking).
        threading.Timer(5.0, self._run_update_check).start()

    # ------------------------------------------------------------------ menu

    def _build_menu(self):
        self.status_item = rumps.MenuItem('Hold fn to record')

        self.history_menu = rumps.MenuItem('History')
        self._refresh_history()

        self.model_items: dict[str, rumps.MenuItem] = {}
        model_menu = rumps.MenuItem('Model')
        for m in MODELS:
            item = rumps.MenuItem(m, callback=lambda _, model=m: self._set_model(model))
            model_menu[m] = item
            self.model_items[m] = item
        self._sync_model_checkmarks()

        self.update_item = rumps.MenuItem('Check for Updates', callback=self._update_action)

        self.menu = [
            self.status_item,
            None,
            self.history_menu,
            model_menu,
            None,
            self.update_item,
            rumps.MenuItem('Quit Wisper', callback=self._quit),
        ]

    def _sync_model_checkmarks(self):
        for m, item in self.model_items.items():
            item.title = ('✓ ' if m == self.config.model else '   ') + m

    def _ui_tick(self, _):
        # Quit must happen on the main thread; background install sets this state.
        if self._update_state == 'restarting':
            rumps.quit_application()
            return
        if self._needs_history_refresh:
            self._needs_history_refresh = False
            self._refresh_history()
        self._sync_update_item()

    def _sync_update_item(self):
        s = self._update_state
        if s is None:
            title, enabled = 'Check for Updates', True
        elif s == 'checking':
            title, enabled = 'Checking for updates…', False
        elif s == 0:
            title, enabled = 'Up to date ✓', True
        elif isinstance(s, int):
            title, enabled = 'Update Available — Install', True
        elif s == 'installing':
            title, enabled = 'Installing update…', False
        elif s == 'restarting':
            title, enabled = 'Restarting…', False
        else:  # 'error'
            title, enabled = 'Update check failed — retry', True
        self.update_item.title = title
        self.update_item._menuitem.setEnabled_(enabled)

    def _refresh_history(self):
        """Must be called on the main thread (AppKit constraint)."""
        for key in list(self.history_menu.keys()):
            del self.history_menu[key]

        items = self.db.get_recent(self.config.history_limit)
        if not items:
            self.history_menu['_empty'] = rumps.MenuItem('(empty)')
            return

        for item in items:
            snippet = item['text'][:38] + ('…' if len(item['text']) > 38 else '')
            model = item['model'] or '?'
            secs = item['latency_ms'] / 1000
            age = format_age(item['created_at'])
            label = f"{snippet}    {age}  ·  {model}  {secs:.1f}s"
            text = item['text']
            mi = rumps.MenuItem(label, callback=lambda _, t=text: self._recopy(t))
            self.history_menu[str(item['id'])] = mi

        # Separator via a disabled, untitled item — avoids None dict-key ambiguity.
        self.history_menu['_clear'] = rumps.MenuItem(
            '— Clear History', callback=self._clear_history
        )

    # --------------------------------------------------------------- hotkey

    def _setup_hotkey(self):
        self.hotkey = HotkeyManager(
            on_start=self._on_fn_down,
            on_stop=self._on_fn_up,
        )
        self.hotkey.start()

    # ------------------------------------------------------------ recording

    def _on_fn_down(self):
        self.recorder.start()
        self.title = ICON_RECORDING
        self.status_item.title = 'Recording… release fn to stop'
        self.overlay.performSelectorOnMainThread_withObject_waitUntilDone_('show:', None, False)

    def _on_fn_up(self):
        audio_ms = self.recorder.duration_ms()
        audio = self.recorder.stop()
        self.overlay.performSelectorOnMainThread_withObject_waitUntilDone_('hide:', None, False)

        self.title = ICON_IDLE
        self.status_item.title = 'Hold fn to record'

        if audio is None or audio_ms < MIN_AUDIO_MS:
            return

        self.title = ICON_THINKING
        self.status_item.title = 'Transcribing…'

        try:
            t0 = time.monotonic()
            text = self.transcriber.transcribe(audio)
            latency_ms = int((time.monotonic() - t0) * 1000)
        except Exception as exc:
            rumps.notification('Wisper', 'Transcription failed', str(exc), sound=False)
            self.title = ICON_IDLE
            self.status_item.title = 'Hold fn to record'
            return

        self.title = ICON_IDLE
        self.status_item.title = 'Hold fn to record'

        if not text:
            return

        self._paste(text)
        self.db.add(text, audio_ms=audio_ms, model=self.config.model, latency_ms=latency_ms)
        self._needs_history_refresh = True

    # -------------------------------------------------------------- output

    def _paste(self, text: str):
        subprocess.run(['pbcopy'], input=text.encode(), check=True)
        if self.config.auto_paste:
            subprocess.run([
                'osascript', '-e',
                'tell application "System Events" to keystroke "v" using command down',
            ])

    def _recopy(self, text: str):
        subprocess.run(['pbcopy'], input=text.encode(), check=True)

    # --------------------------------------------------------- menu actions

    def _set_model(self, model: str):
        self.config.model = model
        self.config.save()
        self.transcriber.set_model(model)
        self._sync_model_checkmarks()

    def _clear_history(self, _):
        self.db.clear()
        self._needs_history_refresh = True

    # ------------------------------------------------------------ updates

    def _update_action(self, _):
        s = self._update_state
        if s in (None, 0, 'error'):
            self._update_state = 'checking'
            threading.Thread(target=self._run_update_check, daemon=True).start()
        elif isinstance(s, int) and s > 0:
            self._update_state = 'installing'
            threading.Thread(target=self._run_install, daemon=True).start()

    def _run_update_check(self):
        n = check_for_updates(REPO_DIR)
        self._update_state = n if n >= 0 else 'error'
        if n == 0:
            threading.Timer(4.0, self._reset_update_state).start()

    def _reset_update_state(self):
        if self._update_state == 0:
            self._update_state = None

    def _run_install(self):
        ok = install_update(REPO_DIR)
        if not ok:
            self._update_state = 'error'
            return

        self.hotkey.stop()

        # Try launchctl kickstart first — this handles the normal launchd-managed
        # case and starts the new process before this one exits.
        r = subprocess.run(
            ['launchctl', 'kickstart', '-k', f'gui/{os.getuid()}/com.wisper.app'],
            capture_output=True,
        )
        if r.returncode != 0:
            # Not managed by launchd (e.g. started from terminal) — spawn directly.
            launcher = REPO_DIR / 'Wisper.app' / 'Contents' / 'MacOS' / 'Wisper'
            if launcher.exists():
                subprocess.Popen(
                    [str(launcher)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,  # detach so it survives this process exiting
                )

        # Signal _ui_tick to call rumps.quit_application() on the main thread.
        # Calling it directly here (background thread) causes an unclean exit
        # that makes launchd throttle the restart.
        self._update_state = 'restarting'

    # --------------------------------------------------------------- quit

    def _quit(self, _):
        self.hotkey.stop()
        rumps.quit_application()


if __name__ == '__main__':
    WisperApp().run()
