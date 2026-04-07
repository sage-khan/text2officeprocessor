"""
Tests for the centralised config loader (src/core/config_loader.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.core.config_loader import get, load_config


# ---------------------------------------------------------------------------
# load_config — basic resolution
# ---------------------------------------------------------------------------

def test_load_config_returns_dict_with_default_config():
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "validation" in cfg or "sanitization" in cfg  # at least one known key


def test_load_config_explicit_path(tmp_path):
    yaml_file = tmp_path / "custom.yaml"
    yaml_file.write_text("validation:\n  strict: true\n  pptx_min_size_bytes: 9999\n", encoding="utf-8")
    cfg = load_config(yaml_file)
    assert cfg["validation"]["strict"] is True
    assert cfg["validation"]["pptx_min_size_bytes"] == 9999


def test_load_config_missing_explicit_path_returns_empty(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg == {}


def test_load_config_empty_yaml_returns_empty_dict(tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text("", encoding="utf-8")
    cfg = load_config(f)
    assert cfg == {}


def test_load_config_malformed_yaml_returns_empty_dict(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("this: is: not: valid: yaml: :\n  - [broken", encoding="utf-8")
    cfg = load_config(f)
    assert cfg == {}


# ---------------------------------------------------------------------------
# get — safe nested access helper
# ---------------------------------------------------------------------------

def test_get_returns_nested_value():
    cfg = {"a": {"b": {"c": 42}}}
    assert get(cfg, "a", "b", "c") == 42


def test_get_returns_default_for_missing_key():
    cfg = {"a": {}}
    assert get(cfg, "a", "b", "c", default=99) == 99


def test_get_returns_default_when_traversal_hits_non_dict():
    cfg = {"a": "string"}
    assert get(cfg, "a", "b", default="fallback") == "fallback"


def test_get_returns_none_by_default():
    assert get({}, "missing") is None


# ---------------------------------------------------------------------------
# ProgrammaticValidator reads from config
# ---------------------------------------------------------------------------

def test_validator_reads_custom_artifacts(tmp_path):
    yaml_file = tmp_path / "custom.yaml"
    yaml_file.write_text(
        "validation:\n  markdown_artifacts:\n    - '%%CUSTOM%%'\n  check_artifacts: true\n",
        encoding="utf-8",
    )
    from src.core.validation.validator import ProgrammaticValidator
    v = ProgrammaticValidator(config_path=yaml_file)
    assert v.markdown_artifacts == ["%%CUSTOM%%"]


def test_validator_reads_custom_placeholders(tmp_path):
    yaml_file = tmp_path / "custom.yaml"
    yaml_file.write_text(
        "validation:\n  known_placeholders:\n    - 'MY CUSTOM PLACEHOLDER'\n",
        encoding="utf-8",
    )
    from src.core.validation.validator import ProgrammaticValidator
    v = ProgrammaticValidator(config_path=yaml_file)
    assert "MY CUSTOM PLACEHOLDER" in v.known_placeholders


def test_validator_falls_back_to_defaults_with_empty_config(tmp_path):
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.write_text("", encoding="utf-8")
    from src.core.validation.validator import (
        ProgrammaticValidator,
        _DEFAULT_MARKDOWN_ARTIFACTS,
        _DEFAULT_KNOWN_PLACEHOLDERS,
    )
    v = ProgrammaticValidator(config_path=yaml_file)
    assert v.markdown_artifacts == _DEFAULT_MARKDOWN_ARTIFACTS
    assert v.known_placeholders == _DEFAULT_KNOWN_PLACEHOLDERS


def test_validator_check_flags_respected(tmp_path):
    yaml_file = tmp_path / "no_checks.yaml"
    yaml_file.write_text(
        "validation:\n  check_artifacts: false\n  check_placeholders: false\n  check_file_size: false\n",
        encoding="utf-8",
    )
    from src.core.validation.validator import ProgrammaticValidator
    v = ProgrammaticValidator(config_path=yaml_file)
    assert v.check_artifacts is False
    assert v.check_placeholders is False
    assert v.check_file_size is False


def test_validator_custom_min_size(tmp_path):
    yaml_file = tmp_path / "size.yaml"
    yaml_file.write_text("validation:\n  pptx_min_size_bytes: 1234\n", encoding="utf-8")
    from src.core.validation.validator import ProgrammaticValidator
    v = ProgrammaticValidator(config_path=yaml_file)
    assert v.pptx_min_size_bytes == 1234


# ---------------------------------------------------------------------------
# LLMValidator reads from config
# ---------------------------------------------------------------------------

def test_llm_validator_reads_custom_max_chars(tmp_path):
    yaml_file = tmp_path / "llm.yaml"
    yaml_file.write_text("llm_validation:\n  max_content_chars: 500\n", encoding="utf-8")
    from unittest.mock import MagicMock
    from src.core.validation.validator import LLMValidator
    v = LLMValidator(provider=MagicMock(), config_path=yaml_file)
    assert v._max_content_chars == 500


def test_llm_validator_reads_custom_prompt(tmp_path):
    yaml_file = tmp_path / "llm.yaml"
    yaml_file.write_text(
        "llm_validation:\n  prompt: 'Custom prompt: {content}'\n",
        encoding="utf-8",
    )
    from unittest.mock import MagicMock
    from src.core.validation.validator import LLMValidator
    v = LLMValidator(provider=MagicMock(), config_path=yaml_file)
    assert "Custom prompt" in v._prompt_template


def test_llm_validator_falls_back_to_default_prompt_with_empty_config(tmp_path):
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.write_text("", encoding="utf-8")
    from unittest.mock import MagicMock
    from src.core.validation.validator import LLMValidator, _DEFAULT_LLM_PROMPT
    v = LLMValidator(provider=MagicMock(), config_path=yaml_file)
    assert v._prompt_template == _DEFAULT_LLM_PROMPT.strip()
