"""
src/core/config_loader.py

Centralised YAML configuration loader.

Resolution order (first found wins):
  1. Explicit path passed as argument (e.g. --config flag)
  2. ./config/default_rules.yaml  (repo-local, used during development)
  3. <package>/src/data/config/default_rules.yaml  (bundled with the package)

All call sites receive a plain dict. Missing keys fall back to module-level
defaults so the app always runs even with an empty or partial config file.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REPO_CONFIG = Path(__file__).parent.parent.parent / "config" / "default_rules.yaml"
_BUNDLED_CONFIG = Path(__file__).parent.parent / "data" / "config" / "default_rules.yaml"


def _find_default_config() -> Path | None:
    for candidate in (_REPO_CONFIG, _BUNDLED_CONFIG):
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=8)
def _load_yaml_cached(path: Path) -> dict:
    """Load and cache a YAML file by its resolved absolute path."""
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        logger.debug("Config loaded from %s", path)
        return data
    except Exception as exc:
        logger.warning("Could not load config '%s': %s — using defaults.", path, exc)
        return {}


def load_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """
    Load the rules YAML config.

    Args:
        config_path: Explicit path override. When ``None`` the default
                     config is located automatically.

    Returns:
        Parsed config dict, possibly empty if no file was found.
    """
    if config_path is not None:
        path = Path(config_path).resolve()
        if not path.exists():
            logger.warning("Config file not found: %s — using defaults.", path)
            return {}
        return _load_yaml_cached(path)

    default = _find_default_config()
    if default is None:
        logger.debug("No default config found; using built-in defaults.")
        return {}
    return _load_yaml_cached(default.resolve())


def get(config: dict, *keys: str, default: Any = None) -> Any:
    """
    Safely retrieve a nested value from a config dict.

    Example:
        get(cfg, "validation", "pptx_min_size_bytes", default=50_000)
    """
    node = config
    for key in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(key, None)
        if node is None:
            return default
    return node
