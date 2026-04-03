from pathlib import Path

import pytest

from video.downsample import DownsampleError, downsample_video
from video.ingest import probe_video
from core.schemas.video import ProcessingConfig

FIXTURE = Path(__file__).parent.parent / "fixtures" / "video_fixture.mov"


@pytest.fixture
def fixture_video():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE}")
    return FIXTURE


def test_downsample_creates_output(fixture_video, tmp_path):
    out = tmp_path / "out.mp4"
    config = ProcessingConfig(target_fps=2.0, target_width=320)
    result = downsample_video(fixture_video, out, config)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0


def test_downsample_target_fps(fixture_video, tmp_path):
    out = tmp_path / "out.mp4"
    config = ProcessingConfig(target_fps=2.0, target_width=320)
    downsample_video(fixture_video, out, config)
    vf = probe_video(out)
    # Allow ±0.5 fps tolerance due to codec rounding
    assert abs(vf.fps - 2.0) < 0.5


def test_downsample_target_width(fixture_video, tmp_path):
    out = tmp_path / "out.mp4"
    config = ProcessingConfig(target_fps=2.0, target_width=320)
    downsample_video(fixture_video, out, config)
    vf = probe_video(out)
    assert vf.width == 320


def test_downsample_aspect_ratio_preserved(fixture_video, tmp_path):
    out = tmp_path / "out.mp4"
    original = probe_video(fixture_video)
    config = ProcessingConfig(target_fps=2.0, target_width=320)
    downsample_video(fixture_video, out, config)
    vf = probe_video(out)
    original_ratio = original.width / original.height
    output_ratio = vf.width / vf.height
    assert abs(original_ratio - output_ratio) < 0.05


def test_downsample_invalid_input(tmp_path):
    out = tmp_path / "out.mp4"
    config = ProcessingConfig(target_fps=4.0, target_width=320)
    with pytest.raises(DownsampleError, match="not found"):
        downsample_video(Path("/nonexistent/video.mp4"), out, config)
