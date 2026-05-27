import sys


def _install_pynput_mock():
    """Provide a minimal pynput stub for headless (no X display) environments."""
    from unittest.mock import MagicMock

    class KeyCode:
        """Mirrors pynput.keyboard.KeyCode just enough for _is_fn and toggle tests."""

        def __init__(self, vk=None, char=None, **kw):
            self.vk = vk
            self.char = char

        @classmethod
        def from_char(cls, char):
            return cls(char=char)

        def __repr__(self):
            return f"KeyCode(vk={self.vk}, char={self.char!r})"

    class _SpecialKey:
        def __init__(self, name):
            self.name = name

    class Key:
        space = _SpecialKey("space")
        enter = _SpecialKey("enter")
        esc = _SpecialKey("esc")

    keyboard_mock = MagicMock()
    keyboard_mock.KeyCode = KeyCode
    keyboard_mock.Key = Key
    keyboard_mock.Listener = MagicMock

    pynput_mock = MagicMock()
    pynput_mock.keyboard = keyboard_mock

    sys.modules["pynput"] = pynput_mock
    sys.modules["pynput.keyboard"] = keyboard_mock


def _pynput_available():
    try:
        from pynput import keyboard

        keyboard.KeyCode  # triggers backend init; raises on headless Linux
        return True
    except Exception:
        return False


if not _pynput_available():
    # Remove any partially-initialised pynput entries before installing the mock.
    for _key in [k for k in sys.modules if k.startswith("pynput")]:
        del sys.modules[_key]
    _install_pynput_mock()
