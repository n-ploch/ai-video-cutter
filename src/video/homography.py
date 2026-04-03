from __future__ import annotations

import numpy as np
import cv2


def fit_homography(
    flow: np.ndarray,
    ransac_threshold: float = 2.0,
    sample_step: int = 4,
) -> tuple[np.ndarray | None, float]:
    """
    Fit a homography to a dense flow field via RANSAC.

    Uses a sparse grid (every sample_step pixels) to keep memory and compute
    proportional to frame size rather than O(N^2).

    Returns (H_mat, inlier_ratio). H_mat is None if RANSAC fails.
    """
    H, W = flow.shape[:2]
    coords = np.array(
        [[x, y] for y in range(0, H, sample_step) for x in range(0, W, sample_step)],
        dtype=np.float32,
    )
    dx = flow[::sample_step, ::sample_step, 0].flatten()
    dy = flow[::sample_step, ::sample_step, 1].flatten()

    if len(coords) < 4:
        return None, 0.0

    dst = coords + np.stack([dx, dy], axis=1)
    H_mat, inlier_mask = cv2.findHomography(
        coords, dst, cv2.RANSAC, ransacReprojThreshold=ransac_threshold
    )
    if H_mat is None or inlier_mask is None:
        return None, 0.0

    inlier_ratio = float(inlier_mask.sum() / len(inlier_mask))
    return H_mat, inlier_ratio


def decompose_homography(
    H_mat: np.ndarray,
    frame_shape: tuple[int, int],
) -> dict[str, float]:
    """
    Decompose a homography matrix into interpretable camera-motion primitives.

    Parameters
    ----------
    H_mat : 3x3 homography matrix
    frame_shape : (height, width) of the frame the homography was computed on

    Returns dict with keys: pan, tilt, roll, zoom, camera_magnitude, scene_activity.
      pan/tilt are normalised by frame dimensions.
      roll is in degrees.
      zoom = scale - 1 (0 = no zoom, positive = zoom in, negative = zoom out).
      camera_magnitude and scene_activity are placeholders (require flow to compute);
      call decompose_homography_with_flow for full decomposition.
    """
    frame_h, frame_w = frame_shape
    tx = float(H_mat[0, 2])
    ty = float(H_mat[1, 2])
    angle = float(np.arctan2(H_mat[1, 0], H_mat[0, 0]))
    scale = float(np.sqrt(H_mat[0, 0] ** 2 + H_mat[1, 0] ** 2))

    return {
        "pan": tx / frame_w,
        "tilt": ty / frame_h,
        "roll": float(np.degrees(angle)),
        "zoom": scale - 1.0,
    }


def decompose_flow(
    flow: np.ndarray,
    sample_step: int = 4,
    ransac_threshold: float = 2.0,
) -> dict[str, float] | None:
    """
    Full decomposition: fit homography to flow and extract all camera primitives
    plus scene_activity (residual flow after removing camera motion).

    Returns dict with keys: pan, tilt, roll, zoom, camera_magnitude, scene_activity,
    moving_object_ratio. Returns None if RANSAC fails.
    """
    H_frame, W_frame = flow.shape[:2]
    H_mat, inlier_ratio = fit_homography(flow, ransac_threshold, sample_step)
    if H_mat is None:
        return None

    coords = np.array(
        [[x, y] for y in range(0, H_frame, sample_step) for x in range(0, W_frame, sample_step)],
        dtype=np.float32,
    )
    dx = flow[::sample_step, ::sample_step, 0].flatten()
    dy = flow[::sample_step, ::sample_step, 1].flatten()

    coords_h = np.concatenate([coords, np.ones((len(coords), 1))], axis=1)
    warped = (H_mat @ coords_h.T).T
    warped = warped[:, :2] / warped[:, 2:3]
    camera_flow = warped - coords
    actual_flow = np.stack([dx, dy], axis=1)
    residual_flow = actual_flow - camera_flow

    primitives = decompose_homography(H_mat, (H_frame, W_frame))
    primitives["camera_magnitude"] = float(np.linalg.norm(camera_flow, axis=1).mean())
    primitives["scene_activity"] = float(np.linalg.norm(residual_flow, axis=1).mean())
    primitives["moving_object_ratio"] = float(1.0 - inlier_ratio)
    return primitives
