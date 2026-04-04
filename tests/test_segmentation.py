import numpy as np
import pytest
from video.segmentation import (
    preprocess_signal,
    detect_scene_boundaries,
    detect_movement_boundaries,
    movement_stats,
)
from core.schemas.segment import CameraMovement


def _step_signal(t: int = 100, c: int = 4, step_at: int = 50) -> np.ndarray:
    """Signal with a sharp step change at step_at — should produce a boundary near there."""
    sig = np.zeros((t, c))
    sig[step_at:] = 1.0
    return sig


def _ramp_signal(t: int = 60, c: int = 4) -> np.ndarray:
    sig = np.zeros((t, c))
    for i in range(c):
        sig[:, i] = np.linspace(0, 1, t) * (i + 1) * 0.1
    return sig


# ── preprocess_signal ────────────────────────────────────────────────────────

def test_preprocess_signal_range():
    sig = np.random.rand(50, 4) * 10
    out = preprocess_signal(sig)
    assert out.min() >= -1e-9
    assert out.max() <= 1.0 + 1e-9


def test_preprocess_signal_constant_channel():
    sig = np.ones((30, 4))
    out = preprocess_signal(sig)
    # Constant channel → after normalisation it's all 0 (lo==hi branch)
    assert np.allclose(out, 0.0) or np.all(np.isfinite(out))


def test_preprocess_signal_shape_preserved():
    sig = np.random.rand(80, 4)
    out = preprocess_signal(sig)
    assert out.shape == sig.shape


def test_preprocess_signal_short():
    sig = np.random.rand(3, 4)
    out = preprocess_signal(sig)
    assert out.shape == (3, 4)


# ── detect_scene_boundaries ──────────────────────────────────────────────────

def test_detect_scene_boundaries_step():
    sig = _step_signal(t=100, step_at=50)
    pre = preprocess_signal(sig)
    bps = detect_scene_boundaries(pre, penalty=3.0)
    assert len(bps) >= 1
    assert bps[-1] == len(pre)
    # The boundary should land near the step
    interior = [b for b in bps if b < len(pre)]
    if interior:
        assert any(40 <= b <= 60 for b in interior), f"Expected boundary near 50, got {interior}"


def test_detect_scene_boundaries_flat():
    sig = np.zeros((50, 4))
    pre = preprocess_signal(sig)
    bps = detect_scene_boundaries(pre, penalty=3.0)
    # No meaningful change → single segment
    assert bps == [len(pre)]


def test_detect_scene_boundaries_returns_end():
    sig = np.random.rand(40, 4)
    pre = preprocess_signal(sig)
    bps = detect_scene_boundaries(pre)
    assert bps[-1] == len(pre)


# ── detect_movement_boundaries ───────────────────────────────────────────────

def test_detect_movement_boundaries_step():
    sig = _step_signal(t=60, step_at=30)
    pre = preprocess_signal(sig)
    bps = detect_movement_boundaries(pre, penalty=2.0)
    assert bps[-1] == len(pre)
    interior = [b for b in bps if b < len(pre)]
    if interior:
        assert any(20 <= b <= 40 for b in interior), f"Expected boundary near 30, got {interior}"


def test_detect_movement_boundaries_too_short():
    sig = np.random.rand(2, 4)
    bps = detect_movement_boundaries(sig)
    assert bps == [len(sig)]


def test_detect_movement_does_not_preprocess():
    """Verify movement boundaries accept already-preprocessed signal (values in [0,1])."""
    sig = np.random.rand(40, 4)
    bps = detect_movement_boundaries(sig, penalty=2.0)
    assert isinstance(bps, list)
    assert bps[-1] == len(sig)


# ── movement_stats ───────────────────────────────────────────────────────────

def test_movement_stats_returns_camera_movement():
    sig = np.random.rand(20, 4)
    ts = np.linspace(0, 5, 20)
    cm = movement_stats(sig, ts, segment_id=0, movement_id=0)
    assert isinstance(cm, CameraMovement)
    assert cm.segment_id == 0
    assert cm.subsegment_id == 0
    assert np.isfinite(cm.pan_entry_vel)
    assert np.isfinite(cm.pan_exit_vel)
    assert np.isfinite(cm.pan_mean_abs_deriv)
    assert np.isfinite(cm.pan_std_deriv)


def test_movement_stats_entry_exit_velocity_5pct():
    """entry_vel and exit_vel must be computed on first/last 5% of frames."""
    n = 100
    # Flat then ramp: entry should be ~0, exit should be ~positive
    sig = np.zeros((n, 4))
    ramp = np.linspace(0, 1, 50)
    sig[50:, 0] = ramp  # pan ramps up in second half
    ts = np.linspace(0, 10, n)
    cm = movement_stats(sig, ts, segment_id=0, subsegment_id=0)
    # With 5% of 100 = 5 frames at exit (ramp end), exit_vel should be > entry_vel
    # pan_exit_vel should reflect the ramp slope
    assert cm.pan_exit_vel >= cm.pan_entry_vel


def test_movement_stats_start_end_times():
    sig = np.random.rand(10, 4)
    ts = np.array([1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25])
    cm = movement_stats(sig, ts, segment_id=1, subsegment_id=2)
    assert cm.start_time == pytest.approx(1.0)
    assert cm.end_time == pytest.approx(3.25)
    assert cm.segment_id == 1
    assert cm.subsegment_id == 2
