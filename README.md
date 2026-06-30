# RTI Sahayak

*Police reform, one RTI at a time.* — UiPath AgentHack 2026 · Track: **UiPath Maestro Case**.

## Submission Links

- 🎥 **Demo video (≤5 min):** https://youtu.be/I2JscSfypwA
- 📊 **Presentation deck:** https://docs.google.com/presentation/d/1lNnXYb1A-2QiPLKy8k720E8yAalQID59/edit?usp=sharing
- 💻 **Repository:** https://github.com/rahulaachaaaaa/rti-sahayak

## Project Description

In India, any citizen can file a **Right to Information (RTI Act 2005)** request, and a
police-station **Public Information Officer (PIO)** is legally bound to answer within
**30 days** — deciding what the law lets them disclose, redacting personal data, and
citing the exact section of the Act. Get it wrong and the cost is real: a leaked
informant's identity, or a personal **₹25,000 penalty** on the officer.

**RTI Sahayak** treats every RTI request as a **case** and runs its full lifecycle as one
long-running, suspendable workflow — an **audit-first agent** that does this reasoning but
**never sends anything without a human**. For each case it: classifies the requested items,
retrieves the relevant (synthetic, CCTNS-style) records, decides what **Section 8**
allows — **quoting the exempting clause word-for-word** so it can't invent law — redacts
what is exempt (including *hidden coreferent* PII), drafts a compliant reply, and then
**pauses at an un-bypassable human-approval gate** in UiPath Action Center. A PIO reviews
the draft, the quote-verified citations, and the redactions, then approves. Every
decision, citation, and redaction is written to an append-only audit trail.

Each reasoning step runs on **Claude Opus 4.8** (via the UiPath LLM Gateway, keyless) or
**DeepSeek**, flipped by one environment variable.

## Track: Agentic Case Management (UiPath Maestro Case)

Each RTI request is a **case**, and the coded agent **orchestrates its entire lifecycle** as
a single suspendable workflow on the UiPath Platform:

```
intake/classify → retrieve case records → exemption reasoning → redaction
   → draft reply → PIO approval (human case task) → close
```

The agent suspends mid-case at a human task and resumes on approval — exactly the
long-running, human-in-the-loop case pattern this track targets. **All orchestration and
agent logic run through the UiPath Platform** (coded agent on Orchestrator, human task in
Action Center, reasoning via the LLM Gateway).

## UiPath Components

**Built and running in this submission:**

| Concern | UiPath component |
|---|---|
| Case orchestration / lifecycle | **Coded Agent** — LangGraph (`uipath` + `uipath-langchain`), the agent *is* the case workflow; deployed serverless on Automation Cloud |
| Long-running execution / jobs | **Orchestrator** — process published from the package; jobs run **and suspend** mid-case |
| Human-in-the-loop case task (un-bypassable) | **Action Center** — `interrupt(CreateEscalation(...))` raises the PIO approval task |
| LLM reasoning (keyless) | **UiPath LLM Gateway** — `UiPathChat`, no personal API key |

**Roadmap (stated honestly — not in this build):**

| Concern | Target component | Current state |
|---|---|---|
| Visual case canvas | **Maestro Case** | Workflow is built to drop into a Maestro Case canvas; currently orchestrated as the coded agent above |
| Append-only audit store | **Data Service** (`AuditLog` entity) | Written to a JSONL sink + in-state list today; Data Service entity write is roadmap |
| Deadline / penalty ROI dashboard | **UiPath Apps** | Roadmap |

## Agent Type

**Coded Agent** (not low-code). A deterministic, multi-node **LangGraph** pipeline (two
self-repair *critic* loops + an HITL gate), packaged and published as a UiPath coded
agent via the `uipath` CLI. No Agent Builder / low-code agent is used.

## Pipeline

```
S1 Intake/Classify → S2 Records Retrieval → S3 Exemption Reasoner (RAG over §8)
   → S3.5 Citation Critic ──(repair ≤2 / abstain → escalate)
   → S4 Severability/Redaction (regex → optional Presidio NER → LLM)
   → S4.5 Redaction Critic ──(repair ≤2 / leak → escalate)
   → S5 Response Drafter → S6 PIO Approval (HITL) → END
```

Agentic behaviour: bounded self-repair loops, **cross-model verification** on S3 (Claude
vs DeepSeek disagree → force human review), a confidence risk-gate, and three-way
severability (disclose / exempt / partial). Tier-2 Presidio NER is optional and disabled
in the serverless build, so deployed redaction is **regex → LLM**.

## The model switch

```bash
export RTI_PROVIDER=claude     # every node on Claude via UiPath LLM Gateway (no key; needs `uipath auth`)
export RTI_PROVIDER=deepseek   # every node on DeepSeek (bring-your-own DEEPSEEK_API_KEY)
```

Pin a single node in [config.yaml](config.yaml) under `nodes:`; enable the S3 ensemble
guard with `cross_check: [exemption_reasoner]`. See [src/rti_sahayak/models.py](src/rti_sahayak/models.py).

## Setup Instructions (for judging)

Requires **Python 3.11–3.12** (the UiPath runtime targets ≤3.12). Uses [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install dependencies from the lockfile (reproducible)
uv sync --extra dev

# 2. Fastest verification — keyless deterministic test gate (NO API key, NO cloud):
uv run pytest -q                     # expect: 30 passed

# 3. Run the agent locally on the demo case (it suspends at the human-approval gate):
cp .env.example .env                 # set RTI_PROVIDER (+ DEEPSEEK_API_KEY if using deepseek)
uv run uipath run agent --file demo_input.json
```

**Run it on UiPath Automation Cloud (the full demo):**

```bash
uv run uipath auth                   # log into the tenant (needed for the Claude/gateway path)
uv lock                              # IMPORTANT: re-lock after any version bump, before pack
uv run uipath pack
uv run uipath publish                # publishes the package to the tenant feed
```

Then in **Orchestrator**: create a process from the published `rti-sahayak` package, set
`RTI_PROVIDER` (and `DEEPSEEK_API_KEY` if using DeepSeek), **Start** a job with the
contents of [demo_input.json](demo_input.json). The job runs S1–S5 (~10s) and **suspends**
at S6 — open the task in **Action Center**, review, and **Approve** to let it complete.

> Packaging note: the serverless runtime installs with `uv sync --locked`, so `uv.lock`
> must match `pyproject.toml`. Always re-lock after a version bump before `uipath pack`.

## Validation

```bash
uv run pytest -q                                   # Tier-1 invariants — keyless CI gate
uv run python eval/run.py --config all-deepseek --n 3   # invariants + Tier-2 metrics + scorecard
uv run python eval/run.py --no-pipeline                 # deterministic guard proofs only
```

- **Tier-1 invariants** (100%, model-independent): provenance exists, every citation
  quote-verifies, the pipeline pauses at HITL, zero PII leak.
- **8 stratified + 6 seeded-fault** cases in [eval/cases/](eval/cases/); each seeded fault
  maps 1:1 to the guard it must trip.

## Layout

```
config.yaml · langgraph.json · pyproject.toml · demo_input.json
src/rti_sahayak/  graph.py  models.py  state.py  rag.py  redaction.py  audit.py  nodes/
corpus/  rti_act_s8.jsonl  records/*.json
eval/  run.py  invariants.py  metrics.py  cases/*.yaml
tests/  test_invariants.py  test_rl.py
```

## Built with Claude Code

The Python (graph, nodes, RAG, redaction, audit, eval harness, synthetic corpus) was
authored with **Claude Code** as the coding agent.

## Caveats

Synthetic data only; live CCTNS integration is authorized future work (there is no public
CCTNS API). Confidence prioritises human attention — it never auto-sends. The audit log is
for provenance/observability, not tamper-evidence. License: [MIT](LICENSE).
