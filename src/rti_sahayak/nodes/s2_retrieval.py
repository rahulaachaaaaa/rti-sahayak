"""S2 Records Retrieval — load synthetic CCTNS records and match them to items.

Stands in for UiPath Document Understanding: instead of OCR/extraction we load
pre-extracted synthetic records from corpus/records/<records_ref>.json. Records are
matched to items strictly by item_type — a record nobody requested is not retrieved, and
an item with no matching record simply gets none (handled downstream as disclose/escalate).
"""
from __future__ import annotations

import json

from ..audit import record
from ..config_loader import REPO_ROOT
from ..state import RTIState

_RECORDS_DIR = REPO_ROOT / "corpus" / "records"


def _load_records(records_ref: str) -> list[dict]:
    path = _RECORDS_DIR / f"{records_ref}.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def s2_retrieval(state: RTIState) -> dict:
    rti_id = state["rti_id"]
    items = state["items"]
    ref = state.get("records_ref", rti_id)
    audit: list[dict] = []

    raw = _load_records(ref)
    by_type: dict[str, list[dict]] = {}
    for r in raw:
        by_type.setdefault(r.get("record_type", "other"), []).append(r)

    records: list[dict] = []
    for item in items:
        matched = by_type.get(item["item_type"], [])
        for r in matched:
            records.append({
                "record_id": r["record_id"],
                "item_id": item["item_id"],
                "record_type": r.get("record_type", "other"),
                "text": r["text"],
            })

    record(audit, rti_id, "s2_retrieval", "records_matched",
           records_ref=ref, record_count=len(records),
           record_ids=[r["record_id"] for r in records])

    out: dict = {"records": records, "audit": audit}
    if not records:
        # Nothing on file matches the request — a human must confirm "not held"
        # and issue the standard no-records reply (escalate-no-rule, spec s9).
        flags = list(state.get("flags", []))
        flags.append("no_records_found")
        record(audit, rti_id, "s2_retrieval", "escalate_no_records", requested_items=len(items))
        out["flags"] = flags
        out["escalate"] = True
    return out
