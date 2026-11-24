"""Routing safety checks that prevent audio feedback loops before they start."""
from __future__ import annotations

from .devices import cable_id, is_virtual


def _label(cid: str) -> str:
    return f"CABLE-{cid}" if cid else "the virtual cable"


def check(role: str, in_name: str, out_name: str, other_in: str, other_out: str) -> str | None:
    """Return a plain-language problem if this routing would cause feedback, else None.

    role "mic": voice path (real mic -> virtual cable). role "speaker": call-audio path (cable -> headphones).
    other_in / other_out: the device names currently selected on the opposite path.
    """
    if role == "mic":
        if not is_virtual(out_name):
            return ("This sends your microphone straight to your headphones or speakers, so you would hear yourself "
                    "and get feedback. Send the cleaned voice to a virtual cable input such as CABLE-A Input.")
        mic_out, spk_in = cable_id(out_name), cable_id(other_in)
    else:
        if not is_virtual(in_name):
            return ("The speaker path must take call audio from a virtual cable output such as CABLE-B Output. "
                    "Taking it from a microphone would play your own voice back to you.")
        mic_out, spk_in = cable_id(other_out), cable_id(in_name)
    if mic_out is not None and spk_in is not None and mic_out == spk_in:
        return (f"Both paths use {_label(mic_out)}, so your voice would loop back into your headphones. "
                "Use CABLE-A for the microphone path and CABLE-B for the speaker path "
                "(install the A+B cable pack if you only have one cable).")
    return None
