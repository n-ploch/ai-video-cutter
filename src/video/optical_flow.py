from __future__ import annotations

import cv2
import numpy as np


def resize_for_flow(frame_bgr: np.ndarray, max_width: int = 640) -> np.ndarray:
    """Resize frame and convert to grayscale for flow computation."""
    h, w = frame_bgr.shape[:2]
    scale = max_width / w
    new_h = int(h * scale)
    resized = cv2.resize(frame_bgr, (max_width, new_h))
    return cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)


def compute_flow(
    prev_gray: np.ndarray,
    curr_gray: np.ndarray,
    pyr_scale: float = 0.5,
    levels: int = 3,
    winsize: int = 15,
    iterations: int = 3,
    poly_n: int = 5,
    poly_sigma: float = 1.2,
) -> np.ndarray:
    """Farneback dense optical flow. Returns array of shape (H, W, 2)."""
    return cv2.calcOpticalFlowFarneback(
        prev_gray, curr_gray, None,
        pyr_scale=pyr_scale,
        levels=levels,
        winsize=winsize,
        iterations=iterations,
        poly_n=poly_n,
        poly_sigma=poly_sigma,
        flags=0,
    )


def flow_statistics(flow: np.ndarray) -> tuple[float, float, float]:
    """
    Compute summary statistics from a dense flow field.

    Returns (mean_magnitude, dominant_direction_rad, coherence).
    coherence ∈ [0, 1]: 1 = perfectly uniform motion direction.
    """
    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    mean_mag = float(mag.mean())
    dx_mean = float(np.cos(ang).mean())
    dy_mean = float(np.sin(ang).mean())
    dominant_dir = float(np.arctan2(dy_mean, dx_mean))
    coherence = float(np.sqrt(dx_mean ** 2 + dy_mean ** 2))
    return mean_mag, dominant_dir, coherence
