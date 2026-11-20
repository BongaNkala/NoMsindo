"""Minimal ctypes binding for the RNNoise shared library.

We load the library shipped inside the `pyrnnoise` wheel (Apache-2.0) directly, instead of
importing the package, so the installer does not have to bundle matplotlib/torch-style extras.
"""
from __future__ import annotations

import ctypes
import importlib.util
import os
import platform
import sys

import numpy as np

_NAME = {"Windows": "rnnoise.dll", "Darwin": "librnnoise.dylib"}.get(platform.system(), "librnnoise.so")


def _locate() -> str:
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(getattr(sys, "_MEIPASS", ""), "nomsindo", "lib", _NAME))
    spec = importlib.util.find_spec("pyrnnoise")
    for p in (spec.submodule_search_locations or []) if spec else []:
        cands.append(os.path.join(p, _NAME))
    cands.append(os.path.join(os.path.dirname(__file__), "lib", _NAME))
    for c in cands:
        if os.path.exists(c):
            return c
    raise OSError(f"RNNoise library not found. Looked in: {cands}")


LIB_PATH = _locate()
_lib = ctypes.CDLL(LIB_PATH)
_lib.rnnoise_create.argtypes = [ctypes.c_void_p]
_lib.rnnoise_create.restype = ctypes.c_void_p
_lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
_lib.rnnoise_get_frame_size.restype = ctypes.c_int
_lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                       ctypes.POINTER(ctypes.c_float)]
_lib.rnnoise_process_frame.restype = ctypes.c_float
FRAME_SIZE = _lib.rnnoise_get_frame_size()  # 480 @ 48 kHz


def create():
    return _lib.rnnoise_create(None)


def destroy(state) -> None:
    _lib.rnnoise_destroy(state)


def process_mono_frame(state, frame: np.ndarray):
    """int16 frame of FRAME_SIZE samples -> (int16 cleaned frame, speech probability)."""
    buf = frame.astype(np.float32)
    ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
    prob = _lib.rnnoise_process_frame(state, ptr, ptr)
    return np.clip(buf, -32768, 32767).astype(np.int16), float(prob)
