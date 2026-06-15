import threading
import time
from typing import Callable

from pynput import keyboard

# macOS virtual key code for fn / Globe key (kVK_Function = 63).
# pynput fires on_release for NSFlagsChanged events (both press and release),
# so we use toggle mode: first event starts recording, next stops it.
_FN_VK = 63
_DEBOUNCE_S = 0.1  # ignore duplicate events within this window

_VK_LABELS: dict[int, str] = {63: "fn"}
_NAMED_KEY_LABELS: dict[str, str] = {
    "alt_r": "Right ⌥",
    "alt_l": "Left ⌥",
    "alt": "⌥",
    "ctrl_r": "Right ⌃",
    "ctrl_l": "Left ⌃",
    "shift_r": "Right ⇧",
    "shift_l": "Left ⇧",
    "cmd_r": "Right ⌘",
    "cmd_l": "Left ⌘",
    "caps_lock": "Caps Lock",
}


def key_display_name(vk: int, key_name: str) -> str:
    """Human-readable label for the configured hotkey."""
    if key_name:
        label = _NAMED_KEY_LABELS.get(key_name)
        if label:
            return label
        if key_name.startswith("f") and key_name[1:].isdigit():
            return key_name.upper()
        return key_name
    return _VK_LABELS.get(vk, f"VK {vk}")


def _is_fn(key, vk: int = _FN_VK) -> bool:
    return isinstance(key, keyboard.KeyCode) and key.vk == vk


def _is_named_key(key, name: str) -> bool:
    """Match a pynput Key enum by name (e.g. 'alt_r')."""
    try:
        return key == getattr(keyboard.Key, name)
    except AttributeError:
        return False


class HotkeyManager:
    """Push-to-talk recording triggered by a configurable hotkey.

    For the built-in Fn key (VK 63), macOS fires NSFlagsChanged for both
    press and release as on_release events, so toggle mode is used instead.
    All other keys use true push-to-talk: on_press starts, on_release stops.

    _busy blocks re-entrancy: a new press/toggle is ignored until the
    current on_start/on_stop callback returns.
    """

    def __init__(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        vk: int = _FN_VK,
        key_name: str = "",
    ):
        self.on_start = on_start
        self.on_stop = on_stop
        self._vk = vk
        self._key_name = key_name
        # Fn key can't distinguish press from release — use toggle as push-to-talk proxy.
        self._toggle_mode = not key_name and vk == _FN_VK
        self._listener: keyboard.Listener | None = None
        self._recording = False
        self._busy = False
        self._last_event = 0.0

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _matches(self, key) -> bool:
        return _is_named_key(key, self._key_name) if self._key_name else _is_fn(key, self._vk)

    def _dispatch(
        self,
        fn: Callable[[], None],
        *,
        rollback_recording: bool = False,
        clear_busy: bool = True,
    ) -> None:
        """Run fn in a daemon thread; optionally roll back _recording and/or clear _busy."""

        def _run():
            try:
                fn()
            except Exception:
                if rollback_recording:
                    self._recording = False
            finally:
                if clear_busy:
                    self._busy = False

        threading.Thread(target=_run, daemon=True).start()

    def start(self):
        if self._toggle_mode:
            self._listener = keyboard.Listener(on_release=self._on_release)
        else:
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key):
        """Push-to-talk: start recording on key down."""
        if not self._matches(key):
            return
        if self._recording or self._busy:
            return
        self._recording = True
        self._busy = True
        self._dispatch(self.on_start, rollback_recording=True)

    def _on_release(self, key):
        if not self._matches(key):
            return

        if not self._toggle_mode:
            # Push-to-talk: stop recording on key up.
            if not self._recording:
                return
            self._recording = False
            self._dispatch(self.on_stop, clear_busy=False)
            return

        # Toggle mode (Fn key only): each NSFlagsChanged event alternates start/stop.
        now = time.monotonic()
        if now - self._last_event < _DEBOUNCE_S:
            return  # absorb duplicate/rapid-fire NSFlagsChanged events
        if self._busy:
            return  # previous toggle still in flight; ignore
        self._last_event = now
        self._busy = True

        if not self._recording:
            self._recording = True
            self._dispatch(self.on_start, rollback_recording=True)
        else:
            self._recording = False
            self._dispatch(self.on_stop)

    def force_reset(self):
        """Reset all internal state — called by the watchdog when things diverge."""
        self._recording = False
        self._busy = False
