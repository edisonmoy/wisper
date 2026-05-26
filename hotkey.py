import threading
from typing import Callable
from pynput import keyboard

# macOS virtual key code for fn / Globe key (kVK_Function = 63).
# pynput doesn't expose this as Key.fn, so we match by vk.
_FN_VK = 63


def _is_fn(key) -> bool:
    return isinstance(key, keyboard.KeyCode) and key.vk == _FN_VK


class HotkeyManager:
    """Listens for fn (Globe) key: press starts recording, release stops it."""

    def __init__(self, on_start: Callable, on_stop: Callable):
        self.on_start = on_start
        self.on_stop = on_stop
        self._listener: keyboard.Listener | None = None
        self._fn_down = False

    def start(self):
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
        if _is_fn(key) and not self._fn_down:
            self._fn_down = True
            threading.Thread(target=self.on_start, daemon=True).start()

    def _on_release(self, key):
        if _is_fn(key) and self._fn_down:
            self._fn_down = False
            threading.Thread(target=self.on_stop, daemon=True).start()
