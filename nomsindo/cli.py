"""Offline tool: python -m nomsindo.cli in.wav out.wav [--strength 100] [--strong]"""
import argparse

import numpy as np
import soundfile as sf

from .engine import SAMPLE_RATE, process_array


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--strength", type=int, default=100)
    ap.add_argument("--strong", action="store_true")
    a = ap.parse_args()
    audio, sr = sf.read(a.src, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(sr, SAMPLE_RATE)
        mono = resample_poly(mono, SAMPLE_RATE // g, sr // g).astype(np.float32)
    out = process_array(mono, a.strength / 100.0, 2 if a.strong else 1)
    sf.write(a.dst, out, SAMPLE_RATE)
    print(f"wrote {a.dst}")


if __name__ == "__main__":
    main()
