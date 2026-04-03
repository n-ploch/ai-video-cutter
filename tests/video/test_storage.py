from pathlib import Path

import pytest

from core.project import Project, ProjectStatus
from core.schemas.video import VideoFile, ProcessingConfig
from core.storage import ProjectStorage

FIXTURE = Path(__file__).parent.parent / "fixtures" / "video_fixture.mov"


@pytest.fixture
def storage(tmp_path):
    return ProjectStorage(root=tmp_path / "projects")


@pytest.fixture
def fixture_video():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE}")
    return FIXTURE


# ── create_project ────────────────────────────────────────────────────────────

def test_create_project_returns_project(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    assert isinstance(project, Project)
    assert project.name == "test"
    assert len(project.video_files) == 1


def test_create_project_folder_structure(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    project_dir = storage.get_project_path(project.id)
    for subfolder in ("sources", "analysis", "storyboard", "timeline"):
        assert (project_dir / subfolder).is_dir()


def test_create_project_manifest_written(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    manifest = storage.get_project_path(project.id) / "project.json"
    assert manifest.exists()


def test_create_project_status_created(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    assert project.status == ProjectStatus.created


# ── save_json / load_json ─────────────────────────────────────────────────────

def test_save_load_pydantic_model(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    config = ProcessingConfig(target_fps=2.0, target_width=320)
    storage.save_json(project.id, "config", config)
    loaded = storage.load_json(project.id, "config", ProcessingConfig)
    assert loaded.target_fps == 2.0
    assert loaded.target_width == 320


def test_save_load_list_of_dicts(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    data = [{"a": 1, "b": 2.0}, {"a": 3, "b": 4.0}]
    storage.save_json(project.id, "mydata", data)
    loaded = storage.load_json(project.id, "mydata")
    assert loaded == data


def test_save_load_list_of_models(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    configs = [ProcessingConfig(target_fps=1.0), ProcessingConfig(target_fps=2.0)]
    storage.save_json(project.id, "configs", configs)
    loaded = storage.load_json(project.id, "configs", ProcessingConfig)
    assert len(loaded) == 2
    assert loaded[0].target_fps == 1.0
    assert loaded[1].target_fps == 2.0


def test_load_json_missing_key(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    with pytest.raises(FileNotFoundError):
        storage.load_json(project.id, "nonexistent")


# ── list_projects ─────────────────────────────────────────────────────────────

def test_list_projects_empty(storage):
    assert storage.list_projects() == []


def test_list_projects_returns_created(storage, fixture_video):
    p1 = storage.create_project("alpha", [fixture_video])
    p2 = storage.create_project("beta", [fixture_video])
    projects = storage.list_projects()
    ids = {p.id for p in projects}
    assert p1.id in ids
    assert p2.id in ids


# ── get_project ───────────────────────────────────────────────────────────────

def test_get_project_roundtrip(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    loaded = storage.get_project(project.id)
    assert loaded.id == project.id
    assert loaded.name == project.name


def test_save_project_updates_status(storage, fixture_video):
    project = storage.create_project("test", [fixture_video])
    project.status = ProjectStatus.ready
    storage.save_project(project)
    loaded = storage.get_project(project.id)
    assert loaded.status == ProjectStatus.ready
