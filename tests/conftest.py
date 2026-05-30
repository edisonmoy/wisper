import sys

# ---------------------------------------------------------------------------
# pynput mock — headless Linux has no X display
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# macOS / AppKit mocks — only available on macOS
# ---------------------------------------------------------------------------


def _macos_available():
    try:
        import AppKit  # noqa: F401

        return True
    except ImportError:
        return False


def _install_macos_mocks():
    """Install minimal AppKit/Foundation/objc/rumps/setproctitle stubs for Linux CI.

    Key requirements:
    - AppKit.NSObject must be a real Python class so that subclasses
      (_MenuDelegate, RecordingOverlay, _WaveformView) can inherit from it.
    - objc.super(cls, self) must return an object whose init / initWithFrame_
      return *self*, matching the PyObjC self-reassignment pattern.
    - objc.python_method must be a no-op decorator.
    - rumps.App and rumps.MenuItem must be real classes (both are subclassed
      or instantiated extensively by WisperApp).
    """
    from unittest.mock import MagicMock

    # ------------------------------------------------------------------
    # NSObject base — must be a concrete Python class for subclassing.
    # ------------------------------------------------------------------
    class _FakeNSObject:
        def __getattr__(self, name):
            # Return a callable MagicMock for any AppKit selector not explicitly
            # defined (e.g. setOpaque_, setNeedsDisplay_, contentView, …).
            return MagicMock()

        @classmethod
        def alloc(cls):
            return cls.__new__(cls)

        def init(self):
            return self

        def initWithFrame_(self, frame):
            return self

        def initWithContentRect_styleMask_backing_defer_(self, *a):
            return self

    # ------------------------------------------------------------------
    # objc
    # ------------------------------------------------------------------
    def _fake_super(cls, self_obj):
        """Mimics objc.super(cls, self) — returns object whose .init* return self_obj."""
        m = MagicMock()
        m.init.return_value = self_obj
        m.initWithFrame_.return_value = self_obj
        return m

    objc_mock = MagicMock()
    objc_mock.super = _fake_super
    objc_mock.python_method = staticmethod(lambda f: f)  # no-op decorator

    # ------------------------------------------------------------------
    # AppKit
    # ------------------------------------------------------------------
    appkit_mock = MagicMock()
    appkit_mock.NSObject = _FakeNSObject
    appkit_mock.NSView = _FakeNSObject
    appkit_mock.NSPanel = _FakeNSObject
    appkit_mock.NSApplicationActivationPolicyProhibited = 2
    # NSApplication.sharedApplication().setActivationPolicy_(...) runs at
    # app.py module level — must not raise.
    appkit_mock.NSApplication.sharedApplication.return_value = MagicMock()

    # ------------------------------------------------------------------
    # Foundation
    # ------------------------------------------------------------------
    foundation_mock = MagicMock()

    # ------------------------------------------------------------------
    # rumps — App is subclassed by WisperApp; MenuItem is instantiated heavily.
    # ------------------------------------------------------------------
    class _RumpsMenuItem:
        def __init__(self, title="", callback=None, **kw):
            self.title = title
            self.callback = callback
            self._menuitem = MagicMock()
            self._items: dict = {}

        def __setitem__(self, k, v):
            self._items[k] = v

        def __getitem__(self, k):
            return self._items[k]

        def __delitem__(self, k):
            del self._items[k]

        def keys(self):
            return list(self._items.keys())

        def __contains__(self, k):
            return k in self._items

    class _RumpsApp:
        def __init__(self, name, quit_button=None):
            self.name = name
            self.menu = []
            self._nsapp = MagicMock()
            self._nsapp.nsstatusitem = MagicMock()

        def run(self):  # pragma: no cover
            pass

    rumps_mock = MagicMock()
    rumps_mock.App = _RumpsApp
    rumps_mock.MenuItem = _RumpsMenuItem
    # Use a factory so rumps.Timer(callback, interval) returns a fresh
    # MagicMock() with no spec (passing MagicMock directly would use the
    # callback as the spec, hiding attributes like .start).
    rumps_mock.Timer = lambda *a, **kw: MagicMock()
    rumps_mock.notification = MagicMock()
    rumps_mock.quit_application = MagicMock()

    sys.modules.update(
        {
            "AppKit": appkit_mock,
            "Foundation": foundation_mock,
            "objc": objc_mock,
            "rumps": rumps_mock,
            "setproctitle": MagicMock(),
        }
    )


if not _macos_available():
    _install_macos_mocks()
