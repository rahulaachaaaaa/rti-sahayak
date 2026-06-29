"""Tiered redaction: regex -> Presidio NER -> LLM (spec s7-domain).

Tier 1 (regex)    : structured Indian PII (Aadhaar, phone, email, PAN, vehicle no).
Tier 2 (Presidio) : named-entity PII (PERSON, LOCATION) when presidio is installed.
Tier 3 (LLM)      : contextual / coreferenced PII the first two tiers miss
                    (e.g. "the informant, her brother" — relational identifiers).

`leak_rescan` re-runs the deterministic tiers over redacted text; it powers both the
Redaction Critic (S4.5) and the zero-PII-leak invariant. The deterministic tiers make
the leak check model-independent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---- Tier 1: regex patterns (Indian-context structured identifiers) ----
# Order matters: more specific patterns first so they win the span.
_REGEX: list[tuple[str, re.Pattern[str]]] = [
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")),
    ("VEHICLE", re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,2}[\s-]?\d{4}\b")),
]

REDACTION_TOKEN = "[REDACTED:{kind}]"


@dataclass
class Span:
    start: int
    end: int
    text: str
    pii_type: str
    tier: str


def _regex_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for kind, pat in _REGEX:
        for m in pat.finditer(text):
            spans.append(Span(m.start(), m.end(), m.group(), kind, "regex"))
    return spans


# None = not yet tried; False = unavailable (don't retry); engine = ready.
_PRESIDIO_ENGINE: object | None | bool = None


PRESIDIO_SPACY_MODEL = "en_core_web_sm"


def _get_presidio():
    """Build the Presidio engine once, pinned to en_core_web_sm. Pre-checks that the model
    is installed (via spacy.util.is_package) so we NEVER trigger spaCy's auto-downloader —
    that printed noise and could raise SystemExit. Missing model -> tier disabled, not a
    crash; regex + LLM tiers still run."""
    global _PRESIDIO_ENGINE
    if _PRESIDIO_ENGINE is None:
        try:
            import spacy
            if not spacy.util.is_package(PRESIDIO_SPACY_MODEL):
                _PRESIDIO_ENGINE = False
                return _PRESIDIO_ENGINE
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": PRESIDIO_SPACY_MODEL}],
            })
            _PRESIDIO_ENGINE = AnalyzerEngine(nlp_engine=provider.create_engine())
        except BaseException:  # noqa: BLE001 — never let NER setup kill the pipeline
            _PRESIDIO_ENGINE = False
    return _PRESIDIO_ENGINE


def _presidio_spans(text: str) -> list[Span]:
    engine = _get_presidio()
    if not engine:                       # False / None -> tier unavailable, skip
        return []
    try:
        # PERSON/NRP only: dates, the FIR number, and city names are NOT s8(1)(j)
        # personal info — redacting them destroys the disclosure's utility. Structured
        # ids go through regex; residential addresses through the LLM tier.
        results = engine.analyze(
            text=text, language="en",
            entities=["PERSON", "NRP"],
            score_threshold=0.6,
        )
    except BaseException:  # noqa: BLE001
        return []
    return [
        Span(r.start, r.end, text[r.start:r.end], r.entity_type, "presidio")
        for r in results
    ]


def _dedupe(spans: list[Span]) -> list[Span]:
    """Drop spans fully contained in another; keep the widest. Sort by start."""
    spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    kept: list[Span] = []
    for s in spans:
        if any(k.start <= s.start and s.end <= k.end for k in kept):
            continue
        kept.append(s)
    return kept


def detect(text: str, *, use_presidio: bool = True) -> list[Span]:
    """Deterministic tiers only (regex + presidio). LLM tier is applied in the node."""
    spans = _regex_spans(text)
    if use_presidio:
        spans += _presidio_spans(text)
    return _dedupe(spans)


def apply_spans(text: str, spans: list[Span]) -> str:
    """Replace each span (right-to-left so offsets stay valid) with a typed token."""
    out = text
    for s in sorted(spans, key=lambda s: s.start, reverse=True):
        out = out[: s.start] + REDACTION_TOKEN.format(kind=s.pii_type) + out[s.end :]
    return out


def leak_rescan(redacted_text: str, *, use_presidio: bool = True) -> list[Span]:
    """Re-detect deterministic PII in already-redacted text. Empty list == clean."""
    return detect(redacted_text, use_presidio=use_presidio)


# Bounded so a pathological input can never loop forever; a fixpoint is reached in
# 2-3 passes in practice (each pass can only remove text, so it must terminate).
_MAX_REDACT_PASSES = 6


def redact_deterministic(
    text: str, *, use_presidio: bool = True, max_passes: int = _MAX_REDACT_PASSES
) -> tuple[str, list[Span]]:
    """Apply the deterministic tiers (regex + Presidio) repeatedly until no PII remains.

    A SINGLE pass is not enough: replacing a span changes the surrounding text, which can
    shift spaCy's NER and surface a detection that did not fire on the original (e.g.
    'Lane 4' becomes a PERSON once the adjacent 'Malviya Nagar' is replaced). Looping to a
    fixpoint guarantees ``leak_rescan(result) == []`` for the deterministic tiers, which is
    exactly the model-independent property the zero-PII-leak invariant relies on. Returns
    the redacted text and every span applied across all passes (for provenance/audit)."""
    out = text
    applied: list[Span] = []
    for _ in range(max_passes):
        spans = detect(out, use_presidio=use_presidio)
        if not spans:
            break
        applied += spans
        out = apply_spans(out, spans)
    return out, applied
