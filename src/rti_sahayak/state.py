"""Typed state + node I/O contracts threaded through the LangGraph graph (spec s5)."""
from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, Any, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Disposition = Literal["disclose", "exempt", "partial"]
ItemType = Literal[
    "fir_copy", "charge_sheet", "witness_statement", "investigation_status",
    "personnel_record", "general_info", "other",
]


# ---- structured contracts (LLM structured-output targets) ----

class RequestedItem(BaseModel):
    item_id: str
    text: str                                   # the citizen's phrasing of this ask
    item_type: ItemType = "other"


class RTIRequest(BaseModel):
    rti_id: str
    applicant_name: str = "Applicant"
    received_date: str                          # ISO yyyy-mm-dd
    deadline_date: str                          # received + 30 days (RTI Act s7(1))
    items: list[RequestedItem] = Field(default_factory=list)


class RecordFound(BaseModel):
    record_id: str
    item_id: str                                # which requested item it answers
    record_type: ItemType
    text: str                                   # extracted record text (synthetic CCTNS)


class Citation(BaseModel):
    section: str                                # e.g. "8(1)(h)"
    clause_id: str                              # corpus chunk id
    quote: str                                  # verbatim text the model claims is in the clause
    verified: Optional[bool] = None             # set by S3.5 quote-verify


class ItemDisposition(BaseModel):
    item_id: str
    disposition: Disposition
    exemption_clauses: list[str] = Field(default_factory=list)   # e.g. ["8(1)(h)"]
    justification: str = ""
    confidence: float = 0.0                     # 0..1
    citations: list[Citation] = Field(default_factory=list)


class Redaction(BaseModel):
    record_id: str
    span: str                                   # the exact text redacted
    tier: Literal["regex", "presidio", "llm"]
    pii_type: str                               # AADHAAR, PHONE, PERSON, ...
    exemption_clause: str = "8(1)(j)"           # default: personal information


class DraftResponse(BaseModel):
    rti_id: str
    body: str
    cited_sections: list[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    rti_id: str
    actor: str                                  # node name or "human"
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str                              # ISO 8601


# ---- the graph state ----

class RTIState(TypedDict, total=False):
    # input
    rti_id: str
    request_text: str
    received_date: str
    records_ref: str                            # corpus/records subdir or case id (which records to load)

    # progressive results
    request: dict                               # RTIRequest.model_dump()
    items: list[dict]                           # RequestedItem dumps
    records: list[dict]                         # RecordFound dumps
    dispositions: list[dict]                    # ItemDisposition dumps
    redactions: list[dict]                      # Redaction dumps
    redacted_records: dict[str, str]            # record_id -> redacted text
    draft: dict                                 # DraftResponse dump

    # control / agentic flow
    confidence: float
    rl_case_type: str                           # bandit state: disclose|exempt|mixed|escalate
    rl_tau: float                               # learned gate used at S5 (feedback attribution)
    rl_action: str                              # gate decision: "auto" | "defer"
    flags: list[str]                            # e.g. "model_disagreement", "low_confidence"
    repair_count_citation: int
    repair_count_redaction: int
    escalate: bool
    human_decision: dict                        # filled by S6 HITL

    # provenance — operator.add reducer so every node APPENDS (append-only trail)
    audit: Annotated[list[dict], operator.add]  # AuditEntry dumps
    messages: Annotated[list[AnyMessage], add_messages]


def new_audit(rti_id: str, actor: str, action: str, **details: Any) -> dict:
    from datetime import datetime, timezone
    return AuditEntry(
        rti_id=rti_id, actor=actor, action=action, details=details,
        timestamp=datetime.now(timezone.utc).isoformat(),
    ).model_dump()


def deadline_from(received: str) -> str:
    from datetime import timedelta
    d = date.fromisoformat(received)
    return (d + timedelta(days=30)).isoformat()
