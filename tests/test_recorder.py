import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

from recorder import SAMPLE_RATE, WAVEFORM_BARS, AudioRecorder


@pytest.fixture
def recorder():
    return AudioRecorder()


def test_initial_waveform_all_zeros(recorder):
    wf = recorder.get_waveform()
    assert len(wf) == WAVEFORM_BARS
    assert all(v == 0.0 for v in wf)


def test_callback_appends_rms(recorder):
    recorder._recording = True
    chunk = np.full((1024, 1), 0.5, dtype="float32")
    recorder._callback(chunk, 1024, None, None)
    assert recorder.get_waveform()[-1] > 0


def test_callback_silent_chunk_appends_zero(recorder):
    recorder._recording = True
    chunk = np.zeros((1024, 1), dtype="float32")
    recorder._callback(chunk, 1024, None, None)
    assert recorder.get_waveform()[-1] == pytest.approx(0.0)


def test_callback_ignored_when_not_recording(recorder):
    recorder._recording = False
    chunk = np.ones((1024, 1), dtype="float32")
    recorder._callback(chunk, 1024, None, None)
    assert all(v == 0.0 for v in recorder.get_waveform())
    assert recorder._buffer == []


def test_waveform_resets_on_start(recorder):
    recorder._recording = True
    recorder._callback(np.ones((1024, 1), dtype="float32"), 1024, None, None)
    assert recorder.get_waveform()[-1] > 0

    mock_sd = MagicMock()
    mock_sd.InputStream.return_value = MagicMock()
    recorder._recording = False
    with _mock_sd(mock_sd):
        recorder.start()

    assert all(v == 0.0 for v in recorder.get_waveform())


def test_stop_without_start_returns_none(recorder):
    assert recorder.stop() is None


def test_stop_without_audio_returns_none(recorder):
    mock_sd = MagicMock()
    mock_sd.InputStream.return_value = MagicMock()
    with _mock_sd(mock_sd):
        recorder.start()
    result = recorder.stop()
    assert result is None


def test_stop_returns_concatenated_audio(recorder):
    recorder._recording = True
    chunk = np.ones((512, 1), dtype="float32")
    recorder._callback(chunk, 512, None, None)
    recorder._callback(chunk, 512, None, None)
    # _stream is None (no real sounddevice started); stop() skips stream teardown.
    result = recorder.stop()
    assert result is not None
    assert len(result) == 1024


def test_duration_ms_empty(recorder):
    assert recorder.duration_ms() == 0


def test_duration_ms_one_second(recorder):
    recorder._recording = True
    chunk = np.zeros((SAMPLE_RATE, 1), dtype="float32")
    recorder._callback(chunk, SAMPLE_RATE, None, None)
    assert recorder.duration_ms() == 1000


def test_waveform_maxlen_is_waveform_bars(recorder):
    recorder._recording = True
    # Feed more chunks than WAVEFORM_BARS
    chunk = np.ones((1024, 1), dtype="float32")
    for _ in range(WAVEFORM_BARS + 10):
        recorder._callback(chunk, 1024, None, None)
    assert len(recorder.get_waveform()) == WAVEFORM_BARS


def test_is_recording_property(recorder):
    assert recorder.is_recording is False
    recorder._recording = True
    assert recorder.is_recording is True


def test_start_while_already_recording_is_noop(recorder):
    """start() while already recording must not reset the buffer or re-open a stream."""
    recorder._recording = True
    chunk = np.ones((512, 1), dtype="float32")
    recorder._callback(chunk, 512, None, None)
    buffer_len = len(recorder._buffer)
    # sounddevice is imported at the top of start(); inject a mock so the
    # import succeeds on Linux CI where sounddevice is not installed.
    with _mock_sd(MagicMock()):
        recorder.start()  # returns early because _recording is already True
    assert len(recorder._buffer) == buffer_len


# ---------------------------------------------------------------------------
# helper


def _mock_sd(mock):
    """Inject a mock sounddevice into sys.modules for the duration of a with-block."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        sys.modules["sounddevice"] = mock
        try:
            yield
        finally:
            sys.modules.pop("sounddevice", None)

    return _ctx()
