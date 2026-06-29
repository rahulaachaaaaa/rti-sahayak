"""RAG grounding in RTI Act s8 (spec s6).

Clause-chunked local store over corpus/rti_act_s8.jsonl. Default retriever is a
dependency-light lexical scorer (BM25-lite) so the store is fully local, deterministic,
and needs no embedding API/auth — the "fast, model-agnostic default" the spec calls for.
(FAISS + gateway embeddings is the optional upgrade if time allows.)

The deterministic guard `quote_verify` is what catches fabricated citations regardless
of model: the cited verbatim text must actually be a substring of the clause it cites.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config_loader import REPO_ROOT

CORPUS_PATH = REPO_ROOT / "corpus" / "rti_act_s8.jsonl"

_WORD = re.compile(r"[a-z0-9]+")


def _norm(text: str) -> str:
    """Lowercase + collapse all non-alphanumeric runs to single spaces."""
    return " ".join(_WORD.findall(text.lower()))


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass
class Clause:
    section: str          # "8(1)(h)"
    clause_id: str        # "s8_1_h"
    verbatim_text: str
    norm_text: str        # normalized, for substring quote-verify


@lru_cache(maxsize=1)
def _load() -> list[Clause]:
    clauses: list[Clause] = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            clauses.append(
                Clause(
                    section=d["section"],
                    clause_id=d["clause_id"],
                    verbatim_text=d["verbatim_text"],
                    norm_text=_norm(d["verbatim_text"]),
                )
            )
    return clauses


@lru_cache(maxsize=1)
def _idf() -> dict[str, float]:
    clauses = _load()
    n = len(clauses)
    df: dict[str, int] = {}
    for c in clauses:
        for t in set(_tokens(c.verbatim_text + " " + c.section)):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((n - d + 0.5) / (d + 0.5) + 1.0) for t, d in df.items()}


def retrieve(query: str, k: int = 4) -> list[Clause]:
    """BM25-lite ranking of clauses against the query."""
    clauses = _load()
    idf = _idf()
    q = _tokens(query)
    scored: list[tuple[float, Clause]] = []
    for c in clauses:
        body = _tokens(c.verbatim_text + " " + c.section)
        if not body:
            continue
        counts: dict[str, int] = {}
        for t in body:
            counts[t] = counts.get(t, 0) + 1
        dl = len(body)
        score = 0.0
        for t in q:
            if t in counts:
                tf = counts[t]
                score += idf.get(t, 0.0) * (tf * 2.5) / (tf + 1.5 * (0.25 + 0.75 * dl / 30))
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored[:k] if s > 0] or [c for _, c in scored[:k]]


def get_clause(section_or_id: str) -> Clause | None:
    key = section_or_id.strip()
    for c in _load():
        if c.section == key or c.clause_id == key:
            return c
    return None


def quote_verify(quote: str, section: str) -> bool:
    """DETERMINISTIC GUARD: is `quote` actually verbatim text of clause `section`?

    Catches fabricated citations independent of the model. True iff the cited section
    exists AND the normalized quote is a contiguous substring of the clause's
    normalized verbatim text. An empty/whitespace quote never verifies.
    """
    nq = _norm(quote)
    if not nq:
        return False
    clause = get_clause(section)
    if clause is None:
        return False
    return nq in clause.norm_text


def all_sections() -> list[str]:
    return [c.section for c in _load()]
