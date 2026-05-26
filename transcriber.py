import threading
import numpy as np


class Transcriber:
    def __init__(self, model_name: str = 'base.en'):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def preload(self):
        """Load model in background so first use isn't slow."""
        threading.Thread(target=self._ensure_loaded, daemon=True).start()

    def transcribe(self, audio: np.ndarray) -> str:
        self._ensure_loaded()
        # .en models only understand English; multilingual models auto-detect.
        language = 'en' if self.model_name.endswith('.en') else None
        segments, _ = self._model.transcribe(
            audio,
            language=language,
            vad_filter=True,
            vad_parameters={'min_silence_duration_ms': 300},
        )
        return ' '.join(seg.text for seg in segments).strip()

    def set_model(self, model_name: str):
        with self._lock:
            self.model_name = model_name
            self._model = None

    def _ensure_loaded(self):
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_name,
                device='cpu',
                compute_type='int8',
            )
