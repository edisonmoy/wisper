"""Tests for Transcriber — fully mocked faster_whisper, no model downloads."""

import sys
import time
from unittest.mock import MagicMock, patch

import numpy as np

from transcriber import Transcriber


class _Seg:
    """Minimal faster_whisper segment stand-in."""

    def __init__(self, text: str):
        self.text = text


def _mock_whisper(segments=None):
    """Return a WhisperModel mock whose transcribe() yields *segments*."""
    model = MagicMock()
    model.transcribe.return_value = (iter(segments or []), MagicMock())
    return model


def _patch_fw(model_instance):
    """Context manager: patch faster_whisper.WhisperModel to return *model_instance*."""
    fw = MagicMock()
    fw.WhisperModel = MagicMock(return_value=model_instance)
    return patch.dict(sys.modules, {"faster_whisper": fw})


# ---------------------------------------------------------------- lazy loading


def test_model_not_loaded_on_init():
    t = Transcriber("base.en")
    assert t._model is None


def test_model_loaded_on_first_transcribe():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("hello")])
    with _patch_fw(mock):
        t.transcribe(np.zeros(100, dtype="float32"))
    assert t._model is mock


def test_model_loaded_only_once_across_calls():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("hi")])
    fw = MagicMock()
    fw.WhisperModel = MagicMock(return_value=mock)
    with patch.dict(sys.modules, {"faster_whisper": fw}):
        t.transcribe(np.zeros(100, dtype="float32"))
        # Reload the mock's return iterable for second call
        mock.transcribe.return_value = (iter([_Seg("there")]), MagicMock())
        t.transcribe(np.zeros(100, dtype="float32"))
    fw.WhisperModel.assert_called_once()


def test_preload_loads_model_in_background():
    t = Transcriber("base.en")
    mock = _mock_whisper()
    with _patch_fw(mock):
        t.preload()
        # Give the daemon thread time to complete
        deadline = time.monotonic() + 2.0
        while t._model is None and time.monotonic() < deadline:
            time.sleep(0.01)
    assert t._model is mock


# ---------------------------------------------------------------- transcription


def test_single_segment_returned():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("hello world")])
    with _patch_fw(mock):
        result = t.transcribe(np.zeros(100, dtype="float32"))
    assert result == "hello world"


def test_multiple_segments_joined_with_space():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("hello"), _Seg("world")])
    with _patch_fw(mock):
        result = t.transcribe(np.zeros(100, dtype="float32"))
    assert result == "hello world"


def test_empty_segments_returns_empty_string():
    t = Transcriber("base.en")
    mock = _mock_whisper([])
    with _patch_fw(mock):
        result = t.transcribe(np.zeros(100, dtype="float32"))
    assert result == ""


def test_outer_whitespace_stripped():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("  hi  "), _Seg("  there  ")])
    with _patch_fw(mock):
        result = t.transcribe(np.zeros(100, dtype="float32"))
    assert result == result.strip()


# ---------------------------------------------------------------- language selection


def test_dot_en_model_passes_language_en():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("hi")])
    with _patch_fw(mock):
        t.transcribe(np.zeros(100, dtype="float32"))
    kwargs = mock.transcribe.call_args[1]
    assert kwargs["language"] == "en"


def test_multilingual_model_passes_language_none():
    t = Transcriber("large-v2")
    mock = _mock_whisper([_Seg("bonjour")])
    with _patch_fw(mock):
        t.transcribe(np.zeros(100, dtype="float32"))
    kwargs = mock.transcribe.call_args[1]
    assert kwargs["language"] is None


def test_distil_large_model_is_multilingual():
    """distil-large-v3 does not end in .en — should have language=None."""
    t = Transcriber("distil-large-v3")
    mock = _mock_whisper([_Seg("text")])
    with _patch_fw(mock):
        t.transcribe(np.zeros(100, dtype="float32"))
    kwargs = mock.transcribe.call_args[1]
    assert kwargs["language"] is None


# ---------------------------------------------------------------- set_model


def test_set_model_clears_cached_model():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("hi")])
    with _patch_fw(mock):
        t.transcribe(np.zeros(100, dtype="float32"))
    assert t._model is not None
    t.set_model("small.en")
    assert t._model is None


def test_set_model_updates_model_name():
    t = Transcriber("base.en")
    t.set_model("small.en")
    assert t.model_name == "small.en"


def test_set_model_loads_new_model_on_next_call():
    t = Transcriber("base.en")
    mock1 = _mock_whisper([_Seg("old")])
    mock2 = _mock_whisper([_Seg("new")])
    fw1 = MagicMock()
    fw1.WhisperModel = MagicMock(return_value=mock1)
    fw2 = MagicMock()
    fw2.WhisperModel = MagicMock(return_value=mock2)

    with patch.dict(sys.modules, {"faster_whisper": fw1}):
        t.transcribe(np.zeros(100, dtype="float32"))

    t.set_model("small.en")

    with patch.dict(sys.modules, {"faster_whisper": fw2}):
        result = t.transcribe(np.zeros(100, dtype="float32"))

    fw2.WhisperModel.assert_called_once_with("small.en", device="cpu", compute_type="int8")
    assert result == "new"


# ---------------------------------------------------------------- model init args


def test_model_created_with_cpu_and_int8():
    t = Transcriber("tiny.en")
    fw = MagicMock()
    fw.WhisperModel = MagicMock(return_value=_mock_whisper([]))
    with patch.dict(sys.modules, {"faster_whisper": fw}):
        t.transcribe(np.zeros(100, dtype="float32"))
    fw.WhisperModel.assert_called_once_with("tiny.en", device="cpu", compute_type="int8")


def test_vad_filter_enabled():
    t = Transcriber("base.en")
    mock = _mock_whisper([_Seg("text")])
    with _patch_fw(mock):
        t.transcribe(np.zeros(100, dtype="float32"))
    kwargs = mock.transcribe.call_args[1]
    assert kwargs.get("vad_filter") is True
