"""Tests for src/core/config.py — loading, hashing, and override behaviour."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.config import Settings

REPO_ROOT = Path(__file__).parents[1]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"


# ── Loading ───────────────────────────────────────────────────────────────────

def test_load_default_config():
    settings = Settings.load(DEFAULT_YAML)
    assert isinstance(settings.video.target_fps, float)
    assert isinstance(settings.video.target_width, int)
    assert isinstance(settings.vlm.model, str)
    assert isinstance(settings.storyboard.review_threshold, float)
    assert isinstance(settings.editor.similarity_threshold, float)


def test_load_custom_yaml(tmp_path):
    cfg = tmp_path / "custom.yaml"
    cfg.write_text(yaml.dump({"video": {"target_fps": 2.0, "target_width": 320}}))
    settings = Settings.load(cfg)
    assert settings.video.target_fps == 2.0
    assert settings.video.target_width == 320
    # Non-specified keys fall back to defaults.
    assert settings.vlm.provider == "anthropic"


def test_load_empty_yaml_uses_defaults(tmp_path):
    cfg = tmp_path / "empty.yaml"
    cfg.write_text("")
    settings = Settings.load(cfg)
    assert settings.video.target_fps == 4.0


# ── config_hash ───────────────────────────────────────────────────────────────

def test_config_hash_is_string():
    settings = Settings.load(DEFAULT_YAML)
    assert isinstance(settings.config_hash, str)
    assert len(settings.config_hash) == 64  # sha256 hex digest


def test_config_hash_stable_for_same_config():
    s1 = Settings.load(DEFAULT_YAML)
    s2 = Settings.load(DEFAULT_YAML)
    assert s1.config_hash == s2.config_hash


def test_config_hash_changes_when_target_fps_changes():
    s1 = Settings.load(DEFAULT_YAML)
    s2 = s1.model_copy(update={"video": s1.video.model_copy(update={"target_fps": 1.0})})
    assert s1.config_hash != s2.config_hash


def test_config_hash_changes_when_target_width_changes():
    s1 = Settings.load(DEFAULT_YAML)
    s2 = s1.model_copy(update={"video": s1.video.model_copy(update={"target_width": 320})})
    assert s1.config_hash != s2.config_hash


def test_config_hash_stable_when_vlm_changes():
    """VLM config changes should NOT affect the config_hash (video section only)."""
    s1 = Settings.load(DEFAULT_YAML)
    s2 = s1.model_copy(update={"vlm": s1.vlm.model_copy(update={"temperature": 0.9})})
    assert s1.config_hash == s2.config_hash


def test_config_hash_stable_when_storyboard_changes():
    s1 = Settings.load(DEFAULT_YAML)
    s2 = s1.model_copy(update={"storyboard": s1.storyboard.model_copy(update={"review_threshold": 0.99})})
    assert s1.config_hash == s2.config_hash
