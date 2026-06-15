import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from pynput import keyboard

from hotkey import _FN_VK, HotkeyManager, _is_fn, _is_named_key, key_display_name

# ------------------------------------------------------------------ _is_fn


def test_is_fn_correct_vk():
    assert _is_fn(keyboard.KeyCode(vk=_FN_VK)) is True


def test_is_fn_wrong_vk():
    assert _is_fn(keyboard.KeyCode(vk=_FN_VK + 1)) is False


def test_is_fn_special_key():
    assert _is_fn(keyboard.Key.space) is False


def test_is_fn_regular_char():
    assert _is_fn(keyboard.KeyCode.from_char("a")) is False


# ------------------------------------------------------------------ key_display_name


def test_display_name_default_fn():
    assert key_display_name(63, "") == "fn"


def test_display_name_unknown_vk():
    assert key_display_name(999, "") == "VK 999"


def test_display_name_named_key_known():
    assert key_display_name(63, "alt_r") == "Right ⌥"


def test_display_name_named_key_fkey():
    assert key_display_name(63, "f13") == "F13"


def test_display_name_named_key_unknown():
    assert key_display_name(63, "some_weird_key") == "some_weird_key"


# ------------------------------------------------------------------ toggle logic


@pytest.fixture
def mgr():
    return HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())


FN = keyboard.KeyCode(vk=_FN_VK)


def test_first_tap_calls_on_start(mgr):
    mgr._on_release(FN)
    time.sleep(0.05)
    mgr.on_start.assert_called_once()
    mgr.on_stop.assert_not_called()


def test_second_tap_calls_on_stop(mgr):
    mgr._on_release(FN)
    time.sleep(0.15)  # wait past debounce window
    mgr._on_release(FN)
    time.sleep(0.05)
    mgr.on_start.assert_called_once()
    mgr.on_stop.assert_called_once()


def test_third_tap_starts_again(mgr):
    mgr._on_release(FN)
    time.sleep(0.15)
    mgr._on_release(FN)
    time.sleep(0.15)
    mgr._on_release(FN)
    time.sleep(0.05)
    assert mgr.on_start.call_count == 2
    assert mgr.on_stop.call_count == 1


def test_non_fn_key_ignored(mgr):
    mgr._on_release(keyboard.Key.space)
    time.sleep(0.05)
    mgr.on_start.assert_not_called()


def test_recording_state_toggles(mgr):
    assert mgr._recording is False
    mgr._on_release(FN)
    time.sleep(0.15)
    assert mgr._recording is True
    mgr._on_release(FN)
    time.sleep(0.05)
    assert mgr._recording is False


# ------------------------------------------------------------------ start / stop


def test_start_launches_listener_toggle_mode(mgr):
    """Toggle-mode (Fn key) listener is started with only on_release."""
    with patch("hotkey.keyboard.Listener") as MockListener:
        mock = MagicMock()
        MockListener.return_value = mock
        mgr.start()
        _, kwargs = MockListener.call_args
        assert "on_release" in kwargs
        assert "on_press" not in kwargs
        mock.start.assert_called_once()
        assert mock.daemon is True


def test_start_launches_listener_push_to_talk_mode():
    """Push-to-talk listener is started with both on_press and on_release."""
    ptt = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock(), key_name="alt_r")
    with patch("hotkey.keyboard.Listener") as MockListener:
        mock = MagicMock()
        MockListener.return_value = mock
        ptt.start()
        _, kwargs = MockListener.call_args
        assert "on_press" in kwargs
        assert "on_release" in kwargs


def test_stop_halts_listener(mgr):
    with patch("hotkey.keyboard.Listener") as MockListener:
        mock = MagicMock()
        MockListener.return_value = mock
        mgr.start()
        mgr.stop()
        mock.stop.assert_called_once()
        assert mgr._listener is None


def test_stop_without_start_is_safe(mgr):
    mgr.stop()  # should not raise


# ------------------------------------------------------------------ robustness


def test_busy_cleared_even_if_on_start_raises(mgr):
    mgr.on_start.side_effect = RuntimeError("mic failed")
    mgr._on_release(FN)
    time.sleep(0.15)
    assert mgr._busy is False
    assert mgr._recording is False  # rolled back on exception


def test_busy_cleared_even_if_on_stop_raises(mgr):
    mgr._on_release(FN)
    time.sleep(0.15)
    mgr.on_stop.side_effect = RuntimeError("stop failed")
    mgr._on_release(FN)
    time.sleep(0.15)
    assert mgr._busy is False


def test_force_reset_clears_state(mgr):
    mgr._on_release(FN)
    time.sleep(0.05)
    assert mgr._recording is True
    mgr.force_reset()
    assert mgr._recording is False
    assert mgr._busy is False


def test_rapid_taps_debounced(mgr):
    # Two taps within debounce window — only first should register
    mgr._on_release(FN)
    mgr._on_release(FN)  # within 0.1s → ignored
    time.sleep(0.05)
    assert mgr.on_start.call_count == 1
    assert mgr.on_stop.call_count == 0


def test_busy_flag_blocks_release(mgr):
    """_on_release is a no-op when _busy is True (previous toggle still in flight)."""
    mgr._busy = True
    mgr._last_event = 0.0  # old enough that debounce would not fire
    mgr._on_release(FN)
    time.sleep(0.05)
    mgr.on_start.assert_not_called()


# ------------------------------------------------------------------ push-to-talk


@pytest.fixture
def ptt():
    """HotkeyManager in push-to-talk mode (non-Fn key)."""
    return HotkeyManager(on_start=MagicMock(), on_stop=MagicMock(), key_name="alt_r")


ALT_R = keyboard.Key.alt_r


def test_ptt_press_starts_recording(ptt):
    ptt._on_press(ALT_R)
    time.sleep(0.05)
    ptt.on_start.assert_called_once()
    ptt.on_stop.assert_not_called()


def test_ptt_release_stops_recording(ptt):
    ptt._on_press(ALT_R)
    time.sleep(0.05)
    ptt._on_release(ALT_R)
    time.sleep(0.05)
    ptt.on_stop.assert_called_once()


def test_ptt_release_without_press_is_noop(ptt):
    ptt._on_release(ALT_R)
    time.sleep(0.05)
    ptt.on_stop.assert_not_called()


def test_ptt_double_press_ignored(ptt):
    ptt._on_press(ALT_R)
    time.sleep(0.05)
    ptt._on_press(ALT_R)  # already recording
    time.sleep(0.05)
    assert ptt.on_start.call_count == 1


def test_ptt_non_matching_key_ignored(ptt):
    ptt._on_press(keyboard.Key.space)
    time.sleep(0.05)
    ptt.on_start.assert_not_called()


def test_ptt_on_stop_exception_is_swallowed(ptt):
    """on_stop raising in push-to-talk release must not propagate."""
    ptt.on_stop.side_effect = RuntimeError("stop failed")
    ptt._on_press(ALT_R)
    time.sleep(0.05)
    ptt._on_release(ALT_R)
    time.sleep(0.05)
    assert ptt._recording is False


def test_is_named_key_unknown_name_returns_false():
    """_is_named_key returns False when the Key attribute doesn't exist."""
    key = keyboard.Key.space
    assert _is_named_key(key, "nonexistent_key_xyz") is False


# ------------------------------------------------------------------ is_recording property


def test_is_recording_initially_false():
    mgr = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())
    assert mgr.is_recording is False


def test_is_recording_reflects_internal_state():
    mgr = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())
    mgr._recording = True
    assert mgr.is_recording is True
    mgr._recording = False
    assert mgr.is_recording is False


# ------------------------------------------------------------------ _dispatch helper


def test_dispatch_runs_fn():
    mgr = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())
    done = threading.Event()
    mgr._dispatch(lambda: done.set())
    assert done.wait(timeout=1)


def test_dispatch_clears_busy_by_default():
    mgr = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())
    mgr._busy = True
    done = threading.Event()
    mgr._dispatch(lambda: done.set())
    done.wait(timeout=1)
    time.sleep(0.05)
    assert mgr._busy is False


def test_dispatch_does_not_clear_busy_when_disabled():
    mgr = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())
    mgr._busy = True
    done = threading.Event()
    mgr._dispatch(lambda: done.set(), clear_busy=False)
    done.wait(timeout=1)
    time.sleep(0.05)
    assert mgr._busy is True


def test_dispatch_rolls_back_recording_on_error():
    mgr = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())
    mgr._recording = True
    done = threading.Event()

    def _raise():
        done.set()
        raise RuntimeError("boom")

    mgr._dispatch(_raise, rollback_recording=True)
    done.wait(timeout=1)
    time.sleep(0.05)
    assert mgr._recording is False


def test_dispatch_does_not_rollback_recording_when_disabled():
    mgr = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock())
    mgr._recording = True
    done = threading.Event()

    def _raise():
        done.set()
        raise RuntimeError("boom")

    mgr._dispatch(_raise, rollback_recording=False)
    done.wait(timeout=1)
    time.sleep(0.05)
    assert mgr._recording is True


def test_ptt_toggle_mode_false_for_named_key(ptt):
    assert ptt._toggle_mode is False


def test_toggle_mode_true_for_fn_key(mgr):
    assert mgr._toggle_mode is True


def test_toggle_mode_false_for_custom_vk():
    m = HotkeyManager(on_start=MagicMock(), on_stop=MagicMock(), vk=61)
    assert m._toggle_mode is False


def test_ptt_on_start_exception_rolls_back_recording(ptt):
    ptt.on_start.side_effect = RuntimeError("mic fail")
    ptt._on_press(ALT_R)
    time.sleep(0.15)
    assert ptt._recording is False
    assert ptt._busy is False
