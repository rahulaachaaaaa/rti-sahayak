"""PIO-feedback threshold learner — RLHF-lite (spec 2026-06-29).

A contextual threshold bandit. The human PIO's approve/reject/edit at S6 is the reward.
The only learnable parameter is the per-case-type confidence gate `tau`: the agent
auto-drafts when `confidence >= tau[case_type]` ("clean — quick approve") else defers
("needs review"). RL only chooses how much finished work to put in front of the human —
S6 HITL ALWAYS runs, so the policy can never bypass the human gate.

No reward model, no PPO, no fine-tuning: just an online, guaranteed-direction update on a
single scalar per case_type, persisted to JSON. Seeded at the old static 0.55 so behaviour
is identical before any feedback ("starts as baseline, learns from there").
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from .config_loader import REPO_ROOT

BASELINE_TAU = 0.55          # the previous static LOW_CONFIDENCE gate
TAU_MIN, TAU_MAX = 0.30, 0.90  # bounded so an auto draft STILL always reaches S6
LR = 0.2
MARGIN = 0.02

CASE_TYPES = ("disclose", "exempt", "mixed", "escalate")

_DEFAULT_PATH = Path(
    os.getenv("RTI_RL_POLICY", str(REPO_ROOT / "eval" / "_runs" / "rl_policy.json"))
)


def enabled() -> bool:
    """RL on by default; `RTI_RL=off` pins every gate to the 0.55 baseline."""
    return os.getenv("RTI_RL", "on").strip().lower() not in ("off", "0", "false", "no")


def case_type_of(dispositions: list[dict] | None, escalate: bool) -> str:
    """Bucket a request by its disposition mix (the bandit 'state')."""
    disps = {d.get("disposition") for d in (dispositions or [])}
    if not disps:
        return "escalate"
    if disps == {"disclose"}:
        return "disclose"
    if disps == {"exempt"}:
        return "exempt"
    return "mixed"


def _verdict(human_decision: dict | None) -> tuple[bool, bool]:
    """Return (approved, edited) from an S6 human_decision."""
    hd = human_decision or {}
    action = str(hd.get("action") or hd.get("outcome") or "approve").lower()
    rejected = action in ("reject", "rejected", "deny", "denied", "decline", "declined")
    edited = bool(hd.get("edited_body"))
    return (not rejected), edited


def reward_of(action: str, human_decision: dict | None) -> float:
    """Map the PIO verdict to a reward, given what the agent did at the gate."""
    approved, edited = _verdict(human_decision)
    if action == "auto":
        if approved and not edited:
            return 1.0
        if approved and edited:
            return 0.0
        return -1.0
    # action == "defer"
    if approved and not edited:
        return -0.3   # needless escalation — could have auto-drafted
    return 0.3        # defer justified (PIO edited or rejected)


def decide(confidence: float, tau: float) -> str:
    return "auto" if confidence >= tau else "defer"


def _clip(x: float) -> float:
    return max(TAU_MIN, min(TAU_MAX, x))


class PolicyStore:
    """Per-case-type thresholds, persisted to JSON. Pure (no LLM, no graph)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else _DEFAULT_PATH
        self.table: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                self.table = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.table = {}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.table, indent=2), encoding="utf-8")
        except OSError:
            pass  # never let policy persistence crash the pipeline

    def _entry(self, case_type: str) -> dict:
        return self.table.setdefault(
            case_type, {"tau": BASELINE_TAU, "n": 0, "last_reward": 0.0}
        )

    def threshold(self, case_type: str) -> float:
        """Learned gate for this case_type; baseline if RL is disabled."""
        if not enabled():
            return BASELINE_TAU
        return float(self._entry(case_type)["tau"])

    def update(
        self, case_type: str, confidence: float, action: str, human_decision: dict | None
    ) -> dict:
        """Apply the online update from one PIO verdict. Returns the change record."""
        e = self._entry(case_type)
        old_tau = float(e["tau"])
        approved, edited = _verdict(human_decision)
        should_auto = approved and not edited
        if should_auto:
            # auto was / would have been right -> pull tau below this confidence
            new_tau = _clip(old_tau - LR * max(0.0, old_tau - confidence + MARGIN))
        else:
            # auto would have been wrong -> push tau above this confidence
            new_tau = _clip(old_tau + LR * max(0.0, confidence - old_tau + MARGIN))
        reward = reward_of(action, human_decision)
        e.update(tau=new_tau, n=e["n"] + 1, last_reward=reward)
        self.save()
        return {
            "case_type": case_type, "old_tau": round(old_tau, 4),
            "new_tau": round(new_tau, 4), "reward": reward, "action": action,
            "confidence": round(float(confidence), 4),
        }


def ingest_feedback(state: dict, human_decision: dict | None, store: PolicyStore | None = None) -> dict:
    """Post-S6 hook: turn the PIO verdict into a policy update + an audit row.

    Reads what the gate did from state (`rl_case_type`, `rl_action`, `confidence`),
    falling back to recomputing from dispositions/escalate when absent.
    """
    store = store or PolicyStore()
    case_type = state.get("rl_case_type") or case_type_of(
        state.get("dispositions"), bool(state.get("escalate"))
    )
    action = state.get("rl_action") or ("auto" if not state.get("escalate") else "defer")
    confidence = float(state.get("confidence", 0.0))
    change = store.update(case_type, confidence, action, human_decision)
    return change


def reset_policy(path: Path | str | None = None) -> None:
    """Clear the persisted policy (eval/demo reset)."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass
