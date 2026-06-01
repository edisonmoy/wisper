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
    """Toggle recording on each fn key event.

    _busy blocks new toggles until the current on_start/on_stop callback
    returns, preventing the flag from getting out of sync with the recorder
    when the user taps fn faster than the callback can complete.
    """

    def __init__(self, on_start: Callable, on_stop: Callable, vk: int = _FN_VK, key_name: str = ""):
        self.on_start = on_start
        self.on_stop = on_stop
        self._vk = vk
        self._key_name = key_name
        self._listener: keyboard.Listener | None = None
        self._recording = False
        self._busy = False
        self._last_event = 0.0

    def start(self):
        self._listener = keyboard.Listener(on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_release(self, key):
        matched = _is_named_key(key, self._key_name) if self._key_name else _is_fn(key, self._vk)
        if not matched:
            return

        now = time.monotonic()
        if now - self._last_event < _DEBOUNCE_S:
            return  # absorb duplicate/rapid-fire NSFlagsChanged events
        if self._busy:
            return  # previous toggle still in flight; ignore
        self._last_event = now
        self._busy = True

        if not self._recording:
            self._recording = True

            def _run():
                try:
                    self.on_start()
                except Exception:
                    self._recording = False  # roll back so state stays consistent
                finally:
                    self._busy = False

            threading.Thread(target=_run, daemon=True).start()
        else:
            self._recording = False

            def _run():
                try:
                    self.on_stop()
                except Exception:
                    pass
                finally:
                    self._busy = False

            threading.Thread(target=_run, daemon=True).start()

    def force_reset(self):
        """Reset all internal state — called by the watchdog when things diverge."""
        self._recording = False
        self._busy = False
