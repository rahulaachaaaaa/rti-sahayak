# RTI Sahayak

*Police reform, one RTI at a time.* — UiPath AgentHack 2026 (Maestro **Case** track).

An **audit-first** agent that helps an Indian police-station **Public Information
Officer (PIO)** answer citizen **Right to Information (RTI Act 2005)** requests: it reads
the request, retrieves the relevant (synthetic, CCTNS-style) records, decides what
**§8** allows — citing the exact clause — redacts what is exempt, and drafts a compliant
reply. A human PIO approves in **Action Center** before anything is sent. Every decision,
citation, and redaction is logged to an append-only audit trail.

Each reasoning step runs on **Claude Opus 4.8** or **DeepSeek**, flipped by one setting.

## What runs where (UiPath)

| Concern | UiPath component |
|---|---|
| Reasoning agent | **Coded agent** — LangGraph via `uipath-langchain`, on Automation Cloud |
| Orchestration / case lifecycle | **Maestro** (Case) |
| Human approval (un-bypassable) | **Action Center** (`interrupt(CreateEscalation(...))`) |
| State + append-only audit log | **Data Service** (`AuditLog` entity) |
| ROI / deadline dashboard | **UiPath Apps** |
| Build assistant | **Claude Code** (see below) |

**Agent type:** coded multi-node LangGraph agent (deterministic pipeline + two critic
loops + an HITL gate), deployed as a UiPath coded agent and invoked by Maestro.

## Pipeline

```
S1 Intake/Classify → S2 Records Retrieval → S3 Exemption Reasoner (RAG over §8)
   → S3.5 Citation Critic ──(repair ≤2 / abstain→escalate)
   → S4 Severability/Redaction (regex → Presidio → LLM)
   → S4.5 Redaction Critic ──(repair ≤2 / leak→escalate)
   → S5 Response Drafter → S6 PIO Approval (HITL) → END
```

Agentic behaviour (spec §5.1): bounded self-repair loops, **cross-model verification**
on S3 (Claude vs DeepSeek disagree → force human review), a confidence risk-gate, and
three-way severability (disclose / exempt / partial).

## The model switch

One env var flips every node:

```bash
export RTI_PROVIDER=deepseek   # everything on DeepSeek (bring-your-own key)
export RTI_PROVIDER=claude     # everything on Claude via UiPath LLM Gateway (no key; needs `uipath auth`)
```

- **Claude → UiPath LLM Gateway**, no personal key (UiPath bills it).
- **DeepSeek → your `DEEPSEEK_API_KEY`** (not in the gateway).
- Pin a single node in `config.yaml` under `nodes:`; turn on the S3 ensemble guard with
  `cross_check: [exemption_reasoner]`.

See [config.yaml](config.yaml) and [src/rti_sahayak/models.py](src/rti_sahayak/models.py).

## Setup

Requires **Python 3.11–3.12** for the full UiPath runtime (the SDK targets ≤3.12; the
keyless test gate also runs on 3.14).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                 # installs uipath, uipath-langchain, langchain, etc.
cp .env.example .env             # set RTI_PROVIDER + DEEPSEEK_API_KEY
```

UiPath lifecycle:

```bash
uipath auth                      # needed for the Claude/gateway path
uipath init
uipath run agent '{"rti_id":"st02","request_text":"...","received_date":"2026-03-20","records_ref":"rs_fir_witness_status"}'
uipath pack
uipath publish --my-workspace
```

> The exact gateway model string (`claude-opus-4-8` in config.yaml) is the one runtime
> value to confirm against the discovery endpoint after `uipath auth`.

## Validation

Demo-level but with real rigor (spec §9).

```bash
# Tier-1 deterministic invariants — CI gate, NO API key required:
pytest -q

# Full harness: invariants + Tier-2 metrics + scorecard, N runs per config:
python eval/run.py --config all-deepseek --n 3
python eval/run.py --config mix --cross-check          # S3 ensemble guard on
python eval/run.py --no-pipeline                       # deterministic guard proofs only
```

- **Tier-1 invariants** (must be 100%, model-independent): provenance exists, every
  citation quote-verifies, the pipeline pauses at HITL, zero PII leak.
- **8 stratified + 6 seeded-fault** cases in [eval/cases/](eval/cases/); each seeded fault
  maps 1:1 to the guard it must trip.
- `scorecard.md` compares model configs — invariants stay green while quality/cost shift.

## Layout

```
config.yaml · langgraph.json · pyproject.toml
src/rti_sahayak/  graph.py  models.py  state.py  rag.py  redaction.py  audit.py  nodes/
corpus/  rti_act_s8.jsonl  records/*.json
eval/  run.py  invariants.py  metrics.py  cases/*.yaml
tests/test_invariants.py
```

## Built with Claude Code

The Python (graph, nodes, RAG, redaction, audit, eval harness, synthetic corpus) was
authored with **Claude Code** as the coding agent; the UiPath shell (Maestro Case,
Action Center, Data Service, Apps) is wired in UiPath Studio Web / Automation Cloud.

## Caveats

Synthetic data only; live CCTNS integration is future work. Confidence prioritises human
attention — it never auto-sends. The audit log is for provenance/observability, not
tamper-evidence. License: [MIT](LICENSE).
