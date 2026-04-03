"""
Pipeline tests — kept sparse per spec.
Integration test covers the full default pipeline on the fixture video.
Unit tests cover step input validation (check_inputs contracts).
"""
from pathlib import Path

import numpy as np
import pytest

from core.schemas.video import ProcessingConfig, SegmentationConfig
from video.pipeline import (
    OpticalFlowStep,
    Pipeline,
    PipelineContext,
    PipelineStepError,
    PreprocessSignalStep,
    SegmentScenesStep,
    default_pipeline,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "video_fixture.mov"


@pytest.fixture
def fixture_video():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE}")
    return FIXTURE


@pytest.fixture
def fast_config():
    return ProcessingConfig(target_fps=2.0, target_width=320)


@pytest.fixture
def seg_config():
    return SegmentationConfig(fd_penalty=3.0, subseg_penalty=2.0, savgol_window=5, savgol_poly=2)


# ── Integration ───────────────────────────────────────────────────────────────

def test_default_pipeline_integration(fixture_video, fast_config, seg_config):
    ctx = default_pipeline(fast_config, seg_config).run(fixture_video)

    assert len(ctx.frame_metrics) > 0, "expected frame metrics"
    assert ctx.raw_signal is not None and len(ctx.raw_signal) > 0
    assert ctx.preprocessed_signal is not None
    assert len(ctx.segments) > 0, "expected at least one segment"
    # project_id is None when no storage is passed — that's fine
    assert ctx.project_id is None


def test_pipeline_stops_after_flow(fixture_video, fast_config):
    ctx = Pipeline([OpticalFlowStep(fast_config)]).run(fixture_video)

    assert ctx.raw_signal is not None
    assert len(ctx.frame_metrics) > 0
    assert ctx.preprocessed_signal is None  # not set
    assert ctx.segments == []               # not set


def test_segment_scenes_on_raw_signal(fixture_video, fast_config, seg_config):
    """SegmentScenesStep with signal_source='raw' works without PreprocessSignalStep."""
    ctx = Pipeline([
        OpticalFlowStep(fast_config),
        SegmentScenesStep(seg_config, signal_source="raw"),
    ]).run(fixture_video)

    assert len(ctx.segments) > 0
    assert ctx.preprocessed_signal is None  # never set


def test_pipeline_resume_reuses_flow(fixture_video, fast_config, seg_config):
    """resume() lets a second pipeline use the flow computed by the first."""
    ctx = Pipeline([OpticalFlowStep(fast_config)]).run(fixture_video)

    ctx2 = Pipeline([
        PreprocessSignalStep(seg_config),
        SegmentScenesStep(seg_config),
    ]).resume(ctx)

    assert ctx2.raw_signal is ctx.raw_signal   # same object — not re-computed
    assert len(ctx2.segments) > 0


# ── Input validation (check_inputs contracts) ─────────────────────────────────

def _empty_ctx(video_path=Path("/fake/video.mov")) -> PipelineContext:
    return PipelineContext(video_path=video_path)


def test_preprocess_step_raises_without_raw_signal():
    ctx = _empty_ctx()
    with pytest.raises(PipelineStepError, match="raw_signal"):
        PreprocessSignalStep(SegmentationConfig()).check_inputs(ctx)


def test_preprocess_step_raises_on_single_row():
    ctx = _empty_ctx()
    ctx.raw_signal = np.zeros((1, 4))
    with pytest.raises(PipelineStepError, match="≥ 2"):
        PreprocessSignalStep(SegmentationConfig()).check_inputs(ctx)


def test_segment_step_raises_without_preprocessed():
    ctx = _empty_ctx()
    ctx.timestamps = np.array([1.0, 2.0])
    with pytest.raises(PipelineStepError, match="preprocessed_signal"):
        SegmentScenesStep(SegmentationConfig(), signal_source="preprocessed").check_inputs(ctx)


def test_segment_step_raises_without_raw():
    ctx = _empty_ctx()
    ctx.timestamps = np.array([1.0, 2.0])
    with pytest.raises(PipelineStepError, match="raw_signal"):
        SegmentScenesStep(SegmentationConfig(), signal_source="raw").check_inputs(ctx)


def test_segment_step_raises_without_timestamps():
    ctx = _empty_ctx()
    ctx.preprocessed_signal = np.zeros((10, 4))
    with pytest.raises(PipelineStepError, match="timestamps"):
        SegmentScenesStep(SegmentationConfig(), signal_source="preprocessed").check_inputs(ctx)


def test_segment_step_raises_on_unknown_source():
    ctx = _empty_ctx()
    with pytest.raises(PipelineStepError, match="Unknown signal_source"):
        SegmentScenesStep(SegmentationConfig(), signal_source="invalid").check_inputs(ctx)  # type: ignore


def test_optical_flow_step_raises_on_missing_file():
    ctx = _empty_ctx(Path("/nonexistent/video.mov"))
    with pytest.raises(PipelineStepError, match="not found"):
        OpticalFlowStep(ProcessingConfig()).check_inputs(ctx)
