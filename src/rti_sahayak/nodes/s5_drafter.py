"""S5 Response Drafter — compose the PIO reply + compute the confidence risk-gate.

Drafts only from verified citations and redacted record text (spec s5). Confidence is a
function of item confidences, critic outcomes, and flags; it sets the review badge and
can escalate, but NEVER auto-sends — a human always approves at S6.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from .. import rl
from ..audit import record
from ..models import get_llm
from ..state import DraftResponse, RTIState

_SYS = (
    "You are a police-station PIO drafting a reply to a citizen's RTI request under the "
    "Right to Information Act 2005. Be factual and courteous. For each item state whether "
    "it is disclosed, withheld, or partially disclosed, and when withheld/partial cite the "
    "exact s8 clause given to you. Use ONLY the provided (already-redacted) record text and "
    "the provided verified citations. Mention the applicant's right to first appeal under "
    "s19. Do not reveal any redacted content."
)


def _compute_confidence(state: RTIState, dispositions: list[dict]) -> float:
    if not dispositions:
        return 0.0
    base = sum(d.get("confidence", 0.0) for d in dispositions) / len(dispositions)
    flags = set(state.get("flags", []))
    penalty = 0.0
    if "model_disagreement" in flags:
        penalty += 0.4
    if "citation_unverified" in flags:
        penalty += 0.3
    if "redaction_leak" in flags:
        penalty += 0.5
    return max(0.0, min(1.0, base - penalty))


def s5_drafter(state: RTIState) -> dict:
    rti_id = state["rti_id"]
    dispositions = state["dispositions"]
    redacted = state.get("redacted_records", {})
    audit: list[dict] = []

    confidence = _compute_confidence(state, dispositions)
    # RL gate: per-case-type threshold learned from PIO feedback (seeded at 0.55 baseline).
    # This only decides auto-draft vs defer — S6 HITL still always runs.
    case_type = rl.case_type_of(dispositions, state.get("escalate", False))
    tau = rl.PolicyStore().threshold(case_type)
    action = rl.decide(confidence, tau)
    badge = "clean — quick approve" if action == "auto" else "needs review"
    escalate = state.get("escalate", False) or action == "defer"
    flags = list(state.get("flags", []))
    if action == "defer" and "low_confidence" not in flags:
        flags.append("low_confidence")

    lines = []
    cited_sections: list[str] = []
    for d in dispositions:
        secs = [c["section"] for c in d.get("citations", []) if c.get("verified")]
        cited_sections += secs
        lines.append(
            f"- item {d['item_id']}: {d['disposition']} "
            f"(s8: {', '.join(d.get('exemption_clauses', [])) or 'n/a'}) — {d.get('justification','')}"
        )
    redacted_block = "\n---\n".join(f"[{rid}]\n{txt}" for rid, txt in redacted.items())
    msg = (
        f"RTI {rti_id}. Dispositions:\n" + "\n".join(lines) +
        f"\n\nREDACTED RECORD TEXT (safe to quote):\n{redacted_block}"
    )

    try:
        llm = get_llm("response_drafter")
        resp = llm.invoke([SystemMessage(_SYS), HumanMessage(msg)])
        body = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as exc:  # draft is recoverable; keep the pipeline alive for HITL
        body = f"[draft generation failed: {exc}] Dispositions:\n" + "\n".join(lines)

    draft = DraftResponse(
        rti_id=rti_id, body=str(body), cited_sections=sorted(set(cited_sections)),
    ).model_dump()

    record(audit, rti_id, "s5_drafter", "draft_produced",
           confidence=round(confidence, 3), badge=badge, escalate=escalate,
           rl_case_type=case_type, rl_tau=round(tau, 3), rl_action=action,
           cited_sections=draft["cited_sections"])

    return {
        "draft": draft, "confidence": confidence, "flags": flags,
        "escalate": escalate, "audit": audit,
        "rl_case_type": case_type, "rl_tau": tau, "rl_action": action,
    }
