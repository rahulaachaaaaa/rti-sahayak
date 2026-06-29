"""Tier-2 probabilistic quality metrics (spec s9), reported per model config.

Computed over a list of per-case run results. Each result is:
  {case, state, interrupted, latency_s, expected}
where `expected` is the case's expected block (dispositions/escalation/redactions).
"""
from __future__ import annotations

from typing import Any

from rti_sahayak.rag import quote_verify
from rti_sahayak.redaction import leak_rescan


def _disp_by_type(state: dict) -> dict[str, str]:
    """Map item_type -> disposition (cases key expectations by type, not model item_id)."""
    type_of = {i["item_id"]: i.get("item_type", "other") for i in state.get("items", [])}
    return {type_of.get(d["item_id"], "other"): d["disposition"]
            for d in state.get("dispositions", [])}


def citation_accuracy(results: list[dict]) -> float:
    ok = tot = 0
    for r in results:
        for d in r["state"].get("dispositions", []):
            for c in d.get("citations", []):
                tot += 1
                ok += 1 if quote_verify(c.get("quote", ""), c.get("section", "")) else 0
    return ok / tot if tot else 1.0


def citation_hallucination_rate(results: list[dict]) -> float:
    return round(1.0 - citation_accuracy(results), 4)


def leak_rate(results: list[dict]) -> float:
    leaked = total = 0
    for r in results:
        for _, text in r["state"].get("redacted_records", {}).items():
            total += 1
            leaked += 1 if leak_rescan(text) else 0
    return round(leaked / total, 4) if total else 0.0


def over_redaction_rate(results: list[dict]) -> float:
    """Fraction of redacted records whose redaction tokens exceed expected (utility loss)."""
    flagged = total = 0
    for r in results:
        exp = {x["record_id"]: x for x in (r.get("expected", {}).get("redactions") or [])}
        for rid, text in r["state"].get("redacted_records", {}).items():
            total += 1
            count = text.count("[REDACTED:")
            allowed = exp.get(rid, {}).get("max_spans")
            if allowed is not None and count > allowed:
                flagged += 1
    return round(flagged / total, 4) if total else 0.0


def escalation_precision_recall(results: list[dict]) -> tuple[float, float]:
    tp = fp = fn = 0
    for r in results:
        pred = bool(r["state"].get("escalate"))
        want = bool(r.get("expected", {}).get("escalation"))
        tp += pred and want
        fp += pred and not want
        fn += (not pred) and want
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    return round(prec, 4), round(rec, 4)


def disposition_accuracy(results: list[dict]) -> float:
    ok = tot = 0
    for r in results:
        got = _disp_by_type(r["state"])
        for item_type, want in (r.get("expected", {}).get("dispositions") or {}).items():
            tot += 1
            ok += 1 if got.get(item_type) == want else 0
    return round(ok / tot, 4) if tot else 1.0


def cross_model_disagreement_rate(results: list[dict]) -> float:
    n = sum(1 for r in results if "model_disagreement" in r["state"].get("flags", []))
    return round(n / len(results), 4) if results else 0.0


def avg_latency(results: list[dict]) -> float:
    lat = [r.get("latency_s", 0.0) for r in results]
    return round(sum(lat) / len(lat), 3) if lat else 0.0


def compute(results: list[dict]) -> dict[str, Any]:
    prec, rec = escalation_precision_recall(results)
    return {
        "disposition_accuracy": disposition_accuracy(results),
        "citation_accuracy": round(citation_accuracy(results), 4),
        "citation_hallucination_rate": citation_hallucination_rate(results),
        "leak_rate": leak_rate(results),
        "over_redaction_rate": over_redaction_rate(results),
        "escalation_precision": prec,
        "escalation_recall": rec,
        "cross_model_disagreement_rate": cross_model_disagreement_rate(results),
        "avg_latency_s": avg_latency(results),
    }
