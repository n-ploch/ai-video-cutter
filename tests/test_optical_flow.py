import numpy as np
import pytest
from video.optical_flow import compute_flow, flow_statistics, resize_for_flow


def test_resize_for_flow(two_frames):
    f1, _ = two_frames
    result = resize_for_flow(f1, max_width=640)
    assert result.ndim == 2, "resize_for_flow should return grayscale (2D)"
    assert result.shape[1] <= 640


def test_resize_for_flow_smaller_width(two_frames):
    f1, _ = two_frames
    result = resize_for_flow(f1, max_width=320)
    assert result.shape[1] <= 320


def test_compute_flow_shape(two_frames):
    f1, f2 = two_frames
    g1 = resize_for_flow(f1)
    g2 = resize_for_flow(f2)
    flow = compute_flow(g1, g2)
    assert flow.shape == (*g1.shape, 2), f"Expected shape {(*g1.shape, 2)}, got {flow.shape}"


def test_compute_flow_dtype(two_frames):
    f1, f2 = two_frames
    g1 = resize_for_flow(f1)
    g2 = resize_for_flow(f2)
    flow = compute_flow(g1, g2)
    assert flow.dtype == np.float32


def test_flow_statistics_range(two_frames):
    f1, f2 = two_frames
    g1 = resize_for_flow(f1)
    g2 = resize_for_flow(f2)
    flow = compute_flow(g1, g2)
    mag, direction, coherence = flow_statistics(flow)
    assert mag >= 0.0, "magnitude must be non-negative"
    assert 0.0 <= coherence <= 1.0, f"coherence must be in [0,1], got {coherence}"
    assert -np.pi <= direction <= np.pi, "direction must be in [-pi, pi]"


def test_flow_statistics_zero_flow():
    # Identical frames → near-zero flow → near-zero magnitude
    gray = np.zeros((100, 100), dtype=np.uint8)
    flow = compute_flow(gray, gray)
    mag, _, coherence = flow_statistics(flow)
    assert mag < 0.1
    # coherence can be anything for zero flow; just check it's in range
    assert 0.0 <= coherence <= 1.0
