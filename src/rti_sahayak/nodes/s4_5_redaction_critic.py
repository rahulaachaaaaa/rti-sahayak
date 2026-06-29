"""S4.5 Redaction Critic — leak re-scan + bounded self-repair (spec s5.1).

Re-runs the deterministic tiers over each redacted record. Any surviving PII (a leak)
routes back to S4 for up to MAX_REPAIRS attempts; still leaking -> flag and escalate.
The leak check is deterministic, so the zero-leak invariant holds under either model.
"""
from __future__ import annotations

from ..audit import record
from ..redaction import leak_rescan
from ..state import RTIState

MAX_REPAIRS = 2


def s4_5_redaction_critic(state: RTIState) -> dict:
    rti_id = state["rti_id"]
    redacted = state.get("redacted_records", {})
    audit: list[dict] = []
    flags = list(state.get("flags", []))
    repair_count = state.get("repair_count_redaction", 0)

    leaks: dict[str, list[str]] = {}
    for record_id, text in redacted.items():
        found = leak_rescan(text)
        if found:
            leaks[record_id] = [s.text for s in found]
        record(audit, rti_id, "s4_5_redaction_critic", "leak_check",
               record_id=record_id, leak_count=len(found),
               pii_types=sorted({s.pii_type for s in found}))

    if not leaks:
        return {"route_redaction": "ok", "audit": audit}

    if repair_count < MAX_REPAIRS:
        record(audit, rti_id, "s4_5_redaction_critic", "repair_requested",
               attempt=repair_count + 1, max=MAX_REPAIRS, leaking_records=list(leaks))
        return {
            "repair_count_redaction": repair_count + 1,
            "route_redaction": "repair", "audit": audit,
        }

    flags.append("redaction_leak")
    record(audit, rti_id, "s4_5_redaction_critic", "escalate_leak",
           attempts=repair_count, leaking_records=list(leaks))
    return {"flags": flags, "escalate": True, "route_redaction": "escalate", "audit": audit}
