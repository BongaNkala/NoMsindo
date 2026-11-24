"""input device -> denoiser -> output device, as two PortAudio streams with a jitter buffer."""
from __future__ import annotations

import threading

import numpy as np

from .engine import FRAME, SAMPLE_RATE, Denoiser


class RingBuffer:
    def __init__(self, capacity: int):
        self.buf = np.zeros(capacity, dtype=np.float32)
        self.cap = capacity
        self.r = self.w = self.n = 0
        self.lock = threading.Lock()

    def write(self, x: np.ndarray) -> None:
        with self.lock:
            if len(x) > self.cap:
                x = x[-self.cap:]
            drop = max(0, self.n + len(x) - self.cap)
            if drop:  # overflow: drop oldest audio
                self.r = (self.r + drop) % self.cap
                self.n -= drop
            idx = (self.w + np.arange(len(x))) % self.cap
            self.buf[idx] = x
            self.w = (self.w + len(x)) % self.cap
            self.n += len(x)

    def read(self, count: int) -> np.ndarray:
        with self.lock:
            take = min(count, self.n)
            idx = (self.r + np.arange(take)) % self.cap
            out = np.zeros(count, dtype=np.float32)
            out[:take] = self.buf[idx]
            self.r = (self.r + take) % self.cap
            self.n -= take
            return out

    def available(self) -> int:
        return self.n

    def trim_to(self, keep: int) -> None:
        with self.lock:
            if self.n > keep:
                skip = self.n - keep
                self.r = (self.r + skip) % self.cap
                self.n = keep


def _db(x: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(x)) + 1e-12))
    return 20.0 * np.log10(rms + 1e-9)


class Pipeline:
    PREFILL = FRAME * 3        # 30 ms
    MAX_LATENCY = FRAME * 10   # 100 ms, trim beyond this (clock drift)

    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.denoiser = Denoiser()
        self.ring = RingBuffer(SAMPLE_RATE)  # 1 s
        self.level_in_db = -90.0
        self.level_out_db = -90.0
        self.status = "stopped"
        self._in = None
        self._out = None
        self._primed = False
        self._pk_in = 0.0
        self._pk_out = 0.0

    @property
    def speech_prob(self) -> float:
        return self.denoiser.speech_prob if self.status == "running" else 0.0

    def take_peaks(self):
        """Peak amplitudes (0..1) since the last call, for the waveform display."""
        a, b = self._pk_in, self._pk_out
        self._pk_in = self._pk_out = 0.0
        return a, b

    # live settings
    def set_strength(self, v: float) -> None:
        self.denoiser.strength = v

    def set_mode(self, m: int) -> None:
        self.denoiser.mode = m

    def _settings(self, dev_index: int):
        import sounddevice as sd
        try:
            api = sd.query_hostapis(sd.query_devices(dev_index)["hostapi"])["name"]
            if "WASAPI" in api:
                return sd.WasapiSettings(auto_convert=True)
        except Exception:
            pass
        return None

    def _in_cb(self, indata, frames, time, status):
        mono = indata[:, 0].copy()
        out = self.denoiser.process(mono) if self.enabled else mono
        self.level_in_db = _db(mono)
        self.level_out_db = _db(out)
        self._pk_in = max(self._pk_in, float(np.max(np.abs(mono))))
        self._pk_out = max(self._pk_out, float(np.max(np.abs(out))))
        self.ring.write(out)

    def _out_cb(self, outdata, frames, time, status):
        if not self._primed:
            if self.ring.available() < self.PREFILL:
                outdata.fill(0)
                return
            self._primed = True
        if self.ring.available() > self.MAX_LATENCY:
            self.ring.trim_to(self.PREFILL)
        chunk = self.ring.read(frames)
        if self.ring.available() == 0 and not chunk.any():
            self._primed = False
        outdata[:] = chunk[:, None]

    def start(self, in_index: int, out_index: int) -> None:
        import sounddevice as sd
        self.stop()
        self.denoiser = Denoiser(self.denoiser.strength, self.denoiser.mode)
        self.ring = RingBuffer(SAMPLE_RATE)
        self._primed = False
        try:
            self._in = sd.InputStream(
                device=in_index, samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=FRAME, callback=self._in_cb, extra_settings=self._settings(in_index))
            self._out = sd.OutputStream(
                device=out_index, samplerate=SAMPLE_RATE, channels=2, dtype="float32",
                blocksize=FRAME, callback=self._out_cb, extra_settings=self._settings(out_index))
            self._out.start()
            self._in.start()
            self.status = "running"
        except Exception as e:  # surfaced in the UI
            self.stop()
            self.status = f"error: {e}"

    def stop(self) -> None:
        for s in (self._in, self._out):
            if s is not None:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass
        self._in = self._out = None
        if self.status == "running":
            self.status = "stopped"
        self.level_in_db = self.level_out_db = -90.0
