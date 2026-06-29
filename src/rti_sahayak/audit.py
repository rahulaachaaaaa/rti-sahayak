"""Append-only audit log writer (spec s8 — the audit-first differentiator).

Writes every AuditEntry to an append-only JSONL sink (path via RTI_AUDIT_LOG) and keeps
the same rows in graph state so eval/invariants can read them without a sink. Mirroring
these rows into a UiPath Data Service `AuditLog` entity is planned (roadmap), not yet
wired here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config_loader import REPO_ROOT
from .state import new_audit

_SINK = Path(os.getenv("RTI_AUDIT_LOG", REPO_ROOT / "eval" / "_runs" / "audit.jsonl"))


def record(state_audit: list[dict], rti_id: str, actor: str, action: str, **details: Any) -> dict:
    """Append one entry to the in-state audit list AND the JSONL sink. Returns the entry.

    Caller is responsible for putting the returned entry into the node's state update
    (the graph reducer concatenates audit lists); we also persist immediately so a
    crash mid-run still leaves a trail.
    """
    entry = new_audit(rti_id, actor, action, **details)
    state_audit.append(entry)
    try:
        _SINK.parent.mkdir(parents=True, exist_ok=True)
        with open(_SINK, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # never let audit persistence crash the pipeline
    return entry


def reset_sink() -> None:
    """Clear the JSONL sink (eval harness calls this between cases)."""
    try:
        if _SINK.exists():
            _SINK.unlink()
    except OSError:
        pass
