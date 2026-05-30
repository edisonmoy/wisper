import time
from unittest.mock import MagicMock, patch

import pytest
from pynput import keyboard

from hotkey import _FN_VK, HotkeyManager, _is_fn

# ------------------------------------------------------------------ _is_fn


def test_is_fn_correct_vk():
    assert _is_fn(keyboard.KeyCode(vk=_FN_VK)) is True


def test_is_fn_wrong_vk():
    assert _is_fn(keyboard.KeyCode(vk=_FN_VK + 1)) is False


def test_is_fn_special_key():
    assert _is_fn(keyboard.Key.space) is False


def test_is_fn_regular_char():
    assert _is_fn(keyboard.KeyCode.from_char("a")) is False


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


def test_start_launches_listener(mgr):
    with patch("hotkey.keyboard.Listener") as MockListener:
        mock = MagicMock()
        MockListener.return_value = mock
        mgr.start()
        MockListener.assert_called_once()
        mock.start.assert_called_once()
        assert mock.daemon is True


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
