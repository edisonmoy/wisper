"""Tests for RecordingOverlay and _WaveformView.

AppKit / Foundation / objc are stubbed by conftest.py on Linux.
"""

from unittest.mock import MagicMock, patch

# Imports happen after conftest installs stubs, so these are safe on Linux.
from overlay import (
    RecordingOverlay,
    _WaveformView,
    create_recording_overlay,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_overlay(visible=False, waveform=None):
    """Construct a RecordingOverlay bypassing Objective-C alloc/init."""
    obj = RecordingOverlay.__new__(RecordingOverlay)
    obj._get_waveform = lambda: waveform if waveform is not None else [0.1, 0.2, 0.3]
    obj._visible = visible
    obj._waveform_view = MagicMock()
    obj._panel = MagicMock()
    return obj


def _make_waveform_view():
    """Construct a _WaveformView, bypassing AppKit's alloc/initWithFrame_."""
    wv = _WaveformView.__new__(_WaveformView)
    wv._samples = []
    return wv


# ---------------------------------------------------------------------------
# _WaveformView
# ---------------------------------------------------------------------------


def test_waveform_view_init_sets_empty_samples():
    """_WaveformView.initWithFrame_ stores an empty sample list."""
    frame = ((0, 0), (200, 44))
    wv = _WaveformView.alloc().initWithFrame_(frame)
    assert wv._samples == []


def test_set_samples_stores_values():
    wv = _make_waveform_view()
    wv.setSamples_([0.1, 0.5, 0.9])
    assert wv._samples == [0.1, 0.5, 0.9]


def test_set_samples_triggers_redisplay(monkeypatch):
    wv = _make_waveform_view()
    redraws = []
    monkeypatch.setattr(wv, "setNeedsDisplay_", lambda _: redraws.append(True), raising=False)
    # Provide setNeedsDisplay_ on the instance since NSView is mocked
    wv.setNeedsDisplay_ = lambda _: redraws.append(True)
    wv.setSamples_([0.3])
    assert redraws  # setNeedsDisplay_ was called


def test_is_opaque_returns_false():
    wv = _make_waveform_view()
    assert wv.isOpaque() is False


def test_draw_rect_no_crash_with_empty_samples():
    """drawRect_ with no samples must not raise."""
    wv = _make_waveform_view()
    wv.drawRect_(None)  # should be a no-op when samples is empty


def test_draw_rect_no_crash_with_samples():
    """drawRect_ with valid samples must not raise (AppKit calls are mocked)."""
    wv = _make_waveform_view()
    wv._samples = [0.1, 0.5, 1.0, 0.3]
    # bounds() is an AppKit method; provide a fake return value.
    import collections

    FakeSize = collections.namedtuple("FakeSize", ["width", "height"])
    FakeBounds = collections.namedtuple("FakeBounds", ["size"])
    wv.bounds = lambda: FakeBounds(size=FakeSize(width=200.0, height=44.0))
    wv.drawRect_(None)  # must not raise


def test_draw_rect_handles_near_zero_max():
    """drawRect_ when all samples are below the 0.001 floor must not raise."""
    wv = _make_waveform_view()
    wv._samples = [0.0, 0.0, 0.0]
    import collections

    FakeSize = collections.namedtuple("FakeSize", ["width", "height"])
    FakeBounds = collections.namedtuple("FakeBounds", ["size"])
    wv.bounds = lambda: FakeBounds(size=FakeSize(width=200.0, height=44.0))
    wv.drawRect_(None)


# ---------------------------------------------------------------------------
# RecordingOverlay public API
# ---------------------------------------------------------------------------


def test_show_sets_visible_true():
    overlay = _make_overlay(visible=False)
    overlay.show_(None)
    assert overlay._visible is True


def test_show_calls_order_front():
    overlay = _make_overlay(visible=False)
    overlay.show_(None)
    overlay._panel.orderFrontRegardless.assert_called_once()


def test_hide_sets_visible_false():
    overlay = _make_overlay(visible=True)
    overlay.hide_(None)
    assert overlay._visible is False


def test_hide_calls_order_out():
    overlay = _make_overlay(visible=True)
    overlay.hide_(None)
    overlay._panel.orderOut_.assert_called_once_with(None)


def test_show_repositions_to_cursor_screen():
    """show_() must call _reposition_to_cursor_screen without raising."""
    overlay = _make_overlay()
    with patch.object(overlay, "_reposition_to_cursor_screen") as mock_repos:
        overlay.show_(None)
    mock_repos.assert_called_once()


# ---------------------------------------------------------------------------
# tick_ / waveform refresh
# ---------------------------------------------------------------------------


def test_tick_updates_waveform_when_visible():
    overlay = _make_overlay(visible=True, waveform=[0.1, 0.2])
    overlay.tick_(None)
    overlay._waveform_view.setSamples_.assert_called_once_with([0.1, 0.2])


def test_tick_skips_update_when_not_visible():
    overlay = _make_overlay(visible=False, waveform=[0.5])
    overlay.tick_(None)
    overlay._waveform_view.setSamples_.assert_not_called()


def test_tick_skips_update_when_waveform_view_is_none():
    overlay = _make_overlay(visible=True)
    overlay._waveform_view = None
    overlay.tick_(None)  # must not raise


# ---------------------------------------------------------------------------
# _reposition_to_cursor_screen
# ---------------------------------------------------------------------------


def test_reposition_no_crash_when_panel_none():
    """If _panel is None (build_panel skipped), reposition must not raise."""
    overlay = _make_overlay()
    overlay._panel = None
    overlay._reposition_to_cursor_screen()  # must not raise


def test_reposition_places_panel_on_cursor_screen():
    overlay = _make_overlay()
    overlay._reposition_to_cursor_screen()
    overlay._panel.setFrameOrigin_.assert_called_once()


# ---------------------------------------------------------------------------
# _build_panel
# ---------------------------------------------------------------------------


def test_build_panel_no_crash_when_screen_is_none():
    """If NSScreen.mainScreen() returns None, _build_panel must be a no-op."""
    import overlay as ov_module

    with patch.object(ov_module, "NSScreen") as mock_screen:
        mock_screen.mainScreen.return_value = None
        obj = RecordingOverlay.__new__(RecordingOverlay)
        obj._waveform_view = None
        obj._panel = None
        obj._build_panel()
    assert obj._panel is None  # was not set


def test_build_panel_sets_panel_and_waveform_view():
    """_build_panel should set _panel and _waveform_view when a screen is available."""
    obj = RecordingOverlay.__new__(RecordingOverlay)
    obj._waveform_view = None
    obj._panel = None
    obj._build_panel()
    # With mocked AppKit, these will be MagicMock instances (not None).
    assert obj._panel is not None
    assert obj._waveform_view is not None


# ---------------------------------------------------------------------------
# create_recording_overlay factory
# ---------------------------------------------------------------------------


def test_create_recording_overlay_returns_overlay():
    def waveform_fn():
        return [0.0] * 44

    overlay = create_recording_overlay(waveform_fn)
    assert isinstance(overlay, RecordingOverlay)


def test_create_recording_overlay_stores_waveform_fn():
    data = [0.5] * 44
    overlay = create_recording_overlay(lambda: data)
    assert overlay._get_waveform() is data


# ---------------------------------------------------------------------------
# show_ / hide_ with _panel=None
# ---------------------------------------------------------------------------


def test_show_no_crash_when_panel_none():
    """show_() when _panel is None must not raise and sets _visible=True."""
    overlay = _make_overlay(visible=False)
    overlay._panel = None
    with patch.object(overlay, "_reposition_to_cursor_screen"):
        overlay.show_(None)
    assert overlay._visible is True


def test_hide_no_crash_when_panel_none():
    """hide_() when _panel is None must not raise and sets _visible=False."""
    overlay = _make_overlay(visible=True)
    overlay._panel = None
    overlay.hide_(None)
    assert overlay._visible is False


# ---------------------------------------------------------------------------
# _reposition_to_cursor_screen – multi-screen iteration
# (monkeypatched at the module level so real ObjC selectors are not modified)
# ---------------------------------------------------------------------------


def test_reposition_cursor_not_on_any_listed_screen(monkeypatch):
    """When the cursor is outside all known screens, mainScreen is used."""
    import overlay as ov_module

    overlay_obj = _make_overlay()

    mouse = MagicMock()
    mouse.x = 9999.0
    mouse.y = 9999.0

    sf = MagicMock()
    sf.origin.x = 0.0
    sf.origin.y = 0.0
    sf.size.width = 1920.0
    sf.size.height = 1080.0

    main_screen = MagicMock()
    main_screen.frame.return_value = sf

    mock_nsevent = MagicMock()
    mock_nsevent.mouseLocation.return_value = mouse

    mock_nsscreen = MagicMock()
    mock_nsscreen.screens.return_value = [main_screen]
    mock_nsscreen.mainScreen.return_value = main_screen

    monkeypatch.setattr(ov_module, "NSEvent", mock_nsevent)
    monkeypatch.setattr(ov_module, "NSScreen", mock_nsscreen)

    overlay_obj._reposition_to_cursor_screen()
    overlay_obj._panel.setFrameOrigin_.assert_called_once()


def test_reposition_cursor_on_second_screen(monkeypatch):
    """_reposition_to_cursor_screen selects the screen that actually contains the cursor."""
    import overlay as ov_module

    overlay_obj = _make_overlay()

    mouse = MagicMock()
    mouse.x = 2500.0
    mouse.y = 100.0

    sf1 = MagicMock()
    sf1.origin.x = 0.0
    sf1.origin.y = 0.0
    sf1.size.width = 1920.0
    sf1.size.height = 1080.0

    sf2 = MagicMock()
    sf2.origin.x = 1920.0
    sf2.origin.y = 0.0
    sf2.size.width = 1920.0
    sf2.size.height = 1080.0

    screen1 = MagicMock()
    screen1.frame.return_value = sf1
    screen2 = MagicMock()
    screen2.frame.return_value = sf2

    mock_nsevent = MagicMock()
    mock_nsevent.mouseLocation.return_value = mouse

    mock_nsscreen = MagicMock()
    mock_nsscreen.screens.return_value = [screen1, screen2]
    mock_nsscreen.mainScreen.return_value = screen1

    monkeypatch.setattr(ov_module, "NSEvent", mock_nsevent)
    monkeypatch.setattr(ov_module, "NSScreen", mock_nsscreen)

    overlay_obj._reposition_to_cursor_screen()
    overlay_obj._panel.setFrameOrigin_.assert_called_once()


# ---------------------------------------------------------------------------
# create_recording_overlay factory
# ---------------------------------------------------------------------------


def test_create_recording_overlay_starts_not_visible():
    overlay = create_recording_overlay(lambda: [])
    assert overlay._visible is False
