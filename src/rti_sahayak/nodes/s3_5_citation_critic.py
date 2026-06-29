"""S3.5 Citation Critic — deterministic quote-verify + bounded self-repair (spec s5.1).

Every citation's `quote` must be verbatim text of the clause it cites (rag.quote_verify).
Fabricated/paraphrased citations fail regardless of model. On failure: route back to S3
for up to MAX_REPAIRS attempts; still failing -> abstain (drop the citation, lower
confidence) and escalate to a human.
"""
from __future__ import annotations

from ..audit import record
from ..rag import quote_verify
from ..state import RTIState

MAX_REPAIRS = 2


def s3_5_citation_critic(state: RTIState) -> dict:
    rti_id = state["rti_id"]
    dispositions = [dict(d) for d in state["dispositions"]]
    audit: list[dict] = []
    flags = list(state.get("flags", []))
    repair_count = state.get("repair_count_citation", 0)

    any_fail = False
    for d in dispositions:
        verified_cites = []
        for c in d.get("citations", []):
            ok = quote_verify(c.get("quote", ""), c.get("section", ""))
            c["verified"] = ok
            verified_cites.append(ok)
            record(audit, rti_id, "s3_5_citation_critic", "quote_verify",
                   item_id=d["item_id"], section=c.get("section"), verified=ok)
        if d.get("citations") and not all(verified_cites):
            any_fail = True

    if not any_fail:
        return {"dispositions": dispositions, "route_citation": "ok", "audit": audit}

    if repair_count < MAX_REPAIRS:
        record(audit, rti_id, "s3_5_citation_critic", "repair_requested",
               attempt=repair_count + 1, max=MAX_REPAIRS)
        return {
            "dispositions": dispositions,
            "repair_count_citation": repair_count + 1,
            "route_citation": "repair",
            "audit": audit,
        }

    # exhausted -> abstain on bad citations + escalate
    for d in dispositions:
        bad = [c for c in d.get("citations", []) if not c.get("verified")]
        if bad:
            d["citations"] = [c for c in d["citations"] if c.get("verified")]
            d["confidence"] = min(d.get("confidence", 0.0), 0.3)
            d["justification"] = (d.get("justification", "") +
                                  " [citation unverified after repairs; abstained]").strip()
    flags.append("citation_unverified")
    record(audit, rti_id, "s3_5_citation_critic", "escalate_unverified_citation",
           attempts=repair_count)
    return {
        "dispositions": dispositions, "flags": flags, "escalate": True,
        "route_citation": "escalate", "audit": audit,
    }
