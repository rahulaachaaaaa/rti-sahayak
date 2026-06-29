# RTI Sahayak — scorecard (all-deepseek)

**Tier-1 invariants:** ✅ 100% every run (1 runs)

## RL — learned auto-draft threshold per case-type (from PIO feedback)
Seeded at 0.55; lower τ = more confident auto-drafting, higher τ = defer to human.

| case_type | learned τ |
|---|---|
| disclose | 0.55 |
| exempt | 0.634 |
| mixed | 0.786 |
| escalate | 0.55 |

## Seeded-fault guard proofs (deterministic)
| case | guard | result |
|---|---|---|
| sf01_fabricated_citation | citations_quote_verify | ✅ fabricated citation rejected by quote-verify |
| sf02_wrong_similar_rule | citations_quote_verify | ✅ mismatched clause/quote rejected by quote-verify |
| sf03_hidden_coref_pii | zero_pii_leak | ✅ unredacted structured PII caught by leak re-scan |
| sf04_no_applicable_rule | escalation | ✅ no-record request escalates to human |
| sf05_over_redaction | over_redaction_rate | ✅ over-redaction flagged by utility metric |
| sf06_cross_model_disagreement | forced_human_review | ✅ model disagreement forces human review |

## Tier-2 metrics (min / mean / max over runs)
| metric | min | mean | max |
|---|---|---|---|
| disposition_accuracy | 0.7778 | 0.7778 | 0.7778 |
| citation_accuracy | 1.0 | 1.0 | 1.0 |
| citation_hallucination_rate | 0.0 | 0.0 | 0.0 |
| leak_rate | 0.0 | 0.0 | 0.0 |
| over_redaction_rate | 0.2222 | 0.2222 | 0.2222 |
| escalation_precision | 1.0 | 1.0 | 1.0 |
| escalation_recall | 1.0 | 1.0 | 1.0 |
| cross_model_disagreement_rate | 0.0 | 0.0 | 0.0 |
| avg_latency_s | 10.468 | 10.468 | 10.468 |
