"""Tests for the permission checklist window.

AppKit / Foundation / objc are stubbed by conftest.py on Linux, so every
AppKit object here is a MagicMock and we assert on the calls made to it.
"""

from unittest.mock import MagicMock, patch

import pytest

import setup_window
from setup_window import (
    _ALL_SET,
    _DRAG_OP_COPY,
    _INTRO,
    _drag_hint_text,
    _DragTile,
    _wisper_icon,
    create_setup_window,
)

GRANTED = {"mic": "granted", "ax": "granted"}
MISSING = {"mic": "missing", "ax": "missing"}


@pytest.fixture
def statuses():
    """Mutable permission state read by the controller on each refresh."""
    state = dict(MISSING)
    with (
        patch("permissions.microphone_status", side_effect=lambda: state["mic"]),
        patch("permissions.accessibility_status", side_effect=lambda: state["ax"]),
    ):
        yield state


def _fresh_mock(*_a, **_kw):
    return MagicMock()


@pytest.fixture
def ctl(statuses):
    # Give every created view its own mock so per-row assertions are meaningful
    # (a plain MagicMock factory would return the same object every time).
    image_view_cls = MagicMock()
    image_view_cls.alloc.return_value.initWithFrame_.side_effect = _fresh_mock
    drag_tile_cls = MagicMock()
    drag_tile_cls.alloc.return_value.initWithFrame_.side_effect = _fresh_mock
    with (
        patch("setup_window.NSButton") as button_cls,
        patch("setup_window.NSTextField") as text_cls,
        patch("setup_window.NSImageView", image_view_cls),
        patch("setup_window._DragTile", drag_tile_cls),
        patch("setup_window.NSWindow"),
    ):
        button_cls.buttonWithTitle_target_action_.side_effect = _fresh_mock
        text_cls.labelWithString_.side_effect = _fresh_mock
        on_change = MagicMock()
        obj = create_setup_window(on_change)
        obj._on_change_mock = on_change
        yield obj


def _shown(ctl):
    with patch("setup_window.NSTimer") as timer_cls:
        ctl.show_(None)
    return timer_cls


# ------------------------------------------------------------------ factory


def test_factory_initialises_state(ctl):
    assert ctl._window is None
    assert ctl._timer is None
    assert ctl._statuses == {}
    assert ctl._drag_hint == []


# --------------------------------------------------------------------- show


def test_show_builds_window_once_and_starts_polling(ctl):
    timer_cls = _shown(ctl)
    window = ctl._window
    assert window is not None
    assert set(ctl._rows) == {"mic", "ax"}
    assert len(ctl._drag_hint) == 2
    window.makeKeyAndOrderFront_.assert_called_with(None)
    timer_cls.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_.assert_called_once()

    _shown(ctl)  # second show reuses the window and the running timer
    assert ctl._window is window


def test_show_positions_window_on_left_of_main_screen(ctl):
    screen = MagicMock()
    vf = screen.visibleFrame.return_value
    vf.origin.x, vf.origin.y, vf.size.height = 0, 0, 1000
    with patch("setup_window.NSScreen") as ns_screen:
        ns_screen.mainScreen.return_value = screen
        _shown(ctl)
    ctl._window.setFrameOrigin_.assert_called_with((40, (1000 - setup_window.WIN_H) / 2))


def test_show_without_screen_skips_positioning(ctl):
    with patch("setup_window.NSScreen") as ns_screen:
        ns_screen.mainScreen.return_value = None
        _shown(ctl)
    ctl._window.setFrameOrigin_.assert_not_called()


def test_show_reports_initial_statuses(ctl):
    _shown(ctl)
    ctl._on_change_mock.assert_called_once_with(MISSING)


def test_show_hides_drag_hint(ctl):
    _shown(ctl)
    for view in ctl._drag_hint:
        view.setHidden_.assert_called_with(True)


# ------------------------------------------------------------------ actions


def test_mic_click_requests_microphone(ctl):
    with patch("permissions.request_microphone") as req:
        ctl.micClicked_(None)
    req.assert_called_once()


def test_ax_click_requests_accessibility_and_reveals_drag_hint(ctl):
    _shown(ctl)
    with patch("permissions.request_accessibility") as req:
        ctl.axClicked_(None)
    req.assert_called_once()
    for view in ctl._drag_hint:
        view.setHidden_.assert_called_with(False)


def test_tick_refreshes(ctl, statuses):
    _shown(ctl)
    statuses["mic"] = "granted"
    ctl.tick_(None)
    ctl._on_change_mock.assert_called_with({"mic": "granted", "ax": "missing"})


# --------------------------------------------------------- close / polling


def test_close_without_window_is_noop(ctl):
    ctl.close_(None)


def test_done_hides_window_but_keeps_polling_while_missing(ctl):
    _shown(ctl)
    timer = ctl._timer
    ctl.doneClicked_(None)
    ctl._window.orderOut_.assert_called_once_with(None)
    assert ctl._timer is timer
    timer.invalidate.assert_not_called()


def test_close_stops_polling_once_all_granted(ctl, statuses):
    statuses.update(GRANTED)
    _shown(ctl)
    timer = ctl._timer
    ctl.windowWillClose_(None)
    timer.invalidate.assert_called_once()
    assert ctl._timer is None


def test_background_poll_stops_when_granted_while_hidden(ctl, statuses):
    _shown(ctl)
    ctl.close_(None)
    timer = ctl._timer
    ctl._window.isVisible.return_value = False
    statuses.update(GRANTED)
    ctl.tick_(None)
    timer.invalidate.assert_called_once()
    assert ctl._timer is None


def test_stop_timer_if_done_without_timer(ctl, statuses):
    statuses.update(GRANTED)
    _shown(ctl)
    ctl._timer = None
    ctl.close_(None)  # must not raise


# ------------------------------------------------------------------ refresh


def test_refresh_skips_when_unchanged(ctl):
    _shown(ctl)
    ctl._on_change_mock.reset_mock()
    ctl._done_button.reset_mock()
    ctl.tick_(None)
    ctl._on_change_mock.assert_not_called()
    ctl._done_button.setTitle_.assert_not_called()


def test_forced_refresh_without_change_does_not_notify(ctl):
    _shown(ctl)
    ctl._on_change_mock.reset_mock()
    _shown(ctl)
    ctl._on_change_mock.assert_not_called()


def test_refresh_all_granted_switches_to_done(ctl, statuses):
    statuses.update(GRANTED)
    _shown(ctl)
    ctl._done_button.setTitle_.assert_called_with("Done")
    ctl._done_button.setKeyEquivalent_.assert_called_with("\r")
    ctl._intro.setStringValue_.assert_called_with(_ALL_SET)
    for row in ctl._rows.values():
        row["button"].setHidden_.assert_called_with(True)
        row["detail"].setStringValue_.assert_called_with("Enabled")


def test_refresh_missing_shows_later_and_step_buttons(ctl):
    _shown(ctl)
    ctl._done_button.setTitle_.assert_called_with("Later")
    ctl._intro.setStringValue_.assert_called_with(_INTRO)
    ctl._rows["mic"]["button"].setTitle_.assert_called_with("Allow")
    ctl._rows["ax"]["button"].setTitle_.assert_called_with("Open Settings")
    ctl._rows["mic"]["button"].setHidden_.assert_called_with(False)


def test_refresh_denied_mic_points_to_settings(ctl, statuses):
    statuses["mic"] = "denied"
    _shown(ctl)
    row = ctl._rows["mic"]
    row["button"].setTitle_.assert_called_with("Open Settings")
    assert "Settings" in row["detail"].setStringValue_.call_args.args[0]


def test_refresh_hides_drag_hint_once_accessibility_granted(ctl, statuses):
    _shown(ctl)
    with patch("permissions.request_accessibility"):
        ctl.axClicked_(None)
    statuses["ax"] = "granted"
    ctl.tick_(None)
    for view in ctl._drag_hint:
        view.setHidden_.assert_called_with(True)


# ---------------------------------------------------------------- drag tile


def test_wisper_icon_prefers_generated_icns(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "wisper.icns").write_bytes(b"x")
    with (
        patch("setup_window.REPO_DIR", tmp_path),
        patch("setup_window.NSImage") as ns_image,
    ):
        icon = _wisper_icon()
    ns_image.alloc.return_value.initWithContentsOfFile_.assert_called_once_with(
        str(tmp_path / "assets" / "wisper.icns")
    )
    assert icon is ns_image.alloc.return_value.initWithContentsOfFile_.return_value


def test_wisper_icon_falls_back_to_binary_icon(tmp_path):
    with (
        patch("setup_window.REPO_DIR", tmp_path),
        patch("setup_window.NSWorkspace") as ws,
        patch("permissions.responsible_binary", return_value="/bin/python3.11"),
    ):
        icon = _wisper_icon()
    ws.sharedWorkspace.return_value.iconForFile_.assert_called_once_with("/bin/python3.11")
    assert icon is ws.sharedWorkspace.return_value.iconForFile_.return_value


def test_drag_tile_drags_responsible_binary_file_url():
    tile = _DragTile.__new__(_DragTile)
    tile._icon = MagicMock()
    tile.bounds = MagicMock()
    tile.beginDraggingSessionWithItems_event_source_ = MagicMock()
    event = MagicMock()
    with (
        patch("setup_window.NSDraggingItem") as drag_item,
        patch("setup_window.NSURL") as ns_url,
        patch("permissions.responsible_binary", return_value="/bin/python3.11"),
    ):
        tile.mouseDown_(event)
    ns_url.fileURLWithPath_.assert_called_once_with("/bin/python3.11")
    item = drag_item.alloc.return_value.initWithPasteboardWriter_.return_value
    item.setDraggingFrame_contents_.assert_called_once_with(tile.bounds.return_value, tile._icon)
    tile.beginDraggingSessionWithItems_event_source_.assert_called_once_with([item], event, tile)


def test_drag_tile_offers_copy_operation():
    tile = _DragTile.__new__(_DragTile)
    assert tile.draggingSession_sourceOperationMaskForDraggingContext_(None, 0) == _DRAG_OP_COPY


def test_drag_hint_text_for_wisper_bundle():
    assert _drag_hint_text("Wisper") == "Turn on Wisper. Not listed? Drag this in:"


def test_drag_hint_text_explains_interpreter_name():
    assert "python3.11 (that's Wisper)" in _drag_hint_text("python3.11")
