import numpy as np
import pytest
from video.optical_flow import compute_flow, resize_for_flow
from video.homography import fit_homography, decompose_homography, decompose_flow


def _zero_flow(h: int = 100, w: int = 160) -> np.ndarray:
    return np.zeros((h, w, 2), dtype=np.float32)


def test_fit_homography_identity():
    """Near-zero flow → homography should be close to identity."""
    flow = _zero_flow()
    H_mat, inlier_ratio = fit_homography(flow)
    assert H_mat is not None
    assert inlier_ratio > 0.9
    # Translation should be near zero
    assert abs(H_mat[0, 2]) < 1.0
    assert abs(H_mat[1, 2]) < 1.0
    # Scale should be near 1
    scale = np.sqrt(H_mat[0, 0] ** 2 + H_mat[1, 0] ** 2)
    assert abs(scale - 1.0) < 0.1


def test_decompose_homography_no_motion():
    """Decomposing an identity homography → all primitives near zero."""
    H_eye = np.eye(3, dtype=np.float64)
    result = decompose_homography(H_eye, frame_shape=(100, 160))
    assert abs(result["pan"]) < 1e-6
    assert abs(result["tilt"]) < 1e-6
    assert abs(result["roll"]) < 1e-4
    assert abs(result["zoom"]) < 1e-6


def test_decompose_flow_returns_none_on_constant_flow():
    """Constant non-zero flow is a pure translation — RANSAC should still fit."""
    flow = np.ones((100, 160, 2), dtype=np.float32) * 2.0
    result = decompose_flow(flow)
    # With a clean constant translation RANSAC should succeed
    assert result is not None
    assert "pan" in result
    assert "tilt" in result
    assert "zoom" in result
    assert "camera_magnitude" in result
    assert "scene_activity" in result


def test_decompose_flow_on_real_frames(two_frames):
    f1, f2 = two_frames
    from video.optical_flow import resize_for_flow, compute_flow
    g1 = resize_for_flow(f1)
    g2 = resize_for_flow(f2)
    flow = compute_flow(g1, g2)
    result = decompose_flow(flow)
    # RANSAC should succeed on a real video pair
    assert result is not None
    for key in ("pan", "tilt", "roll", "zoom", "camera_magnitude", "scene_activity"):
        assert key in result
        assert np.isfinite(result[key])


def test_inlier_ratio_range(two_frames):
    f1, f2 = two_frames
    from video.optical_flow import resize_for_flow, compute_flow
    g1 = resize_for_flow(f1)
    g2 = resize_for_flow(f2)
    flow = compute_flow(g1, g2)
    _, inlier_ratio = fit_homography(flow)
    assert 0.0 <= inlier_ratio <= 1.0
