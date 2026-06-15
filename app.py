import logging
import logging.handlers
import os
import subprocess
import threading
import time

import AppKit
import rumps
import setproctitle

setproctitle.setproctitle("Wisper")

# Hide from Dock. Must be set before rumps touches NSApplication.
# The Info.plist LSUIElement key is ignored because NSBundle.mainBundle()
# resolves to the Python framework, not Wisper.app, with a shell launcher.
AppKit.NSApplication.sharedApplication().setActivationPolicy_(
    AppKit.NSApplicationActivationPolicyProhibited
)

from config import APP_DIR, CLEANUP_MODES, MODELS, REPO_DIR, Config
from history import HistoryDB
from hotkey import HotkeyManager, key_display_name
from overlay import create_recording_overlay
from postprocessor import PostProcessor
from recorder import AudioRecorder
from transcriber import Transcriber
from updater import check_for_updates, install_update
from utils import format_age

logger = logging.getLogger("wisper")

MIN_AUDIO_MS = 300  # ignore taps shorter than this
VERSION = "1.0.0"


# Preset hotkey options shown in the Hotkey submenu.
# Each entry: (display_name, hotkey_vk, hotkey_key)
def _get_input_devices() -> list[str]:
    """Return names of available input devices; returns [] if sounddevice is unavailable."""
    try:
        import sounddevice as sd

        return [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
    except Exception:
        return []


_HOTKEY_PRESETS = [
    ("fn  (built-in Globe key)", 63, ""),
    ("Right ⌥  Option", 0, "alt_r"),
    ("Left ⌥  Option", 0, "alt_l"),
    ("Right ⌃  Control", 0, "ctrl_r"),
    ("Left ⌃  Control", 0, "ctrl_l"),
    ("Caps Lock", 0, "caps_lock"),
    ("F13", 0, "f13"),
    ("F14", 0, "f14"),
    ("F15", 0, "f15"),
    ("F16", 0, "f16"),
]


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


class WisperApp(rumps.App):
    def __init__(self):
        super().__init__("Wisper", quit_button=None)
        self.config = Config.load()

        # Configure rotating log file.
        APP_DIR.mkdir(exist_ok=True)
        _handler = logging.handlers.RotatingFileHandler(
            APP_DIR / "wisper.log", maxBytes=1_000_000, backupCount=3
        )
        _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(_handler)
        logger.setLevel(logging.INFO)

        self.recorder = AudioRecorder()
        self.recorder.device = self.config.mic_name or None
        self.transcriber = Transcriber(self.config.model)
        self.postprocessor = PostProcessor(self.config)
        self.db = HistoryDB(APP_DIR / "history.db")
        self.overlay = create_recording_overlay(self.recorder.get_waveform)

        # Flags set by background threads; consumed by main-thread _ui_tick.
        self._needs_history_refresh = False
        self._pending_restore: list | None = None  # clipboard snapshot to restore
        self._pasting = False  # blocks _ui_tick restore during pbcopy→cmd+v window

        # Watchdog state
        self._recording_started_at: float | None = None
        self._mismatch_ticks = 0

        # Update state: None | 'checking' | int (0=up-to-date, N=available) | 'installing' | 'error'
        # Protected by _update_lock for safe cross-thread access.
        self._update_lock = threading.Lock()
        self.__update_state = None

        # _nsapp (rumps internals) is only created inside run(); defer NSStatusItem
        # customisation to the first _ui_tick so the run loop has already started.
        self._nsapp_configured = False

        self._build_menu()
        self._setup_hotkey()
        self._check_permissions()

        # Pump UI updates on the main thread so we never touch NSMenu from a
        # background thread (AppKit requirement).
        self._timer = rumps.Timer(self._ui_tick, 0.3)
        self._timer.start()

        self.transcriber.preload()

        # Background update check 5s after launch (non-blocking).
        threading.Timer(5.0, self._run_update_check).start()

    @property
    def _update_state(self):
        with self._update_lock:
            return self.__update_state

    @_update_state.setter
    def _update_state(self, value):
        with self._update_lock:
            self.__update_state = value

    # ------------------------------------------------------------------ menu

    def _hotkey_label(self) -> str:
        return key_display_name(self.config.hotkey_vk, self.config.hotkey_key)

    def _idle_title(self) -> str:
        return f"Tap {self._hotkey_label()} to record"

    def _build_menu(self):
        self.status_item = rumps.MenuItem(self._idle_title())

        self.history_menu = rumps.MenuItem("History")
        self._refresh_history()

        self.model_items: dict[str, rumps.MenuItem] = {}
        model_menu = rumps.MenuItem("Model")
        for m in MODELS:
            item = rumps.MenuItem(m, callback=lambda _, model=m: self._set_model(model))
            model_menu[m] = item
            self.model_items[m] = item
        self._sync_model_checkmarks()

        self.cleanup_items: dict[str, rumps.MenuItem] = {}
        cleanup_menu = rumps.MenuItem("Text Cleanup")
        labels = {
            "none": "None",
            "regex": "Basic (remove um/uh)",
            "ai": "AI — Polish & rewrite (Apple Silicon)",
        }
        for mode in CLEANUP_MODES:
            item = rumps.MenuItem(labels[mode], callback=lambda _, m=mode: self._set_cleanup(m))
            cleanup_menu[mode] = item
            self.cleanup_items[mode] = item
        self._sync_cleanup_checkmarks()

        hotkey_menu = rumps.MenuItem(f"Hotkey: {self._hotkey_label()}")
        self.hotkey_preset_items: dict[tuple, tuple] = {}
        for name, vk, key_name in _HOTKEY_PRESETS:
            item = rumps.MenuItem(name, callback=lambda _, v=vk, k=key_name: self._set_hotkey(v, k))
            hotkey_menu[name] = item
            self.hotkey_preset_items[(vk, key_name)] = (item, name)
        self.hotkey_menu = hotkey_menu
        self._sync_hotkey_checkmarks()

        self.mic_items: dict[str, rumps.MenuItem] = {}
        self.mic_menu = rumps.MenuItem(self._mic_label())
        self._build_mic_submenu()

        self.update_item = rumps.MenuItem("Check for Updates", callback=self._update_action)

        self.menu = [
            self.status_item,
            None,
            self.history_menu,
            model_menu,
            cleanup_menu,
            self.hotkey_menu,
            self.mic_menu,
            None,
            self.update_item,
            rumps.MenuItem("Quit Wisper", callback=self._quit),
        ]

    def _sync_model_checkmarks(self):
        for m, item in self.model_items.items():
            item.title = ("✓ " if m == self.config.model else "   ") + m

    def _sync_cleanup_checkmarks(self):
        labels = {
            "none": "None",
            "regex": "Basic (remove um/uh)",
            "ai": "AI — Polish & rewrite (Apple Silicon)",
        }
        for mode, item in self.cleanup_items.items():
            item.title = ("✓ " if mode == self.config.cleanup_mode else "   ") + labels[mode]

    def _set_cleanup(self, mode: str):
        self.config.cleanup_mode = mode
        self.config.save()
        self.postprocessor.set_mode(mode)
        self._sync_cleanup_checkmarks()

    def _configure_nsapp(self):
        """One-time deferred setup that requires the NSApp run loop to be running."""
        nssi = self._nsapp.nsstatusitem
        btn = nssi.button()
        if btn is not None:
            btn.setImage_(_make_menubar_image())
            btn.setTitle_("")

    def _ui_tick(self, _):
        if not self._nsapp_configured:
            self._configure_nsapp()
            self._nsapp_configured = True
        # Quit must happen on the main thread; background install sets this state.
        if self._update_state == "restarting":
            rumps.quit_application()
            return
        if self._needs_history_refresh:
            self._needs_history_refresh = False
            self._refresh_history()
        self._sync_update_item()
        # Clipboard restore must happen on the main thread (NSPasteboard requirement).
        # Skip if _pasting is True — the background thread is between pbcopy and cmd+v.
        if self._pending_restore is not None and not self._pasting:
            self._restore_clipboard(self._pending_restore)
            self._pending_restore = None
        self._watchdog()

    def _restore_clipboard(self, saved_items: list):
        try:
            pb = AppKit.NSPasteboard.generalPasteboard()
            pb.clearContents()
            ns_items = []
            for saved_data in saved_items:
                item = AppKit.NSPasteboardItem.new()
                for ptype, raw in saved_data.items():
                    ns_data = AppKit.NSData.dataWithBytes_length_(raw, len(raw))
                    item.setData_forType_(ns_data, ptype)
                ns_items.append(item)
            if ns_items:
                pb.writeObjects_(ns_items)
        except Exception as exc:
            logger.error("Clipboard restore failed: %s", exc)
            rumps.notification("Wisper", "Clipboard restore failed", str(exc), sound=False)

    # ------------------------------------------------------------- watchdog

    _MAX_RECORDING_S = 300  # 5 minutes — auto-stop if stuck this long
    _MISMATCH_GRACE = 3  # ticks (~0.9 s) before treating divergence as stuck

    def _watchdog(self):
        recorder_on = self.recorder.is_recording
        hotkey_on = self.hotkey._recording

        # Detect divergence between the two state machines.
        if recorder_on != hotkey_on:
            self._mismatch_ticks += 1
            if self._mismatch_ticks >= self._MISMATCH_GRACE:
                self._emergency_reset("state mismatch")
            return
        self._mismatch_ticks = 0

        # Enforce maximum recording duration.
        if recorder_on and self._recording_started_at is not None:
            if time.monotonic() - self._recording_started_at > self._MAX_RECORDING_S:
                self._emergency_reset("max duration exceeded")

    def _emergency_reset(self, reason: str = ""):
        self.recorder.stop()
        self.hotkey.force_reset()
        self._recording_started_at = None
        self._mismatch_ticks = 0
        self._pasting = False
        self.status_item.title = self._idle_title()
        self.overlay.performSelectorOnMainThread_withObject_waitUntilDone_("hide:", None, False)

    def _sync_update_item(self):
        s = self._update_state
        if s is None:
            title, enabled = "Check for Updates", True
        elif s == "checking":
            title, enabled = "Checking for updates…", False
        elif s == 0:
            title, enabled = "Up to date ✓", True
        elif isinstance(s, int):
            title, enabled = "Update Available — Install", True
        elif s == "installing":
            title, enabled = "Installing update…", False
        elif s == "restarting":
            title, enabled = "Restarting…", False
        else:  # 'error'
            title, enabled = "Update check failed — retry", True
        self.update_item.title = title
        self.update_item._menuitem.setEnabled_(enabled)

    def _refresh_history(self):
        """Must be called on the main thread (AppKit constraint)."""
        for key in list(self.history_menu.keys()):
            del self.history_menu[key]

        items = self.db.get_recent(self.config.history_limit)
        if not items:
            self.history_menu["_empty"] = rumps.MenuItem("(empty)")
            return

        for item in items:
            snippet = item["text"][:38] + ("…" if len(item["text"]) > 38 else "")
            model = item["model"] or "?"
            secs = item["latency_ms"] / 1000
            age = format_age(item["created_at"])
            label = f"{snippet}    {age}  ·  {model}  {secs:.1f}s"
            text = item["text"]
            mi = rumps.MenuItem(label, callback=lambda _, t=text: self._recopy(t))
            self.history_menu[str(item["id"])] = mi

        # Separator via a disabled, untitled item — avoids None dict-key ambiguity.
        self.history_menu["_clear"] = rumps.MenuItem(
            "— Clear History", callback=self._clear_history
        )

    # ---------------------------------------------------------- permissions

    def _check_permissions(self):
        """Warn the user if required macOS permissions are missing."""
        try:
            import ApplicationServices  # type: ignore  # macOS-only

            if not ApplicationServices.AXIsProcessTrusted():
                self.status_item.title = "⚠ Grant Accessibility — System Settings"
                logger.warning("Accessibility permission not granted")
                rumps.notification(
                    "Wisper",
                    "Accessibility permission required",
                    "System Settings → Privacy & Security → Accessibility",
                    sound=False,
                )
        except Exception:
            pass  # not on macOS or permission API unavailable

    # --------------------------------------------------------------- hotkey

    def _setup_hotkey(self):
        if hasattr(self, "hotkey"):
            self.hotkey.stop()
        self.hotkey = HotkeyManager(
            on_start=self._on_fn_down,
            on_stop=self._on_fn_up,
            vk=self.config.hotkey_vk,
            key_name=self.config.hotkey_key,
        )
        self.hotkey.start()

    def _sync_hotkey_checkmarks(self):
        for (vk, key_name), (item, name) in self.hotkey_preset_items.items():
            current = self.config.hotkey_vk == vk and self.config.hotkey_key == key_name
            item.title = ("✓ " if current else "   ") + name
        self.hotkey_menu.title = f"Hotkey: {self._hotkey_label()}"

    def _set_hotkey(self, vk: int, key_name: str):
        self.config.hotkey_vk = vk
        self.config.hotkey_key = key_name
        self.config.save()
        self._sync_hotkey_checkmarks()
        self._setup_hotkey()
        logger.info("Hotkey changed to: %s", self._hotkey_label())

    def _mic_label(self) -> str:
        return f"Microphone: {self.config.mic_name or 'System Default'}"

    def _build_mic_submenu(self):
        for key in list(self.mic_menu.keys()):
            del self.mic_menu[key]
        self.mic_items = {}

        item = rumps.MenuItem("System Default", callback=lambda _: self._set_mic(""))
        self.mic_menu["__system__"] = item
        self.mic_items[""] = item

        for name in _get_input_devices():
            i = rumps.MenuItem(name, callback=lambda _, n=name: self._set_mic(n))
            self.mic_menu[name] = i
            self.mic_items[name] = i

        self.mic_menu["__refresh__"] = rumps.MenuItem(
            "— Refresh Device List", callback=lambda _: self._build_mic_submenu()
        )
        self._sync_mic_checkmarks()

    def _sync_mic_checkmarks(self):
        current = self.config.mic_name
        for name, item in self.mic_items.items():
            label = "System Default" if name == "" else name
            item.title = ("✓ " if name == current else "   ") + label
        self.mic_menu.title = self._mic_label()

    def _set_mic(self, name: str):
        self.config.mic_name = name
        self.config.save()
        self.recorder.device = name or None
        self._sync_mic_checkmarks()
        logger.info("Microphone changed to: %s", name or "System Default")

    # ------------------------------------------------------------ recording

    def _on_fn_down(self):
        try:
            self.recorder.start()
        except Exception as exc:
            logger.error("Could not start recording: %s", exc)
            rumps.notification("Wisper", "Could not start recording", str(exc), sound=False)
            raise  # re-raise so HotkeyManager rolls back _recording = False
        self._recording_started_at = time.monotonic()
        logger.info("Recording started")
        self.status_item.title = f"Recording… tap {self._hotkey_label()} to stop"
        self.overlay.performSelectorOnMainThread_withObject_waitUntilDone_("show:", None, False)

    def _on_fn_up(self):
        self._recording_started_at = None
        audio_ms = self.recorder.duration_ms()
        audio = self.recorder.stop()
        self.overlay.performSelectorOnMainThread_withObject_waitUntilDone_("hide:", None, False)

        self.status_item.title = self._idle_title()

        if audio is None or audio_ms < MIN_AUDIO_MS:
            return

        self.status_item.title = "Transcribing…"

        try:
            t0 = time.monotonic()
            text = self.transcriber.transcribe(audio)
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.info("Transcribed %d ms audio in %d ms", audio_ms, latency_ms)
        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            rumps.notification("Wisper", "Transcription failed", str(exc), sound=False)
            self.status_item.title = self._idle_title()
            return

        self.status_item.title = self._idle_title()

        if not text:
            return

        text = self.postprocessor.clean(text)
        self._paste(text)
        self.db.add(text, audio_ms=audio_ms, model=self.config.model, latency_ms=latency_ms)
        self._needs_history_refresh = True

    # -------------------------------------------------------------- output

    def _paste(self, text: str):
        # Snapshot the full clipboard (all types, including images) as raw bytes.
        # Reading NSPasteboard is safe from any thread; writing requires main thread,
        # so the restore is deferred to _ui_tick via _pending_restore.
        pb = AppKit.NSPasteboard.generalPasteboard()
        saved_items = []
        for item in pb.pasteboardItems() or []:
            saved_data = {}
            for ptype in item.types():
                data = item.dataForType_(ptype)
                if data:
                    saved_data[ptype] = bytes(data)
            if saved_data:
                saved_items.append(saved_data)

        # Guard the pbcopy→cmd+v window so _ui_tick won't restore a stale
        # clipboard snapshot from a previous transcription in between them.
        self._pasting = True
        self._pending_restore = None  # discard any unprocessed previous restore
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to keystroke "v" using command down',
            ]
        )
        # Set restore payload before clearing the flag so _ui_tick always sees
        # both fields in a consistent state (Python GIL makes each assignment atomic).
        self._pending_restore = saved_items
        self._pasting = False

    def _recopy(self, text: str):
        subprocess.run(["pbcopy"], input=text.encode(), check=True)

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
        if s in (None, 0, "error"):
            self._update_state = "checking"
            # Safety release so a hung network can't trap the menu forever.
            threading.Timer(15.0, self._unblock_menu).start()
            threading.Thread(target=self._run_update_check, daemon=True).start()
        elif isinstance(s, int) and s > 0:
            self._update_state = "installing"
            threading.Thread(target=self._run_install, daemon=True).start()

    def _unblock_menu(self):
        pass  # No delegate to unblock; kept for _run_update_check compatibility.

    def _run_update_check(self):
        n = check_for_updates(REPO_DIR)
        self._unblock_menu()
        if n < 0:
            self._update_state = "error"
        elif n == 0:
            self._update_state = 0
            threading.Timer(4.0, self._reset_update_state).start()
        else:
            # Updates found — install and restart without requiring a second click.
            logger.info("Update check: %d update(s) available, installing", n)
            self._update_state = "installing"
            self._run_install()

    def _reset_update_state(self):
        if self._update_state == 0:
            self._update_state = None

    def _run_install(self):
        ok = install_update(REPO_DIR)
        if not ok:
            logger.error("Update install failed; leaving running instance untouched")
            self._update_state = "error"
            return

        self.hotkey.stop()

        # Try launchctl kickstart first — this handles the normal launchd-managed
        # case and starts the new process before this one exits.
        r = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.wisper.app"],
            capture_output=True,
        )
        if r.returncode != 0:
            logger.warning(
                "launchctl kickstart failed (%s); falling back to direct relaunch",
                r.stderr.decode(errors="replace").strip(),
            )
            # Not managed by launchd (e.g. started from terminal) — spawn directly.
            launcher = REPO_DIR / "Wisper.app" / "Contents" / "MacOS" / "Wisper"
            if launcher.exists():
                subprocess.Popen(
                    [str(launcher)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,  # detach so it survives this process exiting
                )
            else:
                logger.error("Update install: no launcher found at %s; cannot relaunch", launcher)
        else:
            logger.info("Update install: relaunched via launchctl kickstart")

        # Signal _ui_tick to call rumps.quit_application() on the main thread.
        # Calling it directly here (background thread) causes an unclean exit
        # that makes launchd throttle the restart.
        self._update_state = "restarting"

    # --------------------------------------------------------------- quit

    def _quit(self, _):
        self.hotkey.stop()
        rumps.quit_application()


if __name__ == "__main__":  # pragma: no cover
    WisperApp().run()
