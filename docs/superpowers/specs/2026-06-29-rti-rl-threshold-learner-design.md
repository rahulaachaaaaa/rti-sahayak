# RTI Sahayak — PIO-Feedback Threshold Learner (RLHF-lite)

**Date:** 2026-06-29 · **Status:** approved, implementing

## Goal

Replace the static confidence gate (`LOW_CONFIDENCE = 0.55` in `s5_drafter.py`) with a
per-case-type threshold `τ[case_type]` that **learns online from the PIO's approve / reject /
edit decisions**. The agent auto-drafts where the PIO trusts it and defers ("needs review")
where it doesn't — **without ever bypassing the S6 human gate.**

This is RLHF-lite: a contextual threshold bandit where the human IS the reward. No reward
model, no PPO, no fine-tuning. The Claude path runs through UiPath's gateway (no tunable
weights); the only learnable parameter is the operational gate, and the only signal is the PIO.

## Non-goals (YAGNI)

- No neural policy, reward model, PPO, or model fine-tuning.
- No model comparison / cross-model check / comparative scorecard (dropped).
- No per-node bandits. One gate, one policy table.
- Data Service sync of the policy is an optional later stretch, not in this spec.

## Provider model

The whole project runs on ONE provider selected by the global `RTI_PROVIDER` toggle
(`claude` | `deepseek`) — demoable swap. We do NOT run both at once. Both toggle positions
must reach ALL-GREEN independently (proves the swap works), but never as a comparison.

## RL formulation

- **State** = `case_type ∈ {disclose, exempt, mixed, escalate}`, derived from dispositions
  (all disclose → `disclose`; all exempt → `exempt`; both → `mixed`; no records / hard
  escalate → `escalate`). Matches the stratified eval cases.
- **Action** at the gate: `auto` (confidence ≥ τ → badge "clean — quick approve") vs
  `defer` (badge "needs review"). **S6 HITL runs in both cases** — RL only chooses how much
  finished work to put in front of the human.
- **Reward** from S6 `human_decision` (`action`, `edited_body`):
  | situation | reward |
  |---|---|
  | `auto` + approved unedited | +1.0 |
  | `auto` + approved with edits | 0.0 |
  | `auto` + rejected | −1.0 |
  | `defer` + approved unedited | −0.3 (needless escalation) |
  | `defer` + edited / rejected | +0.3 (defer justified) |
- **Update rule** (guaranteed-direction, online):
  - `should_auto = approved AND not edited` (auto would have been right).
  - if `should_auto`: `τ ← τ − lr · max(0, τ − conf + margin)` (pull threshold below this confidence).
  - else: `τ ← τ + lr · max(0, conf − τ + margin)` (push threshold above this confidence).
  - `lr = 0.2`, `margin = 0.02`, clipped to `[0.30, 0.90]`.

## Components (each independently testable)

1. **`src/rti_sahayak/rl.py`** — pure, no LLM:
   - `PolicyStore(path)` — load/save JSON `{case_type: {tau, n, last_reward}}`; seeded at
     `tau = 0.55` (today's static value) so behavior is unchanged before any feedback.
   - `case_type_of(dispositions, escalate) -> str`
   - `reward_of(action, human_decision) -> float`
   - `threshold(case_type) -> float`
   - `update(case_type, confidence, action, human_decision) -> float` (returns new τ)
   - `enabled()` — reads `RTI_RL` env (`on` default, `off` → always use 0.55 baseline).
2. **`s5_drafter.py`** — compute `case_type`; gate on `policy.threshold(case_type)` instead
   of the constant; record `case_type`, chosen `tau`, and `action` (`auto`/`defer`) into
   state + audit so the feedback step can attribute reward.
3. **`rl.ingest_feedback(state, human_decision)`** — called after S6 (eval harness on
   resume; Action Center task-resolve in deployment). Computes reward, updates the policy,
   writes an audit entry `actor="rl", action="policy_update"`.

## Data flow

```
S5 drafter: case_type = case_type_of(...)
            τ = policy.threshold(case_type)        # learned, seeded 0.55
            action = auto if confidence ≥ τ else defer
            state += {case_type, rl_tau, rl_action}
   ↓
S6 approval (HITL) → human_decision {action, edited_body}   # ALWAYS runs
   ↓
rl.ingest_feedback(state, human_decision):
   reward = reward_of(action, human_decision)
   policy.update(case_type, confidence, action, human_decision)  # τ moves, persisted
   audit += {actor:"rl", action:"policy_update", case_type, old_tau, new_tau, reward}
```

## Safety / invariants preserved

- τ bounded `[0.30, 0.90]` → an auto draft **still always reaches S6**. RL cannot disable HITL.
- Citations/quote-verify, redaction leak-rescan, append-only audit — all untouched.
- New invariant for the eval harness: after any feedback, every run still interrupts at S6
  (HITL un-bypassable) and τ stays within bounds.

## Testing

- **`tests/test_rl.py` (keyless, deterministic):**
  - `reward_of` maps each situation correctly.
  - `update` direction: `auto`+rejected raises τ; `defer`+approved-unedited lowers τ.
  - convergence: a stream of (conf, verdict) for one case_type drives τ to separate
    auto-approved from rejected confidences.
  - τ clipped to `[0.30, 0.90]`; `RTI_RL=off` pins τ = 0.55.
- **`eval/run.py`:** after each stratified case, simulate the PIO verdict from
  `case.expected` and call `ingest_feedback`; scorecard shows learned τ per case_type.
- **To green:** `pytest` (9 existing + new) keyless; `eval/run.py --config all-claude --n 3`
  ALL GREEN; then `--config all-deepseek --n 3` ALL GREEN (proves the toggle).

## Demo narrative

Agent ships at the baseline 0.55 gate. As the PIO approves/rejects in Action Center, the
per-case-type threshold self-tunes — confidently auto-drafting full-disclosure RTIs (always
rubber-stamped) while deferring exempt/mixed ones the PIO tends to edit. Flip `RTI_RL=off`
to show baseline vs learned; flip `RTI_PROVIDER` to swap Claude↔DeepSeek for the whole project.
