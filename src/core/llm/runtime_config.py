from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _candidate_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[3]
    return [
        root / "config" / "llm_config.yaml",
        root / "src" / "data" / "config" / "llm_config.yaml",
    ]


def load_llm_config() -> dict[str, Any]:
    for path in _candidate_paths():
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:
            return {}
    return {}


def resolve_provider_selection(
    requested_provider: str | None,
    requested_model: str | None,
    llm_config_override: dict[str, Any] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """
    Resolve provider + merged config using llm_config.yaml.

    Args:
        llm_config_override: When provided (e.g. the `llm:` section of a unified
            `--config` job file), used in place of the auto-discovered
            llm_config.yaml — same shape: {default_provider, providers: {...}}.

    Returns (None, {}) when the user explicitly requests no LLM.
    """
    cfg = llm_config_override if llm_config_override is not None else load_llm_config()
    default_provider = str(cfg.get("default_provider", "ollama")).strip().lower()
    providers_cfg = cfg.get("providers", {}) if isinstance(cfg.get("providers"), dict) else {}

    selected = (requested_provider or "").strip().lower()
    if selected == "none":
        return None, {}
    if not selected:
        selected = default_provider or "ollama"

    provider_cfg = providers_cfg.get(selected, {})
    merged = provider_cfg.copy() if isinstance(provider_cfg, dict) else {}
    if requested_model and requested_model.strip():
        merged["model"] = requested_model.strip()
    return selected, merged
