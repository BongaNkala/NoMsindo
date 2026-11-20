"""Real-time voice isolation engine (RNNoise, 48 kHz, 10 ms frames)."""
from __future__ import annotations

import numpy as np
from . import rnnoise_lib as _rn

SAMPLE_RATE = 48000
FRAME = _rn.FRAME_SIZE  # 480 samples = 10 ms


class Denoiser:
    """Streaming denoiser. Accepts blocks of any size, returns the same size.

    Adds a fixed 10 ms of algorithmic latency (one RNNoise frame).
    mode 1 = Standard (one pass), mode 2 = Strong (two passes, more aggressive).
    strength 0..1 blends original (0) and cleaned (1) audio.
    """

    def __init__(self, strength: float = 1.0, mode: int = 1):
        self._states = [_rn.create(), _rn.create()]
        self.strength = float(strength)
        self.mode = int(mode)
        self._in = np.zeros(0, dtype=np.int16)
        self._out = np.zeros(FRAME, dtype=np.int16)  # priming = 10 ms
        self.speech_prob = 0.0

    def _frame(self, frame: np.ndarray) -> np.ndarray:
        wet = frame
        passes = 2 if self.mode >= 2 else 1
        probs = []
        for i in range(passes):
            wet, p = _rn.process_mono_frame(self._states[i], wet)
            probs.append(float(p))
        self.speech_prob = probs[0]
        s = min(max(self.strength, 0.0), 1.0)
        if s >= 0.999:
            return wet
        mixed = frame.astype(np.float32) * (1.0 - s) + wet.astype(np.float32) * s
        return np.clip(mixed, -32768, 32767).astype(np.int16)

    def process_int16(self, block: np.ndarray) -> np.ndarray:
        n = len(block)
        self._in = np.concatenate([self._in, block.astype(np.int16, copy=False)])
        outs = [self._out]
        while len(self._in) >= FRAME:
            outs.append(self._frame(self._in[:FRAME].copy()))
            self._in = self._in[FRAME:]
        joined = np.concatenate(outs)
        self._out = joined[n:]
        return joined[:n]

    def process(self, block: np.ndarray) -> np.ndarray:
        """float32 [-1, 1] in, float32 out."""
        pcm = np.clip(block * 32767.0, -32768, 32767).astype(np.int16)
        return self.process_int16(pcm).astype(np.float32) / 32767.0

    def close(self) -> None:
        for s in self._states:
            _rn.destroy(s)
        self._states = []


def process_array(audio: np.ndarray, strength: float = 1.0, mode: int = 1) -> np.ndarray:
    """Offline helper: float32 mono 48 kHz array -> cleaned array (latency compensated)."""
    d = Denoiser(strength, mode)
    pad = np.zeros(FRAME, dtype=np.float32)
    out = d.process(np.concatenate([audio.astype(np.float32), pad]))
    d.close()
    return out[FRAME:]
