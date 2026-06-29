# RTI Sahayak — Demo Video Kit

Target: **under 5 minutes**, public on YouTube, **live footage** of it running on UiPath
Automation Cloud (not slides). It is a **coded agent** on Automation Cloud with an
**Action Center** human-approval gate. (Maestro Case is optional polish, not required.)
Tenant: **staging.uipath.com / hackathon26_992 / DefaultTenant**. Deploy steps:
`docs/cloud-deploy-runbook.md`.

## Recording setup (macOS)

- **Recorder:** press `Cmd+Shift+5` → "Record Entire Screen" (or QuickTime → New Screen
  Recording). Pick the option to **show mouse clicks**.
- **Mic:** in the `Cmd+Shift+5` Options menu, set your mic ON so narration is captured.
- **Resolution:** record at 1080p. Use one monitor; hide other windows.
- **Browser prep:** log into `staging.uipath.com` (org `hackathon26_992`), open these tabs
  in order so you just switch left-to-right:
  1. Orchestrator → your process (ready to start a job)
  2. Action Center → Tasks
  3. (optional) Maestro → your Case
  4. Data Service → AuditLog entity (or terminal showing the audit output)
- **Close** Slack/email/notifications. Turn on Do Not Disturb.
- **Have ready:** the sample input JSON copied to clipboard (see below).

## Pre-flight checklist (do a dry run once before recording)

- [ ] Agent published to **staging.uipath.com / hackathon26_992** and a Process created from it
- [ ] Re-packed + re-published after the approval-node change (generic Action Center task)
- [ ] `RTI_PROVIDER=deepseek`, `DEEPSEEK_API_KEY` set
- [ ] One full job already run successfully → confirms timing (~10s/case)
- [ ] An Action Center task actually appeared and you can approve it
- [ ] Audit trail visible somewhere you can show on screen

## Sample input (validated locally — see `demo_input.json`)
```json
{"rti_id":"DL-RTI-2026-00077","request_text":"Under the Right to Information Act 2005, please provide a copy of the charge sheet filed in FIR No. 00077/2026 (u/s 420 IPC), and disclose the names and full addresses of the informant and any persons who assisted the police in this case.","received_date":"2026-03-20","records_ref":"rs_coref_pii"}
```
This case discloses the offence facts, exempts the informant's identity citing **s8(1)(j)**
(quote-verified), and redacts hidden coreferent PII to `[REDACTED:PERSON_CONTEXT]` —
the strongest 60-second visual. Backup case: `rs_fir_witness_status`.

## The script (timed — narrate while you click)

### 0:00–0:30 — Hook + problem
> "This is RTI Sahayak. In India, citizens file Right to Information requests, and a
> police Public Information Officer must answer them — deciding what the law lets them
> share, what to redact, and citing the exact legal clause. It's slow and error-prone.
> RTI Sahayak is an audit-first agent that does the reasoning, but a human always
> approves before anything is sent."

*On screen:* title / the README top, or the pipeline diagram for 3 seconds.

### 0:30–1:00 — Architecture (name the UiPath pieces)
> "It's a coded LangGraph agent deployed on UiPath Automation Cloud, orchestrated as a
> Maestro Case. The human approval is an un-bypassable Action Center step, and every
> decision is written to an append-only audit log in Data Service."

*On screen:* the Maestro Case stages, or the pipeline diagram.

### 1:00–3:15 — Live demo (the core — keep it continuous)
1. Orchestrator → **Start job**, paste the input. Narrate: *"A citizen RTI comes in."*
2. Let it run (~10s). Narrate the pipeline: *"It classifies the request, retrieves the
   records, reasons over Section 8 of the RTI Act to decide what's exempt — citing the
   exact clause word-for-word — then redacts every phone number, Aadhaar, and name."*
3. Switch to **Action Center** → open the task. Narrate: *"It does NOT send. It pauses
   here for the PIO."* Show the draft reply, the citations, the redactions.
4. **Approve** it. Switch back → job completes. Narrate: *"Approved — only now is the
   reply finalized."*
5. Show the **audit trail**. Narrate: *"Every step, citation, and redaction is logged."*

### 3:15–4:15 — What makes it strong (talk over screen)
> "Four safety invariants are enforced and tested: every decision has a paper trail,
> every legal citation must quote-verify against the real Act, the pipeline always pauses
> for a human, and zero PII leaks — verified by a keyless test gate, 100% green."
> "One env var flips every reasoning step between Claude and DeepSeek. And a lightweight
> feedback learner adjusts how much the agent auto-drafts versus defers to the human,
> per case-type — it can never bypass the human gate."

*On screen:* run `pytest -q` live (30 passed) or show `scorecard.md`.

### 4:15–4:45 — Claude Code bonus + close
> "The entire Python — graph, RAG, redaction, audit, eval harness — was built with Claude
> Code as the coding agent. RTI Sahayak: police reform, one RTI at a time."

*On screen:* repo / a Claude Code session screenshot.

## Tips
- If a live cloud run is flaky, pre-run it once and have a backup local run
  (`uipath run agent '<json>'`) you can cut to — but the cloud + Action Center part must
  be real footage.
- Don't over-explain. Judges want to SEE it work. Demo > narration.
- Export, watch it once for audio, then upload to YouTube as **Public** or **Unlisted-
  but-visible**. Paste the link in Devpost.
