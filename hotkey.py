import threading
from typing import Callable
from pynput import keyboard

# macOS virtual key code for fn / Globe key (kVK_Function = 63).
# pynput only fires release events for this key (NSFlagsChanged quirk),
# so we use toggle mode: first tap starts recording, second tap stops it.
_FN_VK = 63


def _is_fn(key) -> bool:
    return isinstance(key, keyboard.KeyCode) and key.vk == _FN_VK


class HotkeyManager:
    """Toggle recording on each fn key tap (tap once = start, tap again = stop)."""

    def __init__(self, on_start: Callable, on_stop: Callable):
        self.on_start = on_start
        self.on_stop = on_stop
        self._listener: keyboard.Listener | None = None
        self._recording = False

    def start(self):
        self._listener = keyboard.Listener(
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_release(self, key):
        if not _is_fn(key):
            return
        if not self._recording:
            self._recording = True
            threading.Thread(target=self.on_start, daemon=True).start()
        else:
            self._recording = False
            threading.Thread(target=self.on_stop, daemon=True).start()
