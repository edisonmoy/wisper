import threading
import numpy as np

SAMPLE_RATE = 16_000  # Hz — what Whisper expects
CHANNELS = 1
DTYPE = 'float32'


class AudioRecorder:
    def __init__(self):
        self._recording = False
        self._buffer: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self):
        import sounddevice as sd

        with self._lock:
            if self._recording:
                return
            self._buffer = []
            self._recording = True
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._callback,
                blocksize=1024,
            )
            self._stream.start()

    def stop(self) -> np.ndarray | None:
        with self._lock:
            if not self._recording:
                return None
            self._recording = False
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if not self._buffer:
                return None
            return np.concatenate(self._buffer).flatten()

    def _callback(self, indata, frames, time_info, status):
        if self._recording:
            self._buffer.append(indata.copy())

    def duration_ms(self) -> int:
        samples = sum(len(b) for b in self._buffer)
        return int(samples / SAMPLE_RATE * 1000)
