# Cloud Deploy Runbook — run RTI Sahayak in Automation Cloud for the video

Goal: get the **already-published** coded agent running as a job in
**staging.uipath.com / hackathon26_992 / DefaultTenant**, with the human-approval
step visible in **Action Center**, so you can screen-record it.

Your `.nupkg` is already built and in the tenant feed. The HITL step now creates a
**generic Action Center task** (no Action App / App Studio needed) — so the only real
blocker is the **expired token**. Re-pack + re-publish once to ship the updated approval
node (see Step 1).

---

## Step 0 — Re-authenticate (you must do this; it opens a browser)
```bash
cd "/Users/rahulmeena/uipath hackothon/rti-sahayak"
uv run uipath auth
```
Log into **staging.uipath.com**, org **hackathon26_992**, tenant **DefaultTenant**.
This rewrites `UIPATH_ACCESS_TOKEN` in `.env`. The token lasts ~1 hour — re-run if it
expires before you finish recording.

## Step 1 — Re-pack and re-publish (ships the generic-task approval node)
The approval node was changed to create a generic Action Center task (no app needed), so
re-pack and re-publish so the cloud runs the updated build:
```bash
uv run uipath pack
uv run uipath publish
```
If publish 401s, your token expired again — redo Step 0.

## Step 2 — (optional) bind a real Action App instead
Skippable. The default is a generic task that already renders the evidence pack and is
approvable. Only if you want a polished custom form: build an Action App named exactly
`RTI-PIO-Approval` in **Shared** (Approve/Reject outcome, fields bound to the data pack),
then set `RTI_APPROVAL_APP=RTI-PIO-Approval` (and `RTI_APPROVAL_FOLDER=Shared`) before
packing. Leave unset to use the no-setup generic task.

## Step 3 — Create a Process from the package
In **Orchestrator** → **DefaultTenant** → folder **Shared** → **Automations / Processes**
→ **Add process** → pick **rti-sahayak** (version 0.1.0) → finish. (Coded agents may
appear under **Agents/Solutions** depending on the tenant — same idea.)

## Step 4 — Configure runtime credentials
The agent calls DeepSeek. The published package **excludes `.env`** (by design). So set
these as Orchestrator **Assets** or process env vars in the Shared folder:
- `RTI_PROVIDER = deepseek`
- `DEEPSEEK_API_KEY = <your key>`
If the LLM key is missing the job will fault at the first reasoning step.

## Step 5 — Run the job (this is your recording moment)
Start the process with this input (already validated locally, see `demo_input.json`):
```json
{"rti_id":"DL-RTI-2026-00077","request_text":"Under the Right to Information Act 2005, please provide a copy of the charge sheet filed in FIR No. 00077/2026 (u/s 420 IPC), and disclose the names and full addresses of the informant and any persons who assisted the police in this case.","received_date":"2026-03-20","records_ref":"rs_coref_pii"}
```
Expected (~10s): the job runs S1–S5, then **suspends** at the human gate and creates an
Action Center task titled `RTI DL-RTI-2026-00077 — PIO approval required (needs review)`.

- **Action Center → Tasks** → open it → show the draft reply, the **s8(1)(j) citation**,
  and the `[REDACTED:PERSON_CONTEXT]` redactions → click **Approve** → the job **resumes
  and completes**.
- **Fallback** if no app/task: the Orchestrator job sitting in **Suspended** state IS the
  un-bypassable human gate — show that, then resume locally for backup footage:
  `uv run uipath run agent --file demo_input.json` pauses at the same interrupt.

## Step 6 — Show the audit trail
The append-only audit log (every step, citation, redaction, and the human decision) is
written by `audit.py`. Show it from Orchestrator job output, a Data Service entity if you
wired one, or the local `eval/_runs/audit.jsonl`.

---

## Dry-run checklist before you hit record
- [ ] `uv run uipath auth` succeeded, token fresh
- [ ] `RTI_PROVIDER` + `DEEPSEEK_API_KEY` set in the Shared folder
- [ ] Re-packed + re-published after the approval-node change (Step 1)
- [ ] One full job already ran green and a task appeared + approved
- [ ] Tabs pre-opened: Orchestrator job · Action Center · audit view
- [ ] Do Not Disturb on; `demo_input.json` on clipboard
```
```
See `docs/demo-script.md` for the timed 5-minute narration.
