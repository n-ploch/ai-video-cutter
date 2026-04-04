"""Tests for the refactored ProjectStorage API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import Settings
from core.project import Project, ProjectStatus
from core.schemas.video import ProcessingConfig
from core.storage import ProjectStorage, hash_video_file

REPO_ROOT = Path(__file__).parents[1]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"
FIXTURE = Path(__file__).parent / "fixtures" / "video_fixture.mov"


@pytest.fixture
def settings():
    return Settings.load(DEFAULT_YAML)


@pytest.fixture
def storage(tmp_path):
    return ProjectStorage(
        root=tmp_path / "projects",
        default_config=DEFAULT_YAML,
    )


@pytest.fixture
def fixture_video():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE}")
    return FIXTURE


# ── hash_video_file ───────────────────────────────────────────────────────────

def test_hash_video_file_returns_16_char_string(tmp_path):
    f = tmp_path / "dummy.mp4"
    f.write_bytes(b"x" * 1024)
    h = hash_video_file(f)
    assert isinstance(h, str)
    assert len(h) == 16


def test_hash_video_file_same_content_same_hash(tmp_path):
    f1 = tmp_path / "a.mp4"
    f2 = tmp_path / "b.mp4"
    f1.write_bytes(b"abc" * 100)
    f2.write_bytes(b"abc" * 100)
    assert hash_video_file(f1) == hash_video_file(f2)


def test_hash_video_file_different_content_different_hash(tmp_path):
    f1 = tmp_path / "a.mp4"
    f2 = tmp_path / "b.mp4"
    f1.write_bytes(b"aaa" * 100)
    f2.write_bytes(b"bbb" * 100)
    assert hash_video_file(f1) != hash_video_file(f2)


# ── create_project ────────────────────────────────────────────────────────────

def test_create_project_returns_project(storage, fixture_video):
    project = storage.create_project("myproject", [fixture_video])
    assert isinstance(project, Project)
    assert project.name == "myproject"


def test_create_project_folder_structure(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    project_dir = storage.get_project_path("myproject")
    for subfolder in ("videos", "analysis", "storyboard", "timeline"):
        assert (project_dir / subfolder).is_dir(), f"Missing subfolder: {subfolder}"


def test_create_project_copies_config(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    config_file = storage.get_project_path("myproject") / "config.yaml"
    assert config_file.exists()


def test_create_project_writes_manifest(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    manifest_path = storage.get_project_path("myproject") / "videos" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert "videos" in manifest
    assert len(manifest["videos"]) == 1


def test_create_project_manifest_has_null_processing_steps(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    manifest_path = storage.get_project_path("myproject") / "videos" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = list(manifest["videos"].values())[0]
    for step in ("probed", "downsampled", "optical_flow", "segmented", "described"):
        assert entry["processing"][step] is None


def test_create_project_status_created(storage, fixture_video):
    project = storage.create_project("myproject", [fixture_video])
    assert project.status == ProjectStatus.created


# ── add_video ─────────────────────────────────────────────────────────────────

def test_add_video_returns_hash(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    h = storage.add_video("myproject", fixture_video)
    assert isinstance(h, str) and len(h) == 16


def test_add_video_deduplication(storage, fixture_video):
    """Adding the same video twice should not create a duplicate manifest entry."""
    storage.create_project("myproject", [fixture_video])
    h1 = storage.add_video("myproject", fixture_video)
    h2 = storage.add_video("myproject", fixture_video)
    assert h1 == h2
    manifest_path = storage.get_project_path("myproject") / "videos" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest["videos"]) == 1


def test_add_video_creates_hash_subdir(storage, fixture_video):
    storage.create_project("myproject", [])
    video_hash = storage.add_video("myproject", fixture_video)
    hash_dir = storage.get_project_path("myproject") / "videos" / video_hash
    assert hash_dir.is_dir()


# ── is_step_current / mark_step_complete ──────────────────────────────────────

def test_is_step_current_false_when_null(storage, settings, fixture_video):
    storage.create_project("myproject", [fixture_video])
    video_hash = hash_video_file(fixture_video)
    assert storage.is_step_current("myproject", video_hash, "optical_flow", settings) is False


def test_is_step_current_true_after_mark(storage, settings, fixture_video):
    storage.create_project("myproject", [fixture_video])
    video_hash = hash_video_file(fixture_video)
    storage.mark_step_complete("myproject", video_hash, "optical_flow", settings)
    assert storage.is_step_current("myproject", video_hash, "optical_flow", settings) is True


def test_is_step_current_false_when_config_hash_differs(storage, settings, fixture_video):
    storage.create_project("myproject", [fixture_video])
    video_hash = hash_video_file(fixture_video)
    storage.mark_step_complete("myproject", video_hash, "optical_flow", settings)

    # Produce a settings object with different config_hash.
    new_ds = settings.video.downsample.model_copy(update={"target_fps": 1.0})
    changed = settings.model_copy(
        update={"video": settings.video.model_copy(update={"downsample": new_ds})}
    )
    assert storage.is_step_current("myproject", video_hash, "optical_flow", changed) is False


# ── save_json / load_json ─────────────────────────────────────────────────────

def test_save_load_pydantic_model(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    config = ProcessingConfig(target_fps=2.0, target_width=320)
    storage.save_json("myproject", "analysis/config.json", config)
    loaded = storage.load_json("myproject", "analysis/config.json", ProcessingConfig)
    assert loaded.target_fps == 2.0
    assert loaded.target_width == 320


def test_save_load_list_of_models(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    configs = [ProcessingConfig(target_fps=1.0), ProcessingConfig(target_fps=2.0)]
    storage.save_json("myproject", "analysis/configs.json", configs)
    loaded = storage.load_json("myproject", "analysis/configs.json", ProcessingConfig)
    assert len(loaded) == 2
    assert loaded[0].target_fps == 1.0


def test_save_load_dict(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    data = {"key": "value", "num": 42}
    storage.save_json("myproject", "analysis/meta.json", data)
    loaded = storage.load_json("myproject", "analysis/meta.json")
    assert loaded == data


def test_load_json_missing_raises(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    with pytest.raises(FileNotFoundError):
        storage.load_json("myproject", "analysis/nonexistent.json")


def test_save_json_nested_path(storage, fixture_video):
    """save_json should create intermediate dirs automatically."""
    storage.create_project("myproject", [fixture_video])
    storage.save_json("myproject", "videos/abc123/flow/metrics.json", {"frames": 10})
    loaded = storage.load_json("myproject", "videos/abc123/flow/metrics.json")
    assert loaded["frames"] == 10


# ── save_versioned ────────────────────────────────────────────────────────────

def test_save_versioned_first_is_v1(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    from core.schemas.storyboard import Storyboard
    v = storage.save_versioned("myproject", "storyboard", Storyboard())
    assert v == 1
    assert (storage.get_project_path("myproject") / "storyboard" / "v1.json").exists()


def test_save_versioned_increments(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    from core.schemas.storyboard import Storyboard
    sb = Storyboard()
    v1 = storage.save_versioned("myproject", "storyboard", sb)
    v2 = storage.save_versioned("myproject", "storyboard", sb)
    v3 = storage.save_versioned("myproject", "storyboard", sb)
    assert v1 == 1
    assert v2 == 2
    assert v3 == 3


def test_save_versioned_latest_symlink(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    from core.schemas.storyboard import Storyboard
    storage.save_versioned("myproject", "storyboard", Storyboard())
    storage.save_versioned("myproject", "storyboard", Storyboard())
    symlink = storage.get_project_path("myproject") / "storyboard" / "latest.json"
    assert symlink.is_symlink()
    assert symlink.resolve().name == "v2.json"


# ── list_projects / get_project ───────────────────────────────────────────────

def test_list_projects_empty(storage):
    assert storage.list_projects() == []


def test_list_projects_returns_created(storage, fixture_video):
    storage.create_project("alpha", [fixture_video])
    storage.create_project("beta", [fixture_video])
    names = {p.name for p in storage.list_projects()}
    assert "alpha" in names
    assert "beta" in names


def test_get_project_by_name(storage, fixture_video):
    storage.create_project("myproject", [fixture_video])
    project = storage.get_project("myproject")
    assert project.name == "myproject"


def test_save_project_updates_status(storage, fixture_video):
    project = storage.create_project("myproject", [fixture_video])
    project.status = ProjectStatus.ready
    storage.save_project(project)
    loaded = storage.get_project("myproject")
    assert loaded.status == ProjectStatus.ready
