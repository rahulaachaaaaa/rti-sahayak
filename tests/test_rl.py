"""Keyless, deterministic tests for the PIO-feedback threshold learner (rl.py).

Proves the bandit math without any LLM/API: reward mapping, case_type bucketing,
update direction, online convergence, bound-clipping (the safety property), and the
RTI_RL=off baseline pin.
"""
from __future__ import annotations

import pytest

from rti_sahayak import rl


# ---- case_type bucketing ----

@pytest.mark.parametrize("disps,escalate,expected", [
    ([{"disposition": "disclose"}], False, "disclose"),
    ([{"disposition": "exempt"}], False, "exempt"),
    ([{"disposition": "disclose"}, {"disposition": "exempt"}], False, "mixed"),
    ([{"disposition": "partial"}], False, "mixed"),
    ([], True, "escalate"),
    (None, False, "escalate"),
])
def test_case_type_of(disps, escalate, expected):
    assert rl.case_type_of(disps, escalate) == expected


# ---- reward mapping ----

def test_reward_auto_approved_unedited():
    assert rl.reward_of("auto", {"action": "approve"}) == 1.0


def test_reward_auto_approved_edited():
    assert rl.reward_of("auto", {"action": "approve", "edited_body": "x"}) == 0.0


def test_reward_auto_rejected():
    assert rl.reward_of("auto", {"action": "reject"}) == -1.0


def test_reward_defer_needless():
    assert rl.reward_of("defer", {"action": "approve"}) == -0.3


def test_reward_defer_justified():
    assert rl.reward_of("defer", {"action": "reject"}) == 0.3
    assert rl.reward_of("defer", {"action": "approve", "edited_body": "x"}) == 0.3


# ---- update direction ----

def test_auto_rejected_raises_tau(tmp_path):
    s = rl.PolicyStore(tmp_path / "p.json")
    before = s.threshold("mixed")
    s.update("mixed", confidence=0.6, action="auto", human_decision={"action": "reject"})
    assert s.threshold("mixed") > before  # stricter after a bad auto-draft


def test_needless_defer_lowers_tau(tmp_path):
    s = rl.PolicyStore(tmp_path / "p.json")
    before = s.threshold("disclose")
    s.update("disclose", confidence=0.5, action="defer", human_decision={"action": "approve"})
    assert s.threshold("disclose") < before  # more willing to auto after a needless defer


# ---- online convergence ----

def test_converges_to_defer_when_autos_rejected(tmp_path):
    """conf=0.6 always rejected -> tau climbs above 0.6 so those cases start deferring."""
    s = rl.PolicyStore(tmp_path / "p.json")
    for _ in range(50):
        tau = s.threshold("exempt")
        action = rl.decide(0.6, tau)
        s.update("exempt", confidence=0.6, action=action, human_decision={"action": "reject"})
    assert s.threshold("exempt") > 0.6
    assert rl.decide(0.6, s.threshold("exempt")) == "defer"


def test_converges_to_auto_when_defers_needless(tmp_path):
    """conf=0.5 always approved-unedited -> tau drops below 0.5 so those cases auto-draft."""
    s = rl.PolicyStore(tmp_path / "p.json")
    for _ in range(50):
        tau = s.threshold("disclose")
        action = rl.decide(0.5, tau)
        s.update("disclose", confidence=0.5, action=action, human_decision={"action": "approve"})
    assert s.threshold("disclose") < 0.5
    assert rl.decide(0.5, s.threshold("disclose")) == "auto"


# ---- safety: tau always bounded (an auto draft still always reaches S6) ----

def test_tau_clipped_high(tmp_path):
    s = rl.PolicyStore(tmp_path / "p.json")
    for _ in range(200):
        s.update("exempt", confidence=0.99, action="auto", human_decision={"action": "reject"})
    assert s.threshold("exempt") <= rl.TAU_MAX


def test_tau_clipped_low(tmp_path):
    s = rl.PolicyStore(tmp_path / "p.json")
    for _ in range(200):
        s.update("disclose", confidence=0.01, action="auto", human_decision={"action": "approve"})
    assert s.threshold("disclose") >= rl.TAU_MIN


# ---- RTI_RL toggle ----

def test_rl_off_pins_baseline(tmp_path, monkeypatch):
    s = rl.PolicyStore(tmp_path / "p.json")
    s.update("mixed", confidence=0.6, action="auto", human_decision={"action": "reject"})
    monkeypatch.setenv("RTI_RL", "off")
    assert s.threshold("mixed") == rl.BASELINE_TAU  # learned value ignored when disabled
    monkeypatch.setenv("RTI_RL", "on")
    assert s.threshold("mixed") != rl.BASELINE_TAU  # learned value back when enabled


def test_persistence_round_trip(tmp_path):
    p = tmp_path / "p.json"
    s1 = rl.PolicyStore(p)
    s1.update("exempt", confidence=0.7, action="auto", human_decision={"action": "reject"})
    learned = s1.threshold("exempt")
    s2 = rl.PolicyStore(p)  # fresh load from disk
    assert s2.threshold("exempt") == learned


def test_ingest_feedback_uses_state_fields(tmp_path):
    s = rl.PolicyStore(tmp_path / "p.json")
    state = {"rl_case_type": "exempt", "rl_action": "auto", "confidence": 0.6,
             "escalate": False, "dispositions": [{"disposition": "exempt"}]}
    change = rl.ingest_feedback(state, {"action": "reject"}, store=s)
    assert change["case_type"] == "exempt"
    assert change["new_tau"] > change["old_tau"]
    assert change["reward"] == -1.0
