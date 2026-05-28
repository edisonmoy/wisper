import os
import subprocess
import threading
import time

import AppKit
import objc
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

MIN_AUDIO_MS = 300  # ignore taps shorter than this


def _make_menubar_image():
    """Draw a 5-bar waveform as a black-on-transparent template NSImage.

    macOS template images are automatically rendered white on dark menu bars
    and black on light ones, matching all other system status icons.
    """
    from Foundation import NSMakeRect
    size = 22.0  # standard menu-bar icon point size
    img = AppKit.NSImage.alloc().initWithSize_((size, size))
    img.lockFocus()
    bar_w, gap = 3.0, 1.0
    heights = [7.0, 13.0, 19.0, 13.0, 7.0]
    total_w = len(heights) * (bar_w + gap) - gap
    x0 = (size - total_w) / 2
    AppKit.NSColor.blackColor().setFill()
    for i, h in enumerate(heights):
        x = x0 + i * (bar_w + gap)
        y = (size - h) / 2
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(x, y, bar_w, h), 1.0, 1.0
        )
        path.fill()
    img.unlockFocus()
    img.setTemplate_(True)
    return img


class _MenuDelegate(AppKit.NSObject):
    """NSMenu delegate that can hold the menu open during a short async operation."""

    def init(self):
        self = objc.super(_MenuDelegate, self).init()
        self._block = False
        return self

    def menuShouldClose_(self, _menu):
        return not self._block


class WisperApp(rumps.App):
    def __init__(self):
        super().__init__('Wisper', quit_button=None)
        self.config = Config.load()

        self.recorder = AudioRecorder()
        self.transcriber = Transcriber(self.config.model)
        self.db = HistoryDB(APP_DIR / 'history.db')
        self.overlay = create_recording_overlay(self.recorder.get_waveform)

        # Flag set by background threads; consumed by main-thread timer.
        self._needs_history_refresh = False

        # Update state: None | 'checking' | int (0=up-to-date, N=available) | 'installing' | 'error'
        self._update_state = None

        # _nsapp (rumps internals) is only created inside run(); defer NSStatusItem
        # customisation to the first _ui_tick so the run loop has already started.
        self._nsapp_configured = False

        self._menu_delegate = _MenuDelegate.alloc().init()
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

    def _configure_nsapp(self):
        """One-time deferred setup that requires the NSApp run loop to be running."""
        nssi = self._nsapp.nsstatusitem
        btn = nssi.button()
        if btn is not None:
            btn.setImage_(_make_menubar_image())
            btn.setTitle_('')
        nsm = nssi.menu()
        if nsm:
            nsm.setDelegate_(self._menu_delegate)

    def _ui_tick(self, _):
        if not self._nsapp_configured:
            self._configure_nsapp()
            self._nsapp_configured = True
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
        self.status_item.title = 'Recording… release fn to stop'
        self.overlay.performSelectorOnMainThread_withObject_waitUntilDone_('show:', None, False)

    def _on_fn_up(self):
        audio_ms = self.recorder.duration_ms()
        audio = self.recorder.stop()
        self.overlay.performSelectorOnMainThread_withObject_waitUntilDone_('hide:', None, False)

        self.status_item.title = 'Hold fn to record'

        if audio is None or audio_ms < MIN_AUDIO_MS:
            return

        self.status_item.title = 'Transcribing…'

        try:
            t0 = time.monotonic()
            text = self.transcriber.transcribe(audio)
            latency_ms = int((time.monotonic() - t0) * 1000)
        except Exception as exc:
            rumps.notification('Wisper', 'Transcription failed', str(exc), sound=False)
            self.status_item.title = 'Hold fn to record'
            return

        self.status_item.title = 'Hold fn to record'

        if not text:
            return

        self._paste(text)
        self.db.add(text, audio_ms=audio_ms, model=self.config.model, latency_ms=latency_ms)
        self._needs_history_refresh = True

    # -------------------------------------------------------------- output

    def _paste(self, text: str):
        saved = subprocess.run(['pbpaste'], capture_output=True).stdout
        subprocess.run(['pbcopy'], input=text.encode(), check=True)
        subprocess.run([
            'osascript', '-e',
            'tell application "System Events" to keystroke "v" using command down',
        ])
        # Restore clipboard after a short delay so the paste keystroke has
        # time to be consumed by the target app before we overwrite the clipboard.
        threading.Timer(0.5, lambda: subprocess.run(['pbcopy'], input=saved, check=True)).start()

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
            self._menu_delegate._block = True
            # Safety release so a hung network can't trap the menu forever.
            threading.Timer(15.0, self._unblock_menu).start()
            threading.Thread(target=self._run_update_check, daemon=True).start()
        elif isinstance(s, int) and s > 0:
            self._update_state = 'installing'
            threading.Thread(target=self._run_install, daemon=True).start()

    def _unblock_menu(self):
        self._menu_delegate._block = False

    def _run_update_check(self):
        n = check_for_updates(REPO_DIR)
        self._update_state = n if n >= 0 else 'error'
        self._unblock_menu()
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
