import math
from pathlib import Path

import numpy as np
import pytest

from video.frames import extract_frame, stream_frames
from video.ingest import probe_video
from core.schemas.video import ProcessingConfig

FIXTURE = Path(__file__).parent.parent / "fixtures" / "video_fixture.mov"


@pytest.fixture
def fixture_video():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE}")
    return FIXTURE


@pytest.fixture
def config():
    return ProcessingConfig(target_fps=4.0, target_width=320)


def test_stream_frames_yields_tuples(fixture_video, config):
    frames = list(stream_frames(fixture_video, config))
    assert len(frames) > 0
    idx, ts, arr = frames[0]
    assert isinstance(idx, int)
    assert isinstance(ts, float)
    assert isinstance(arr, np.ndarray)


def test_stream_frames_shape(fixture_video, config):
    frames = list(stream_frames(fixture_video, config))
    _, _, arr = frames[0]
    assert arr.ndim == 3
    assert arr.shape[2] == 3          # BGR channels
    assert arr.shape[1] == config.target_width


def test_stream_frames_dtype(fixture_video, config):
    frames = list(stream_frames(fixture_video, config))
    _, _, arr = frames[0]
    assert arr.dtype == np.uint8


def test_stream_frames_count(fixture_video, config):
    info = probe_video(fixture_video)
    frames = list(stream_frames(fixture_video, config))
    expected = int(info.duration * config.target_fps)
    # ffmpeg may produce ±1 frame due to rounding
    assert abs(len(frames) - expected) <= 2


def test_stream_frames_timestamps_increasing(fixture_video, config):
    frames = list(stream_frames(fixture_video, config))
    timestamps = [ts for _, ts, _ in frames]
    assert all(t2 > t1 for t1, t2 in zip(timestamps, timestamps[1:]))


def test_stream_frames_frame_indices(fixture_video, config):
    frames = list(stream_frames(fixture_video, config))
    indices = [idx for idx, _, _ in frames]
    assert indices == list(range(len(frames)))


def test_extract_frame_shape(fixture_video):
    frame = extract_frame(fixture_video, timestamp=1.0, width=320)
    assert frame.ndim == 3
    assert frame.shape[2] == 3
    assert frame.shape[1] == 320


def test_extract_frame_dtype(fixture_video):
    frame = extract_frame(fixture_video, timestamp=1.0, width=320)
    assert frame.dtype == np.uint8
