"""Loads config.yaml and expands ${ENV:-default} templates.

The global model switch lives here: `default: ${RTI_PROVIDER:-claude}` resolves
at load time from the RTI_PROVIDER env var. One env var flips every node.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# repo root = three parents up from this file (src/rti_sahayak/config_loader.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.getenv("RTI_CONFIG", REPO_ROOT / "config.yaml"))

# matches ${VAR} or ${VAR:-default}
_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand(value: Any) -> Any:
    """Recursively expand ${ENV:-default} templates in strings."""
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            var, default = m.group(1), m.group(2)
            return os.getenv(var, default if default is not None else "")
        return _ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    cfg = _expand(raw)
    cfg.setdefault("nodes", {})
    cfg.setdefault("cross_check", [])
    cfg.setdefault("on_failure", "fallback_to_default")
    return cfg


def provider_for(node: str) -> str:
    """Resolve which provider a node uses: per-node pin > global switch > default."""
    cfg = load_config()
    pinned = (cfg.get("nodes") or {}).get(node)
    if pinned:
        return pinned
    return os.getenv("RTI_PROVIDER", cfg["default"])


def cross_check_nodes() -> list[str]:
    return list(load_config().get("cross_check") or [])
