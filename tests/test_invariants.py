"""Tier-1 deterministic CI gate (spec s9). Runs WITHOUT any API key.

Exercises the four invariant functions and the seeded-fault guard proofs against crafted
fixtures, plus a structural check that the graph routes through the S6 HITL gate before
END. `pytest` returns non-zero on any failure — this is the gate referenced in §9.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

import invariants as inv          # noqa: E402
import run as harness             # noqa: E402
import yaml                       # noqa: E402
from rti_sahayak import rag, redaction  # noqa: E402


def _good_state() -> dict:
    g8h = rag.get_clause("8(1)(h)")
    return {
        "items": [{"item_id": "i1", "item_type": "investigation_status"}],
        "dispositions": [{
            "item_id": "i1", "disposition": "exempt", "exemption_clauses": ["8(1)(h)"],
            "citations": [{"section": "8(1)(h)", "quote": g8h.verbatim_text, "verified": True}],
            "confidence": 0.9,
        }],
        "redacted_records": {"INV-1": "Investigation is ongoing. [REDACTED:PHONE]"},
        "audit": [
            {"actor": "s1_intake", "action": "classified", "details": {}},
            {"actor": "s3_exemption", "action": "disposition", "details": {"item_id": "i1"}},
        ],
        "human_decision": {},
    }


# ---- deterministic guards ----

def test_quote_verify_true_for_verbatim():
    g = rag.get_clause("8(1)(g)")
    assert rag.quote_verify(g.verbatim_text, "8(1)(g)") is True


def test_quote_verify_false_for_fabricated():
    assert rag.quote_verify("the officer just prefers secrecy", "8(1)(z)") is False
    # right section, wrong (other-clause) quote -> still rejected
    g = rag.get_clause("8(1)(g)")
    assert rag.quote_verify(g.verbatim_text, "8(1)(h)") is False


def test_leak_rescan_catches_structured_pii():
    assert redaction.leak_rescan("call 9876543210, Aadhaar 5421 8830 1290")
    assert redaction.leak_rescan("nothing sensitive here") == []


def test_deterministic_redaction_reaches_fixpoint():
    """Redacting a span shifts NER context, so a single pass can SURFACE a new PII
    detection (here presidio tags 'Lane 4' as PERSON only once 'Malviya Nagar' beside
    it is replaced). The deterministic redactor must loop to a fixpoint so leak_rescan
    is empty — this is the model-independent guarantee the zero-PII-leak invariant rests
    on, and the bug the `mix` eval exposed."""
    text = ("Complainant: Mr. Anil Kumar Sharma, age 41, R/o H.No. 27, Lane 4, "
            "Malviya Nagar, New Delhi-110017, mobile 9876543210, Aadhaar 5421 8830 1290.")
    red, _ = redaction.redact_deterministic(text)
    assert redaction.leak_rescan(red) == []


# ---- the four invariants ----

def test_provenance_invariant():
    ok, _ = inv.provenance_exists(_good_state())
    assert ok
    bad = _good_state(); bad["audit"] = []
    assert inv.provenance_exists(bad)[0] is False


def test_citations_quote_verify_invariant():
    assert inv.citations_quote_verify(_good_state())[0] is True
    bad = _good_state()
    bad["dispositions"][0]["citations"][0]["quote"] = "made up text"
    assert inv.citations_quote_verify(bad)[0] is False


def test_pauses_at_hitl_invariant():
    assert inv.pauses_at_hitl(_good_state(), interrupted=True)[0] is True
    assert inv.pauses_at_hitl(_good_state(), interrupted=False)[0] is False


def test_zero_pii_leak_invariant():
    assert inv.zero_pii_leak(_good_state())[0] is True
    bad = _good_state()
    bad["redacted_records"]["INV-1"] = "Reach the IO at 9810098100."
    assert inv.zero_pii_leak(bad)[0] is False


# ---- seeded faults each trip their guard ----

def test_all_seeded_faults_trip_their_guard():
    for p in (ROOT / "eval" / "cases").glob("sf*.yaml"):
        case = yaml.safe_load(p.read_text())
        ok, why = harness.prove_seeded_fault(case)
        assert ok, f"{case['id']} did not trip {case['guard_targeted']}: {why}"


# ---- structural: HITL is on the path to END ----

def test_graph_routes_through_hitl():
    from rti_sahayak.graph import build_graph
    b = build_graph()
    assert "s6_approval" in b.nodes
