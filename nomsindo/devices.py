"""Audio device discovery. Prefers WASAPI on Windows to avoid duplicate entries."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Device:
    index: int
    name: str
    hostapi: str
    max_in: int
    max_out: int


def _sd():
    import sounddevice as sd  # imported lazily so the engine works without PortAudio
    return sd


def list_devices() -> list[Device]:
    sd = _sd()
    apis = [a["name"] for a in sd.query_hostapis()]
    devs = [Device(i, d["name"], apis[d["hostapi"]], d["max_input_channels"],
                   d["max_output_channels"]) for i, d in enumerate(sd.query_devices())]
    preferred = next((a for a in apis if "WASAPI" in a), None)
    if preferred:
        wasapi = [d for d in devs if d.hostapi == preferred]
        if wasapi:
            return wasapi
    return devs


def inputs() -> list[Device]:
    return [d for d in list_devices() if d.max_in > 0]


def outputs() -> list[Device]:
    return [d for d in list_devices() if d.max_out > 0]


def find(devs: list[Device], *needles: str) -> Device | None:
    for n in needles:
        for d in devs:
            if n.lower() in d.name.lower():
                return d
    return None


def default_device(kind: str) -> Device | None:
    sd = _sd()
    idx = sd.default.device[0 if kind == "input" else 1]
    pool = inputs() if kind == "input" else outputs()
    return next((d for d in pool if d.index == idx), pool[0] if pool else None)


def virtual_cable_present() -> bool:
    return find(outputs(), "CABLE Input", "CABLE-A Input", "VB-Audio") is not None


_CABLE = re.compile(r"cable(?:[- ]([a-d])(?![a-z0-9]))?", re.I)


def cable_id(name: str) -> str | None:
    """None = not a VB cable; "" = the single unnamed cable; "A"/"B"/... = that cable.
    Both ends of one cable (CABLE-A Input / CABLE-A Output) return the same id."""
    m = _CABLE.search(name or "")
    return None if not m else (m.group(1) or "").upper()


def is_virtual(name: str) -> bool:
    n = (name or "").lower()
    return cable_id(name) is not None or any(k in n for k in ("vb-audio", "voicemeeter", "virtual", "nomsindo"))
