import pytest

from nomsindo.devices import cable_id, is_virtual
from nomsindo.safety import check

A_IN, A_OUT = "CABLE-A Input (VB-Audio Cable A)", "CABLE-A Output (VB-Audio Cable A)"
B_IN, B_OUT = "CABLE-B Input (VB-Audio Cable B)", "CABLE-B Output (VB-Audio Cable B)"
ONE_IN, ONE_OUT = "CABLE Input (VB-Audio Virtual Cable)", "CABLE Output (VB-Audio Virtual Cable)"
MIC, HP = "Headset Microphone (Plantronics)", "Headset Earphone (Plantronics)"


def test_cable_ids():
    assert cable_id(A_IN) == cable_id(A_OUT) == "A" and cable_id(B_OUT) == "B"
    assert cable_id(ONE_IN) == cable_id(ONE_OUT) == ""
    assert cable_id(MIC) is None and cable_id(HP) is None
    assert cable_id("CABLE Output") == "" and cable_id("Speakers (Cable Delta)") == ""
    assert is_virtual(A_IN) and is_virtual("NoMsindo Microphone") and not is_virtual(HP)


def test_correct_ab_setup_is_ok():
    assert check("mic", MIC, A_IN, B_OUT, HP) is None
    assert check("speaker", B_OUT, HP, MIC, A_IN) is None


def test_mic_to_headphones_is_blocked():       # the exact setup from the first screenshot
    assert "hear yourself" in check("mic", MIC, HP, B_OUT, HP)


def test_speaker_path_from_microphone_is_blocked():
    assert "own voice" in check("speaker", MIC, HP, MIC, A_IN)


def test_same_cable_on_both_paths_is_blocked():
    msg = check("speaker", A_OUT, HP, MIC, A_IN)
    assert msg and "CABLE-A" in msg and "loop" in msg
    assert check("mic", MIC, A_IN, A_OUT, HP) is not None


def test_single_cable_for_both_paths_is_blocked():
    msg = check("speaker", ONE_OUT, HP, MIC, ONE_IN)
    assert msg and "A+B" in msg
