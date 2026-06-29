"""Tier-1 deterministic invariants (spec s9) — must be 100%, model-independent.

Pure functions over a run's audit trail + final state. They never call an LLM, so the
pytest gate (tests/test_invariants.py) runs in CI without any API key.

  1. provenance_exists       — every decision has an audit entry
  2. citations_quote_verify  — every citation's quote is verbatim s8 text (100%)
  3. pauses_at_hitl          — the graph paused at S6 (un-bypassable)
  4. zero_pii_leak           — no structured PII survives in any redacted record
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rti_sahayak.rag import quote_verify          # noqa: E402
from rti_sahayak.redaction import leak_rescan      # noqa: E402


def provenance_exists(state: dict) -> tuple[bool, str]:
    audit = state.get("audit", [])
    if not audit:
        return False, "audit trail is empty"
    actors = {a["actor"] for a in audit}
    for needed in ("s1_intake", "s3_exemption"):
        if needed not in actors:
            return False, f"no audit entry from {needed}"
    for d in state.get("dispositions", []):
        hit = any(a["actor"] == "s3_exemption" and a.get("details", {}).get("item_id") == d["item_id"]
                  for a in audit)
        if not hit:
            return False, f"disposition for {d['item_id']} has no provenance entry"
    return True, "ok"


def citations_quote_verify(state: dict) -> tuple[bool, str]:
    total = 0
    for d in state.get("dispositions", []):
        for c in d.get("citations", []):
            total += 1
            if not quote_verify(c.get("quote", ""), c.get("section", "")):
                return False, f"citation {c.get('section')} on {d['item_id']} fails quote-verify"
    return True, f"{total} citations verified"


def pauses_at_hitl(state: dict, *, interrupted: bool) -> tuple[bool, str]:
    if not interrupted:
        return False, "graph reached END without pausing at S6 HITL"
    if state.get("human_decision"):
        return False, "human_decision was set without a real pause"
    return True, "paused at S6"


def zero_pii_leak(state: dict) -> tuple[bool, str]:
    for rid, text in state.get("redacted_records", {}).items():
        leaks = leak_rescan(text)
        if leaks:
            kinds = sorted({s.pii_type for s in leaks})
            return False, f"PII leak in {rid}: {kinds}"
    return True, "no leaks"


INVARIANTS = ["provenance_exists", "citations_quote_verify", "pauses_at_hitl", "zero_pii_leak"]


def check_all(state: dict, *, interrupted: bool) -> dict[str, tuple[bool, str]]:
    return {
        "provenance_exists": provenance_exists(state),
        "citations_quote_verify": citations_quote_verify(state),
        "pauses_at_hitl": pauses_at_hitl(state, interrupted=interrupted),
        "zero_pii_leak": zero_pii_leak(state),
    }
