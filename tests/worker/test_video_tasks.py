"""Tests for video pipeline Celery tasks and manifest state integrity.

Focus: manifest steps remain None on task failure; storage API semantics.
No real video required — pipeline steps are mocked where needed.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_storage(tmp_path: Path):
    """Return a ProjectStorage backed by tmp_path."""
    from core.storage import ProjectStorage
    from core.storage_local import LocalBackend

    root = tmp_path / "storage"
    root.mkdir()
    return ProjectStorage(root=root, backend=LocalBackend(root))


def _seed_manifest(storage, project_name: str, video_hash: str) -> None:
    """Write a minimal manifest with all processing steps null."""
    project_dir = storage.root / project_name
    (project_dir / "videos").mkdir(parents=True, exist_ok=True)

    manifest = {
        "videos": {
            video_hash: {
                "original_path": "/fake/video.mp4",
                "storage_key": f"{project_name}/videos/{video_hash}/original.mp4",
                "filename": "video.mp4",
                "hash": video_hash,
                "added_at": "2026-01-01T00:00:00+00:00",
                "processing": {
                    "probed": None,
                    "downsampled": None,
                    "optical_flow": None,
                    "segmented": None,
                    "described": None,
                },
                "config_hash": None,
            }
        }
    }
    (project_dir / "videos" / "manifest.json").write_text(json.dumps(manifest))


def _read_manifest(storage, project_name: str) -> dict:
    return json.loads((storage.root / project_name / "videos" / "manifest.json").read_text())


# ── Manifest / storage API ────────────────────────────────────────────────────

def test_is_step_current_false_when_step_null(tmp_path):
    """is_step_current() returns False when the processing step timestamp is None."""
    storage = _make_storage(tmp_path)
    _seed_manifest(storage, "proj", "abc123")

    cfg = MagicMock()
    cfg.config_hash = "hash-A"

    assert not storage.is_step_current("proj", "abc123", "optical_flow", cfg)
    assert not storage.is_step_current("proj", "abc123", "segmented", cfg)
    assert not storage.is_step_current("proj", "abc123", "described", cfg)


def test_is_step_current_false_on_config_mismatch(tmp_path):
    """is_step_current() returns False when config_hash differs (stale run)."""
    storage = _make_storage(tmp_path)
    _seed_manifest(storage, "proj", "abc123")

    cfg_a = MagicMock()
    cfg_a.config_hash = "hash-A"
    cfg_b = MagicMock()
    cfg_b.config_hash = "hash-B"

    # Mark complete with config A
    storage.mark_step_complete("proj", "abc123", "optical_flow", cfg_a)

    # Same config → current
    assert storage.is_step_current("proj", "abc123", "optical_flow", cfg_a)
    # Different config → not current (force reanalyze scenario)
    assert not storage.is_step_current("proj", "abc123", "optical_flow", cfg_b)


def test_mark_step_complete_sets_timestamp(tmp_path):
    """mark_step_complete() records a non-null ISO timestamp for the step."""
    storage = _make_storage(tmp_path)
    _seed_manifest(storage, "proj", "abc123")

    cfg = MagicMock()
    cfg.config_hash = "hash-X"
    storage.mark_step_complete("proj", "abc123", "optical_flow", cfg)

    manifest = _read_manifest(storage, "proj")
    entry = manifest["videos"]["abc123"]
    assert entry["processing"]["optical_flow"] is not None
    # Other steps remain null
    assert entry["processing"]["segmented"] is None
    assert entry["processing"]["described"] is None


def test_add_video_idempotent(tmp_path):
    """add_video() is safe to call twice with the same file hash."""
    from core.storage import ProjectStorage
    from core.storage_local import LocalBackend

    root = tmp_path / "storage"
    root.mkdir()
    storage = ProjectStorage(root=root, backend=LocalBackend(root))

    # Seed minimal project structure
    project_dir = root / "proj"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "videos" / "manifest.json").write_text(json.dumps({"videos": {}}))

    # Create a fake video file with known content
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"FAKE" * 1024)

    hash1 = storage.add_video("proj", fake_video)
    hash2 = storage.add_video("proj", fake_video)

    assert hash1 == hash2  # same hash
    manifest = _read_manifest(storage, "proj")
    assert len(manifest["videos"]) == 1  # no duplicate entry


def test_add_video_creates_hash_folder(tmp_path):
    """add_video() creates the videos/{hash}/ directory."""
    from core.storage import ProjectStorage
    from core.storage_local import LocalBackend

    root = tmp_path / "storage"
    root.mkdir()
    storage = ProjectStorage(root=root, backend=LocalBackend(root))

    project_dir = root / "proj"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "videos" / "manifest.json").write_text(json.dumps({"videos": {}}))

    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"DATA" * 2048)

    video_hash = storage.add_video("proj", fake_video)
    assert (root / "proj" / "videos" / video_hash).is_dir()


# ── Task failure → manifest stays null ───────────────────────────────────────

def _fake_local_path_cm(fake_path: Path):
    """Return a function that acts as storage.backend.local_path, yielding fake_path."""
    @contextmanager
    def _cm(key: str):
        yield fake_path
    return _cm


def _make_mock_settings():
    s = MagicMock()
    s.video.downsample.target_fps = 5.0
    s.video.downsample.target_width = 320
    s.video.downsample.output_format = "mp4"
    s.video.hwaccel = None
    s.video.optical_flow.target_fps = 5.0
    s.video.segmentation.fd_penalty = 3.0
    s.video.segmentation.subseg_penalty = 2.0
    s.video.segmentation.savgol_window = 5
    s.video.segmentation.savgol_poly = 2
    return s


def test_optical_flow_failure_mark_step_never_called(tmp_path):
    """When OpticalFlowStep.run raises, mark_step_complete is never called."""
    # A real (but empty) file so check_inputs passes the "exists" check
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"\x00" * 16)

    mock_storage = MagicMock()
    mock_storage.backend.local_path = _fake_local_path_cm(fake_video)

    mock_settings = _make_mock_settings()

    prev = {
        "project_name": "proj",
        "video_hash": "abc123",
        "video_storage_key": "proj/videos/abc123/original.mp4",
        "downsampled_key": "proj/videos/abc123/downsampled.mp4",
    }

    from worker.video_tasks import task_flow_and_segment
    with patch("worker.video_tasks._get_storage_and_settings", return_value=(mock_storage, mock_settings, MagicMock())):
        with patch("video.pipeline.OpticalFlowStep.run", side_effect=RuntimeError("flow exploded")):
            with patch.object(task_flow_and_segment, "update_state"):
                with pytest.raises(RuntimeError, match="flow exploded"):
                    task_flow_and_segment.run(prev)

    mock_storage.mark_step_complete.assert_not_called()


def test_segmentation_failure_mark_step_never_called(tmp_path):
    """When SegmentScenesStep.run raises, mark_step_complete is never called."""
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"\x00" * 16)

    mock_storage = MagicMock()
    mock_storage.backend.local_path = _fake_local_path_cm(fake_video)
    mock_settings = _make_mock_settings()

    prev = {
        "project_name": "proj",
        "video_hash": "abc123",
        "video_storage_key": "proj/videos/abc123/original.mp4",
        "downsampled_key": "proj/videos/abc123/downsampled.mp4",
    }

    from worker.video_tasks import task_flow_and_segment
    with patch("worker.video_tasks._get_storage_and_settings", return_value=(mock_storage, mock_settings, MagicMock())):
        # Let flow pass, fail on segmentation
        with patch("video.pipeline.OpticalFlowStep.run", return_value=MagicMock()):
            with patch("video.pipeline.PreprocessSignalStep.run", return_value=MagicMock()):
                with patch("video.pipeline.SegmentScenesStep.run", side_effect=RuntimeError("seg exploded")):
                    with patch.object(task_flow_and_segment, "update_state"):
                        with pytest.raises(RuntimeError, match="seg exploded"):
                            task_flow_and_segment.run(prev)

    mock_storage.mark_step_complete.assert_not_called()


def test_vlm_global_failure_described_stays_null(tmp_path):
    """When task_vlm_global raises before dispatching the chord, mark_step_complete
    for 'described' is never called — the chord never starts, collect never runs."""
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"\x00" * 16)

    mock_storage = MagicMock()
    mock_storage.backend.local_path = _fake_local_path_cm(fake_video)
    mock_storage.load_json.return_value = []  # empty segments list
    mock_settings = MagicMock()

    prev = {
        "project_name": "proj",
        "video_hash": "abc123",
        "video_storage_key": "proj/videos/abc123/original.mp4",
        "downsampled_key": "proj/videos/abc123/downsampled.mp4",
    }

    from worker.vlm_tasks import task_vlm_global
    with patch("worker.vlm_tasks._get_storage_and_settings", return_value=(mock_storage, mock_settings)):
        with patch("worker.vlm_tasks.create_vlm_backend", return_value=MagicMock()):
            with patch("worker.vlm_tasks._analyze_global", side_effect=RuntimeError("vlm exploded")):
                with patch.object(task_vlm_global, "update_state"):
                    with pytest.raises(RuntimeError, match="vlm exploded"):
                        task_vlm_global.run(prev)

    # mark_step_complete should never have been called for "described"
    for call_args in mock_storage.mark_step_complete.call_args_list:
        assert "described" not in call_args.args
