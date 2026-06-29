"""S4 Severability/Redaction — tiered regex -> Presidio -> LLM over disclosable records.

Three-way severability (spec s5.1): only disclosable/partial records are redacted;
fully-exempt items are withheld whole. Each redacted span is logged with its exemption
clause (default s8(1)(j), personal information). The LLM tier catches contextual /
coreferenced PII the deterministic tiers miss; failures fall back to deterministic-only.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..audit import record
from ..models import get_llm
from ..redaction import Span, apply_spans, detect, redact_deterministic
from ..state import RTIState

_LLM_SYS = (
    "You find personal/contextual PII that regex and NER missed, for redaction under RTI "
    "Act s8(1)(j) and informant protection under s8(1)(g). Return each exact substring to "
    "redact, one per line, copied verbatim from the text (names, relational identifiers "
    "like 'her brother the constable', addresses, informant descriptors). No commentary."
)


def _llm_spans(text: str) -> list[Span]:
    try:
        llm = get_llm("redaction_llm")
        resp = llm.invoke([SystemMessage(_LLM_SYS), HumanMessage(text)])
        content = resp.content if hasattr(resp, "content") else str(resp)
    except Exception:
        return []
    spans: list[Span] = []
    for line in str(content).splitlines():
        frag = line.strip().lstrip("-*0123456789. ").strip()
        if len(frag) < 3:
            continue
        idx = text.find(frag)
        if idx >= 0:
            spans.append(Span(idx, idx + len(frag), frag, "PERSON_CONTEXT", "llm"))
    return spans


def s4_redaction(state: RTIState) -> dict:
    rti_id = state["rti_id"]
    records = state["records"]
    disp_by_item = {d["item_id"]: d for d in state["dispositions"]}
    audit: list[dict] = []
    redactions: list[dict] = []
    redacted_records: dict[str, str] = dict(state.get("redacted_records", {}))

    for r in records:
        d = disp_by_item.get(r["item_id"])
        disposition = d["disposition"] if d else "exempt"
        if disposition == "exempt":
            redacted_records[r["record_id"]] = "[WITHHELD IN FULL under " + \
                ", ".join(d.get("exemption_clauses", []) or ["s8"]) + "]"
            continue

        text = r["text"]
        from ..redaction import _dedupe
        spans = _dedupe(detect(text) + _llm_spans(text))  # regex + presidio + llm
        redacted = apply_spans(text, spans)
        # Deterministic fixpoint mop-up: redacting shifts NER context and can surface PII
        # the first pass missed. Loop the deterministic tiers until clean so the zero-leak
        # invariant (same leak_rescan) holds model-independently — not just best-effort.
        redacted, residual = redact_deterministic(redacted)
        spans += residual
        for s in spans:
            redactions.append({
                "record_id": r["record_id"], "span": s.text, "tier": s.tier,
                "pii_type": s.pii_type, "exemption_clause": "8(1)(j)",
            })
        redacted_records[r["record_id"]] = redacted
        record(audit, rti_id, "s4_redaction", "redacted",
               record_id=r["record_id"], disposition=disposition,
               span_count=len(spans), tiers=sorted({s.tier for s in spans}))

    return {"redactions": redactions, "redacted_records": redacted_records, "audit": audit}
