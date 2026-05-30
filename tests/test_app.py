"""Comprehensive tests for WisperApp and supporting classes.

AppKit / Foundation / objc / rumps / setproctitle are stubbed by conftest.py
on Linux, allowing the full app module to be imported and exercised without a
real macOS display or hardware keyboard.
"""

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import app as app_mod
from app import VERSION, WisperApp, _make_menubar_image, _MenuDelegate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_app_dir(tmp_path, monkeypatch):
    """Redirect APP_DIR to a temp directory so tests don't touch ~/.wisper."""
    monkeypatch.setattr(app_mod, "APP_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def wa(tmp_app_dir):
    """WisperApp instance with all macOS side-effects suppressed.

    Patches applied for the lifetime of each test:
    - create_recording_overlay → MagicMock (no real NSPanel)
    - Transcriber.preload → no-op (no model download threads)
    - threading.Timer → MagicMock (no background threads at startup)
    - rumps.quit_application → MagicMock (would terminate the process on macOS)
    - rumps.notification → MagicMock (would show OS dialogs on macOS)
    - app.AppKit → MagicMock (real NSPasteboard is not patchable on macOS)
    """
    with patch.object(app_mod, "create_recording_overlay", return_value=MagicMock()):
        with patch.object(app_mod.Transcriber, "preload"):
            with patch("app.threading.Timer", return_value=MagicMock()):
                with (
                    patch.object(app_mod.rumps, "quit_application") as _mock_quit,
                    patch.object(app_mod.rumps, "notification") as _mock_notif,
                    patch("app.AppKit") as _mock_appkit,
                ):
                    instance = WisperApp()
                    instance._mock_quit = _mock_quit
                    instance._mock_notification = _mock_notif
                    instance._mock_appkit = _mock_appkit
                    yield instance


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def test_make_menubar_image_returns_something():
    """_make_menubar_image must not raise with mocked AppKit."""
    result = _make_menubar_image()
    assert result is not None


def test_version_constant_is_string():
    assert isinstance(VERSION, str)
    assert len(VERSION) > 0


# ---------------------------------------------------------------------------
# _MenuDelegate
# ---------------------------------------------------------------------------


class TestMenuDelegate:
    def _delegate(self):
        return _MenuDelegate.alloc().init()

    def test_initial_state(self):
        d = self._delegate()
        assert d._hover_on_update is False
        assert d._check_active is False
        assert d.update_nsitem is None

    def test_menu_should_close_true_when_idle(self):
        d = self._delegate()
        assert d.menuShouldClose_(None) is True

    def test_menu_should_close_false_when_hovering(self):
        d = self._delegate()
        d._hover_on_update = True
        assert d.menuShouldClose_(None) is False

    def test_menu_should_close_false_when_check_active(self):
        d = self._delegate()
        d._check_active = True
        assert d.menuShouldClose_(None) is False

    def test_menu_did_close_resets_hover(self):
        d = self._delegate()
        d._hover_on_update = True
        d.menuDidClose_(None)
        assert d._hover_on_update is False

    def test_highlight_sets_hover_when_on_update_item(self):
        d = self._delegate()
        item = MagicMock()
        d.update_nsitem = item
        d.menu_willHighlightItem_(None, item)
        assert d._hover_on_update is True

    def test_highlight_clears_hover_when_on_other_item(self):
        d = self._delegate()
        d.update_nsitem = MagicMock()
        d._hover_on_update = True
        d.menu_willHighlightItem_(None, MagicMock())
        assert d._hover_on_update is False

    def test_highlight_noop_when_update_nsitem_is_none(self):
        d = self._delegate()
        d.update_nsitem = None
        d.menu_willHighlightItem_(None, MagicMock())
        assert d._hover_on_update is False

    def test_highlight_noop_when_check_active(self):
        d = self._delegate()
        d._check_active = True
        item = MagicMock()
        d.update_nsitem = item
        d._hover_on_update = False
        d.menu_willHighlightItem_(None, item)
        assert d._hover_on_update is False

    def test_highlight_none_item_clears_hover(self):
        d = self._delegate()
        d.update_nsitem = MagicMock()
        d._hover_on_update = True
        d.menu_willHighlightItem_(None, None)
        assert d._hover_on_update is False


# ---------------------------------------------------------------------------
# WisperApp initialisation
# ---------------------------------------------------------------------------


def test_init_creates_recorder(wa):
    assert wa.recorder is not None


def test_init_creates_transcriber(wa):
    assert wa.transcriber is not None


def test_init_creates_db(wa):
    assert wa.db is not None


def test_init_update_state_is_none(wa):
    assert wa._update_state is None


def test_init_sets_nsapp_configured_false(wa):
    assert wa._nsapp_configured is False


# ---------------------------------------------------------------------------
# _update_state property (thread-safe)
# ---------------------------------------------------------------------------


def test_update_state_setter_and_getter(wa):
    wa._update_state = "checking"
    assert wa._update_state == "checking"


def test_update_state_setter_from_thread(wa):
    results = []

    def _set():
        wa._update_state = 42
        results.append(wa._update_state)

    t = threading.Thread(target=_set)
    t.start()
    t.join(timeout=2)
    assert results == [42]


# ---------------------------------------------------------------------------
# Menu building
# ---------------------------------------------------------------------------


def test_build_menu_creates_status_item(wa):
    assert wa.status_item is not None
    assert "fn" in wa.status_item.title.lower()


def test_build_menu_creates_history_menu(wa):
    assert wa.history_menu is not None


def test_build_menu_creates_model_items_for_all_models(wa):
    from config import MODELS

    assert set(wa.model_items.keys()) == set(MODELS)


def test_build_menu_creates_cleanup_items_for_all_modes(wa):
    from config import CLEANUP_MODES

    assert set(wa.cleanup_items.keys()) == set(CLEANUP_MODES)


def test_build_menu_has_update_item(wa):
    assert wa.update_item is not None


def test_version_constant_present_in_app_module():
    """VERSION is accessible and non-empty (menu item is built from it in _build_menu)."""
    assert VERSION and VERSION[0].isdigit()


# ---------------------------------------------------------------------------
# Checkmarks
# ---------------------------------------------------------------------------


def test_sync_model_checkmarks_marks_current_model(wa):
    from config import MODELS

    wa.config.model = MODELS[0]
    wa._sync_model_checkmarks()
    assert wa.model_items[MODELS[0]].title.startswith("✓")
    for m in MODELS[1:]:
        assert not wa.model_items[m].title.startswith("✓")


def test_sync_cleanup_checkmarks_marks_current_mode(wa):
    wa.config.cleanup_mode = "regex"
    wa._sync_cleanup_checkmarks()
    assert wa.cleanup_items["regex"].title.startswith("✓")
    assert not wa.cleanup_items["none"].title.startswith("✓")
    assert not wa.cleanup_items["ai"].title.startswith("✓")


def test_set_cleanup_updates_mode_and_saves(wa):
    wa._set_cleanup("none")
    assert wa.config.cleanup_mode == "none"
    assert wa.cleanup_items["none"].title.startswith("✓")


# ---------------------------------------------------------------------------
# _configure_nsapp
# ---------------------------------------------------------------------------


def test_configure_nsapp_calls_set_image_when_button_present(wa):
    btn = MagicMock()
    wa._nsapp = MagicMock()
    wa._nsapp.nsstatusitem.button.return_value = btn
    wa._nsapp.nsstatusitem.menu.return_value = None
    wa._configure_nsapp()
    btn.setImage_.assert_called_once()
    btn.setTitle_.assert_called_once_with("")


def test_configure_nsapp_skips_image_when_no_button(wa):
    wa._nsapp = MagicMock()
    wa._nsapp.nsstatusitem.button.return_value = None
    nsm = MagicMock()
    wa._nsapp.nsstatusitem.menu.return_value = nsm
    wa._configure_nsapp()  # must not raise


def test_configure_nsapp_sets_delegate_when_menu_present(wa):
    wa._nsapp = MagicMock()
    wa._nsapp.nsstatusitem.button.return_value = None
    nsm = MagicMock()
    wa._nsapp.nsstatusitem.menu.return_value = nsm
    wa._configure_nsapp()
    nsm.setDelegate_.assert_called_once_with(wa._menu_delegate)


def test_configure_nsapp_skips_delegate_when_no_menu(wa):
    wa._nsapp = MagicMock()
    wa._nsapp.nsstatusitem.button.return_value = None
    wa._nsapp.nsstatusitem.menu.return_value = None
    wa._configure_nsapp()  # must not raise


# ---------------------------------------------------------------------------
# _ui_tick
# ---------------------------------------------------------------------------


def test_ui_tick_calls_configure_nsapp_on_first_tick(wa):
    wa._nsapp_configured = False
    with patch.object(wa, "_configure_nsapp") as mock_cfg:
        with patch.object(wa, "_watchdog"):
            wa._ui_tick(None)
    mock_cfg.assert_called_once()
    assert wa._nsapp_configured is True


def test_ui_tick_does_not_reconfigure_after_first_tick(wa):
    wa._nsapp_configured = True
    with patch.object(wa, "_configure_nsapp") as mock_cfg:
        with patch.object(wa, "_watchdog"):
            wa._ui_tick(None)
    mock_cfg.assert_not_called()


def test_ui_tick_quits_when_restarting(wa):
    wa._update_state = "restarting"
    wa._nsapp_configured = True
    wa._ui_tick(None)
    wa._mock_quit.assert_called()


def test_ui_tick_refreshes_history_when_flagged(wa):
    wa._nsapp_configured = True
    wa._update_state = None
    wa._needs_history_refresh = True
    with patch.object(wa, "_refresh_history") as mock_refresh:
        with patch.object(wa, "_watchdog"):
            wa._ui_tick(None)
    mock_refresh.assert_called_once()
    assert wa._needs_history_refresh is False


def test_ui_tick_restores_clipboard_when_pending_and_not_pasting(wa):
    wa._nsapp_configured = True
    wa._update_state = None
    wa._pasting = False
    wa._pending_restore = [{"text/plain": b"hello"}]
    with patch.object(wa, "_restore_clipboard") as mock_restore:
        with patch.object(wa, "_watchdog"):
            wa._ui_tick(None)
    mock_restore.assert_called_once()
    assert wa._pending_restore is None


def test_ui_tick_skips_restore_when_pasting(wa):
    wa._nsapp_configured = True
    wa._update_state = None
    wa._pasting = True
    wa._pending_restore = [{"text/plain": b"hello"}]
    with patch.object(wa, "_restore_clipboard") as mock_restore:
        with patch.object(wa, "_watchdog"):
            wa._ui_tick(None)
    mock_restore.assert_not_called()


# ---------------------------------------------------------------------------
# _restore_clipboard
# ---------------------------------------------------------------------------


def test_restore_clipboard_calls_write_objects(wa):
    items = [{"public.utf8-plain-text": b"hello"}]
    mock_pb = MagicMock()
    wa._mock_appkit.NSPasteboard.generalPasteboard.return_value = mock_pb
    wa._restore_clipboard(items)
    mock_pb.writeObjects_.assert_called_once()


def test_restore_clipboard_empty_items_no_write(wa):
    """Empty saved_items list: clearContents is called but writeObjects_ is not."""
    mock_pb = MagicMock()
    wa._mock_appkit.NSPasteboard.generalPasteboard.return_value = mock_pb
    wa._restore_clipboard([])
    mock_pb.writeObjects_.assert_not_called()


def test_restore_clipboard_exception_triggers_notification(wa):
    wa._mock_appkit.NSPasteboard.generalPasteboard.side_effect = RuntimeError("boom")
    wa._restore_clipboard([{"x": b"y"}])
    wa._mock_notification.assert_called()
    wa._mock_appkit.NSPasteboard.generalPasteboard.side_effect = None


# ---------------------------------------------------------------------------
# _watchdog
# ---------------------------------------------------------------------------


def test_watchdog_no_action_when_states_match(wa):
    wa.recorder._recording = False
    wa.hotkey._recording = False
    wa._mismatch_ticks = 0
    with patch.object(wa, "_emergency_reset") as mock_reset:
        wa._watchdog()
    mock_reset.assert_not_called()
    assert wa._mismatch_ticks == 0


def test_watchdog_increments_mismatch_ticks_on_divergence(wa):
    wa.recorder._recording = True
    wa.hotkey._recording = False
    wa._mismatch_ticks = 0
    with patch.object(wa, "_emergency_reset"):
        wa._watchdog()
    assert wa._mismatch_ticks == 1


def test_watchdog_triggers_emergency_reset_after_grace_ticks(wa):
    wa.recorder._recording = True
    wa.hotkey._recording = False
    wa._mismatch_ticks = wa._MISMATCH_GRACE
    with patch.object(wa, "_emergency_reset") as mock_reset:
        wa._watchdog()
    mock_reset.assert_called_once()


def test_watchdog_resets_mismatch_ticks_when_aligned(wa):
    wa.recorder._recording = False
    wa.hotkey._recording = False
    wa._mismatch_ticks = 2
    with patch.object(wa, "_emergency_reset"):
        wa._watchdog()
    assert wa._mismatch_ticks == 0


def test_watchdog_emergency_reset_on_max_duration(wa):
    wa.recorder._recording = True
    wa.hotkey._recording = True
    wa._recording_started_at = time.monotonic() - (wa._MAX_RECORDING_S + 1)
    with patch.object(wa, "_emergency_reset") as mock_reset:
        wa._watchdog()
    mock_reset.assert_called_once()


def test_watchdog_no_reset_within_max_duration(wa):
    wa.recorder._recording = True
    wa.hotkey._recording = True
    wa._recording_started_at = time.monotonic() - 10
    with patch.object(wa, "_emergency_reset") as mock_reset:
        wa._watchdog()
    mock_reset.assert_not_called()


def test_watchdog_no_reset_when_recording_started_at_is_none(wa):
    wa.recorder._recording = True
    wa.hotkey._recording = True
    wa._recording_started_at = None
    with patch.object(wa, "_emergency_reset") as mock_reset:
        wa._watchdog()
    mock_reset.assert_not_called()


# ---------------------------------------------------------------------------
# _emergency_reset
# ---------------------------------------------------------------------------


def test_emergency_reset_stops_recorder(wa):
    with patch.object(wa.recorder, "stop") as mock_stop:
        wa._emergency_reset("test")
    mock_stop.assert_called_once()


def test_emergency_reset_forces_hotkey_reset(wa):
    with patch.object(wa.hotkey, "force_reset") as mock_fr:
        wa._emergency_reset()
    mock_fr.assert_called_once()


def test_emergency_reset_clears_state_flags(wa):
    wa._recording_started_at = 123.0
    wa._mismatch_ticks = 5
    wa._pasting = True
    wa._emergency_reset()
    assert wa._recording_started_at is None
    assert wa._mismatch_ticks == 0
    assert wa._pasting is False


def test_emergency_reset_updates_status_title(wa):
    wa._emergency_reset()
    assert wa.status_item.title == "Hold fn to record"


def test_emergency_reset_hides_overlay(wa):
    wa._emergency_reset()
    wa.overlay.performSelectorOnMainThread_withObject_waitUntilDone_.assert_called()


# ---------------------------------------------------------------------------
# _sync_update_item
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state,expected_title",
    [
        (None, "Check for Updates"),
        ("checking", "Checking for updates…"),
        (0, "Up to date ✓"),
        (3, "Update Available — Install"),
        ("installing", "Installing update…"),
        ("restarting", "Restarting…"),
        ("error", "Update check failed — retry"),
    ],
)
def test_sync_update_item_titles(wa, state, expected_title):
    wa._update_state = state
    wa._sync_update_item()
    assert wa.update_item.title == expected_title


# ---------------------------------------------------------------------------
# _refresh_history
# ---------------------------------------------------------------------------


def test_refresh_history_empty_shows_placeholder(wa):
    wa._refresh_history()
    assert "_empty" in wa.history_menu


def test_refresh_history_populated_shows_items(wa, tmp_app_dir):
    wa.db.add("hello world", audio_ms=1000, model="base.en", latency_ms=800)
    wa._refresh_history()
    assert "_empty" not in wa.history_menu
    assert "_clear" in wa.history_menu


def test_refresh_history_long_text_truncated(wa):
    long_text = "a" * 100
    wa.db.add(long_text, audio_ms=1000, model="base.en", latency_ms=800)
    wa._refresh_history()
    keys = wa.history_menu.keys()
    labels = [wa.history_menu[k].title for k in keys if k not in ("_clear",)]
    assert any("…" in lbl for lbl in labels)


def test_refresh_history_clears_old_items(wa):
    wa.db.add("item one", audio_ms=500, model="base.en", latency_ms=400)
    wa._refresh_history()
    wa.db.clear()
    wa._refresh_history()
    assert "_empty" in wa.history_menu


# ---------------------------------------------------------------------------
# _check_permissions
# ---------------------------------------------------------------------------


def test_check_permissions_noop_when_import_fails(wa):
    """If ApplicationServices is not importable, _check_permissions is a silent no-op."""
    with patch.dict(sys.modules, {"ApplicationServices": None}):
        wa._check_permissions()  # must not raise


def test_check_permissions_warns_when_not_trusted(wa):
    app_svc = MagicMock()
    app_svc.AXIsProcessTrusted.return_value = False
    with patch.dict(sys.modules, {"ApplicationServices": app_svc}):
        wa._check_permissions()
    wa._mock_notification.assert_called()


def test_check_permissions_silent_when_trusted(wa):
    wa._mock_notification.reset_mock()
    app_svc = MagicMock()
    app_svc.AXIsProcessTrusted.return_value = True
    with patch.dict(sys.modules, {"ApplicationServices": app_svc}):
        wa._check_permissions()
    wa._mock_notification.assert_not_called()


# ---------------------------------------------------------------------------
# _on_fn_down / _on_fn_up
# ---------------------------------------------------------------------------


def test_on_fn_down_starts_recording(wa):
    with patch.object(wa.recorder, "start") as mock_start:
        wa._on_fn_down()
    mock_start.assert_called_once()


def test_on_fn_down_sets_status_title(wa):
    with patch.object(wa.recorder, "start"):
        wa._on_fn_down()
    assert "Recording" in wa.status_item.title


def test_on_fn_down_records_start_time(wa):
    with patch.object(wa.recorder, "start"):
        wa._on_fn_down()
    assert wa._recording_started_at is not None


def test_on_fn_down_shows_overlay(wa):
    with patch.object(wa.recorder, "start"):
        wa._on_fn_down()
    wa.overlay.performSelectorOnMainThread_withObject_waitUntilDone_.assert_called()


def test_on_fn_down_notifies_and_reraises_on_error(wa):
    with patch.object(wa.recorder, "start", side_effect=RuntimeError("mic fail")):
        with pytest.raises(RuntimeError):
            wa._on_fn_down()
    wa._mock_notification.assert_called()


def test_on_fn_up_with_short_audio_skips_transcription(wa):
    wa.recorder._recording = False
    with patch.object(wa.recorder, "duration_ms", return_value=100):
        with patch.object(wa.recorder, "stop", return_value=np.zeros(100)):
            with patch.object(wa.transcriber, "transcribe") as mock_tx:
                wa._on_fn_up()
    mock_tx.assert_not_called()


def test_on_fn_up_with_none_audio_skips_transcription(wa):
    with patch.object(wa.recorder, "duration_ms", return_value=1000):
        with patch.object(wa.recorder, "stop", return_value=None):
            with patch.object(wa.transcriber, "transcribe") as mock_tx:
                wa._on_fn_up()
    mock_tx.assert_not_called()


def test_on_fn_up_transcription_failure_shows_notification(wa):
    with patch.object(wa.recorder, "duration_ms", return_value=1000):
        with patch.object(wa.recorder, "stop", return_value=np.zeros(16000)):
            with patch.object(wa.transcriber, "transcribe", side_effect=RuntimeError("GPU OOM")):
                wa._on_fn_up()
    wa._mock_notification.assert_called()
    assert wa.status_item.title == "Hold fn to record"


def test_on_fn_up_empty_text_skips_paste(wa):
    with patch.object(wa.recorder, "duration_ms", return_value=1000):
        with patch.object(wa.recorder, "stop", return_value=np.zeros(16000)):
            with patch.object(wa.transcriber, "transcribe", return_value=""):
                with patch.object(wa, "_paste") as mock_paste:
                    wa._on_fn_up()
    mock_paste.assert_not_called()


def test_on_fn_up_successful_transcription_pastes_and_saves(wa):
    with patch.object(wa.recorder, "duration_ms", return_value=1000):
        with patch.object(wa.recorder, "stop", return_value=np.zeros(16000)):
            with patch.object(wa.transcriber, "transcribe", return_value="hello"):
                with patch.object(wa.postprocessor, "clean", return_value="hello"):
                    with patch.object(wa, "_paste") as mock_paste:
                        with patch.object(wa.db, "add") as mock_add:
                            wa._on_fn_up()
    mock_paste.assert_called_once_with("hello")
    mock_add.assert_called_once()
    assert wa._needs_history_refresh is True


def test_on_fn_up_resets_recording_started_at(wa):
    wa._recording_started_at = 999.0
    with patch.object(wa.recorder, "duration_ms", return_value=100):
        with patch.object(wa.recorder, "stop", return_value=None):
            wa._on_fn_up()
    assert wa._recording_started_at is None


# ---------------------------------------------------------------------------
# _paste
# ---------------------------------------------------------------------------


def test_paste_calls_pbcopy(wa):
    wa._mock_appkit.NSPasteboard.generalPasteboard.return_value.pasteboardItems.return_value = []
    with patch("app.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        wa._paste("hello")
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any(c[0] == "pbcopy" for c in calls)


def test_paste_clears_pasting_flag_after_completion(wa):
    wa._mock_appkit.NSPasteboard.generalPasteboard.return_value.pasteboardItems.return_value = []
    with patch("app.subprocess.run", return_value=MagicMock(returncode=0)):
        wa._paste("test")
    assert wa._pasting is False


def test_paste_sets_pending_restore(wa):
    wa._mock_appkit.NSPasteboard.generalPasteboard.return_value.pasteboardItems.return_value = []
    with patch("app.subprocess.run", return_value=MagicMock(returncode=0)):
        wa._paste("test")
    assert wa._pending_restore is not None


def test_paste_snapshots_nonempty_clipboard_items(wa):
    """_paste captures clipboard item data into _pending_restore."""
    mock_item = MagicMock()
    mock_item.types.return_value = ["public.utf8-plain-text"]
    mock_item.dataForType_.return_value = b"previous text"

    mock_pb = wa._mock_appkit.NSPasteboard.generalPasteboard.return_value
    mock_pb.pasteboardItems.return_value = [mock_item]

    with patch("app.subprocess.run", return_value=MagicMock(returncode=0)):
        wa._paste("new text")

    assert wa._pending_restore == [{"public.utf8-plain-text": b"previous text"}]


def test_paste_skips_types_with_no_data(wa):
    """_paste omits clipboard types whose dataForType_ returns falsy."""
    mock_item = MagicMock()
    mock_item.types.return_value = ["public.utf8-plain-text", "public.html"]

    def _data(t):
        return b"text" if t == "public.utf8-plain-text" else None

    mock_item.dataForType_.side_effect = _data

    mock_pb = wa._mock_appkit.NSPasteboard.generalPasteboard.return_value
    mock_pb.pasteboardItems.return_value = [mock_item]

    with patch("app.subprocess.run", return_value=MagicMock(returncode=0)):
        wa._paste("new text")

    assert wa._pending_restore == [{"public.utf8-plain-text": b"text"}]


def test_paste_skips_items_where_all_types_have_no_data(wa):
    """_paste skips entire clipboard items when all types have falsy data."""
    mock_item = MagicMock()
    mock_item.types.return_value = ["public.pdf"]
    mock_item.dataForType_.return_value = None

    mock_pb = wa._mock_appkit.NSPasteboard.generalPasteboard.return_value
    mock_pb.pasteboardItems.return_value = [mock_item]

    with patch("app.subprocess.run", return_value=MagicMock(returncode=0)):
        wa._paste("new text")

    assert wa._pending_restore == []


# ---------------------------------------------------------------------------
# _recopy
# ---------------------------------------------------------------------------


def test_recopy_calls_pbcopy_with_text(wa):
    with patch("app.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        wa._recopy("copied text")
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == ["pbcopy"]
    assert mock_run.call_args[1]["input"] == b"copied text"


# ---------------------------------------------------------------------------
# _set_model / _clear_history
# ---------------------------------------------------------------------------


def test_set_model_updates_config(wa):
    from config import MODELS

    new_model = MODELS[-1]
    with patch.object(wa.transcriber, "set_model"):
        wa._set_model(new_model)
    assert wa.config.model == new_model


def test_set_model_reloads_transcriber(wa):
    from config import MODELS

    with patch.object(wa.transcriber, "set_model") as mock_sm:
        wa._set_model(MODELS[0])
    mock_sm.assert_called_once_with(MODELS[0])


def test_set_model_updates_checkmarks(wa):
    from config import MODELS

    with patch.object(wa.transcriber, "set_model"):
        wa._set_model(MODELS[0])
    assert wa.model_items[MODELS[0]].title.startswith("✓")


def test_clear_history_sets_refresh_flag(wa):
    wa._needs_history_refresh = False
    wa._clear_history(None)
    assert wa._needs_history_refresh is True


def test_clear_history_empties_db(wa):
    wa.db.add("text", audio_ms=1000, model="base.en", latency_ms=800)
    wa._clear_history(None)
    assert wa.db.get_recent(10) == []


# ---------------------------------------------------------------------------
# Update flow
# ---------------------------------------------------------------------------


def test_update_action_starts_check_when_state_is_none(wa):
    wa._update_state = None
    with patch("app.threading.Timer", return_value=MagicMock()):
        with patch("app.threading.Thread") as mock_thread:
            wa._update_action(None)
    assert wa._update_state == "checking"
    mock_thread.assert_called()


def test_update_action_starts_check_when_state_is_zero(wa):
    wa._update_state = 0
    with patch("app.threading.Timer", return_value=MagicMock()):
        with patch("app.threading.Thread"):
            wa._update_action(None)
    assert wa._update_state == "checking"


def test_update_action_starts_check_when_state_is_error(wa):
    wa._update_state = "error"
    with patch("app.threading.Timer", return_value=MagicMock()):
        with patch("app.threading.Thread"):
            wa._update_action(None)
    assert wa._update_state == "checking"


def test_update_action_starts_install_when_updates_available(wa):
    wa._update_state = 3
    with patch("app.threading.Thread") as mock_thread:
        wa._update_action(None)
    assert wa._update_state == "installing"
    mock_thread.assert_called()


def test_update_action_noop_when_checking(wa):
    wa._update_state = "checking"
    with patch("app.threading.Thread") as mock_thread:
        wa._update_action(None)
    mock_thread.assert_not_called()


def test_update_action_noop_when_installing(wa):
    wa._update_state = "installing"
    with patch("app.threading.Thread") as mock_thread:
        wa._update_action(None)
    mock_thread.assert_not_called()


def test_unblock_menu_clears_check_active(wa):
    wa._menu_delegate._check_active = True
    wa._unblock_menu()
    assert wa._menu_delegate._check_active is False


def test_run_update_check_sets_count_on_success(wa):
    with patch("app.check_for_updates", return_value=5):
        with patch("app.threading.Timer", return_value=MagicMock()):
            wa._run_update_check()
    assert wa._update_state == 5


def test_run_update_check_sets_error_on_failure(wa):
    with patch("app.check_for_updates", return_value=-1):
        wa._run_update_check()
    assert wa._update_state == "error"


def test_run_update_check_zero_schedules_reset_timer(wa):
    with patch("app.check_for_updates", return_value=0):
        with patch("app.threading.Timer", return_value=MagicMock()) as mock_timer:
            wa._run_update_check()
    mock_timer.assert_called()


def test_run_update_check_nonzero_does_not_schedule_reset(wa):
    with patch("app.check_for_updates", return_value=2):
        with patch("app.threading.Timer", return_value=MagicMock()) as mock_timer:
            wa._run_update_check()
    mock_timer.assert_not_called()


def test_reset_update_state_clears_zero(wa):
    wa._update_state = 0
    wa._reset_update_state()
    assert wa._update_state is None


def test_reset_update_state_noop_when_not_zero(wa):
    wa._update_state = 5
    wa._reset_update_state()
    assert wa._update_state == 5


def test_run_install_sets_error_on_failure(wa):
    with patch("app.install_update", return_value=False):
        wa._run_install()
    assert wa._update_state == "error"


def test_run_install_success_launchctl_succeeds(wa):
    r = MagicMock()
    r.returncode = 0
    with patch("app.install_update", return_value=True):
        with patch.object(wa.hotkey, "stop"):
            with patch("app.subprocess.run", return_value=r):
                wa._run_install()
    assert wa._update_state == "restarting"


def test_run_install_success_launcher_exists(wa, tmp_app_dir):
    r_fail = MagicMock(returncode=1)
    launcher = tmp_app_dir.parent / "Wisper.app" / "Contents" / "MacOS" / "Wisper"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.touch()
    with patch("app.install_update", return_value=True):
        with patch.object(wa.hotkey, "stop"):
            with patch("app.subprocess.run", return_value=r_fail):
                with patch("app.subprocess.Popen") as mock_popen:
                    with patch("app.REPO_DIR", tmp_app_dir.parent):
                        wa._run_install()
    mock_popen.assert_called_once()
    assert wa._update_state == "restarting"


def test_run_install_success_launcher_missing_no_popen(wa, tmp_app_dir):
    r_fail = MagicMock(returncode=1)
    with patch("app.install_update", return_value=True):
        with patch.object(wa.hotkey, "stop"):
            with patch("app.subprocess.run", return_value=r_fail):
                with patch("app.subprocess.Popen") as mock_popen:
                    with patch("app.REPO_DIR", tmp_app_dir / "nonexistent"):
                        wa._run_install()
    mock_popen.assert_not_called()
    assert wa._update_state == "restarting"


# ---------------------------------------------------------------------------
# _quit
# ---------------------------------------------------------------------------


def test_quit_stops_hotkey(wa):
    with patch.object(wa.hotkey, "stop") as mock_stop:
        wa._quit(None)
    mock_stop.assert_called_once()


def test_quit_calls_quit_application(wa):
    wa._quit(None)
    wa._mock_quit.assert_called()
