"""S6 PIO Approval — the un-bypassable HITL gate (spec s5, s7).

Raises a LangGraph interrupt carrying the evidence pack. In the deployed agent this maps
to a UiPath Action Center task via `interrupt(CreateEscalation(...))`; locally / in eval
it falls back to a plain `interrupt(payload)` so the pause is still observable. Either way
the graph CANNOT reach END without a human decision resuming it.

Verified against uipath 2.11 / uipath-langchain 0.13.11:
  from uipath.platform.common import CreateEscalation
  interrupt(CreateEscalation(app_name=..., title=..., data=...))
The Action Center app name/folder are set once the UiPath app exists (TODO at deploy).
"""
from __future__ import annotations

import os

from langgraph.types import interrupt

from ..audit import record
from ..state import RTIState

# Default: generic Action Center task (no Action App / App Studio needed). The evidence
# pack still renders and the task is approvable. Set RTI_APPROVAL_APP to bind the
# escalation to a published Action App instead (then RTI_APPROVAL_FOLDER applies).
APPROVAL_APP_NAME = os.getenv("RTI_APPROVAL_APP") or None
APPROVAL_FOLDER = os.getenv("RTI_APPROVAL_FOLDER", "Shared")


def _evidence_pack(state: RTIState) -> dict:
    return {
        "rti_id": state["rti_id"],
        "deadline_date": state.get("request", {}).get("deadline_date"),
        "confidence": round(state.get("confidence", 0.0), 3),
        "badge": "needs review" if state.get("escalate") else "clean — quick approve",
        "flags": state.get("flags", []),
        "dispositions": state.get("dispositions", []),
        "redacted_records": state.get("redacted_records", {}),
        "draft_body": state.get("draft", {}).get("body", ""),
        "cited_sections": state.get("draft", {}).get("cited_sections", []),
        "audit_len": len(state.get("audit", [])),
    }


def _raise_interrupt(pack: dict):
    """Action Center task if the UiPath runtime is present; else a plain interrupt.

    Creates a generic Action Center task by default (no Action App required). If
    RTI_APPROVAL_APP is set, binds the escalation to that published Action App instead.
    """
    try:
        from uipath.platform.common import CreateEscalation  # type: ignore
        kwargs: dict = {
            "title": f"RTI {pack['rti_id']} — PIO approval required ({pack['badge']})",
            "data": pack,
        }
        if APPROVAL_APP_NAME:
            kwargs["app_name"] = APPROVAL_APP_NAME
            kwargs["app_folder_path"] = APPROVAL_FOLDER
        return interrupt(CreateEscalation(**kwargs))
    except Exception:
        # local / eval: no uipath runtime — still pause for a human
        return interrupt({"type": "pio_approval", "evidence": pack})


def s6_approval(state: RTIState) -> dict:
    rti_id = state["rti_id"]
    audit: list[dict] = []
    pack = _evidence_pack(state)

    record(audit, rti_id, "s6_approval", "awaiting_human",
           badge=pack["badge"], confidence=pack["confidence"], flags=pack["flags"])

    # Blocks here until a human resumes the graph with their decision.
    resume = _raise_interrupt(pack)

    decision = resume if isinstance(resume, dict) else {"action": str(resume)}
    action = decision.get("action") or decision.get("outcome") or "approve"
    record(audit, rti_id, "human", "decision", outcome=action,
           edited=bool(decision.get("edited_body")))

    final_body = decision.get("edited_body") or state.get("draft", {}).get("body", "")
    return {
        "human_decision": {"action": action, **decision},
        "draft": {**state.get("draft", {}), "body": final_body},
        "audit": audit,
    }
