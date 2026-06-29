"""S1 Intake/Classify — raw RTI text -> RTIRequest + tagged RequestedItems (+30d deadline)."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..audit import record
from ..models import invoke_structured
from ..state import RequestedItem, RTIState, deadline_from

_SYS = (
    "You are an intake clerk at an Indian police-station Public Information Officer (PIO) "
    "desk. Split a citizen's RTI (Right to Information Act 2005) request into discrete "
    "requested items. For each item set item_type to one of: fir_copy, charge_sheet, "
    "witness_statement, investigation_status, personnel_record, general_info, other. "
    "Give each item a short stable item_id like 'i1','i2'. Do not answer or judge "
    "exemptions; only segment and classify."
)


class _Items(__import__("pydantic").BaseModel):
    items: list[RequestedItem]


def s1_intake(state: RTIState) -> dict:
    rti_id = state["rti_id"]
    received = state["received_date"]
    audit: list[dict] = []

    parsed = invoke_structured(
        "intake_classify",
        _Items,
        [SystemMessage(_SYS), HumanMessage(state["request_text"])],
    )
    items = [i.model_dump() for i in parsed.items]
    deadline = deadline_from(received)

    record(audit, rti_id, "s1_intake", "classified",
           item_count=len(items), item_types=[i["item_type"] for i in items],
           received_date=received, deadline_date=deadline)

    return {
        "request": {
            "rti_id": rti_id, "received_date": received, "deadline_date": deadline,
            "items": items,
        },
        "items": items,
        "audit": audit,
        "flags": [],
        "repair_count_citation": 0,
        "repair_count_redaction": 0,
    }
