from pathlib import Path

import pytest

from video.ingest import VideoIngestError, probe_video
from core.schemas.video import VideoFile

FIXTURE = Path(__file__).parent.parent / "fixtures" / "video_fixture.mov"


@pytest.fixture
def fixture_video():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE}")
    return FIXTURE


def test_probe_returns_video_file(fixture_video):
    vf = probe_video(fixture_video)
    assert isinstance(vf, VideoFile)


def test_probe_dimensions(fixture_video):
    vf = probe_video(fixture_video)
    assert vf.width == 1920
    assert vf.height == 1080


def test_probe_duration_positive(fixture_video):
    vf = probe_video(fixture_video)
    assert vf.duration > 0.0


def test_probe_fps_positive(fixture_video):
    vf = probe_video(fixture_video)
    assert vf.fps > 0.0


def test_probe_codec_populated(fixture_video):
    vf = probe_video(fixture_video)
    assert vf.codec != ""
    assert vf.codec != "unknown"


def test_probe_path_stored(fixture_video):
    vf = probe_video(fixture_video)
    assert vf.path == fixture_video


def test_probe_file_not_found():
    with pytest.raises(VideoIngestError, match="not found"):
        probe_video(Path("/nonexistent/path/to/video.mp4"))


def test_probe_not_a_video(tmp_path):
    bad = tmp_path / "notavideo.txt"
    bad.write_text("hello")
    with pytest.raises(VideoIngestError):
        probe_video(bad)
