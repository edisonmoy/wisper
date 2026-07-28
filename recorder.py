import collections
import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000  # Hz — what Whisper expects
CHANNELS = 1
DTYPE = "float32"

WAVEFORM_BARS = 44  # RMS history length shown in the overlay


class AudioRecorder:
    def __init__(self):
        self._recording = False
        self._buffer: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self.device: str | None = None  # None = system default
        self._waveform: collections.deque = collections.deque(
            [0.0] * WAVEFORM_BARS, maxlen=WAVEFORM_BARS
        )

    @property
    def is_recording(self) -> bool:
        return self._recording

    def get_waveform(self) -> list[float]:
        return list(self._waveform)

    def start(self):
        import sounddevice as sd

        with self._lock:
            if self._recording:
                return
            self._buffer = []
            self._waveform = collections.deque([0.0] * WAVEFORM_BARS, maxlen=WAVEFORM_BARS)
            self._recording = True
            stream_kwargs = dict(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._callback,
                blocksize=1024,
                device=self.device,
            )
            try:
                self._stream = sd.InputStream(**stream_kwargs)
            except Exception:
                if self.device is None:
                    self._stream = _retry_after_rescan(sd, stream_kwargs)
                else:
                    logger.warning(
                        "Device %r unavailable; falling back to system default", self.device
                    )
                    stream_kwargs["device"] = None
                    try:
                        self._stream = sd.InputStream(**stream_kwargs)
                    except Exception:
                        self._stream = _retry_after_rescan(sd, stream_kwargs)
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
            rms = float(np.sqrt(np.mean(indata**2)))
            self._waveform.append(rms)

    def duration_ms(self) -> int:
        samples = sum(len(b) for b in self._buffer)
        return int(samples / SAMPLE_RATE * 1000)


def _retry_after_rescan(sd, stream_kwargs):
    """Retry opening the stream once after forcing PortAudio to rescan devices.

    PortAudio snapshots the CoreAudio device list once at startup and never
    notices devices connecting/disconnecting afterward (e.g. Bluetooth
    headphones going in and out of range). In a long-running process this
    makes an otherwise-fine device fail to open with a stale-property error.
    Re-initializing PortAudio forces it to pick up the current device list.
    """
    sd._terminate()
    sd._initialize()
    return sd.InputStream(**stream_kwargs)
