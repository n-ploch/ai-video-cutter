from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter
from scipy.stats import spearmanr
import ruptures as rpt

from core.schemas.segment import CameraMovement


# Signal column order — matches FD_SIGNAL_COLS in scripts/scene_selection.py
SIGNAL_COLS = ["pan", "tilt", "zoom", "camera_magnitude"]


def preprocess_signal(
    signal: np.ndarray,
    window: int = 11,
    poly: int = 2,
) -> np.ndarray:
    """
    Apply Savitzky-Golay smoothing then min-max normalise each channel.

    Parameters
    ----------
    signal : shape (T, C) raw signal
    window : SG filter window length (clamped to be ≤ T and odd)
    poly   : SG polynomial order

    Returns normalised copy of shape (T, C).
    """
    X = signal.astype(np.float64).copy()
    n = len(X)
    if n < 2:
        return X

    # Clamp window to valid odd value ≤ n
    win = min(window, n if n % 2 == 1 else n - 1)
    win = max(win, poly + 1 if (poly + 1) % 2 == 1 else poly + 2)

    for i in range(X.shape[1]):
        if n >= win:
            X[:, i] = savgol_filter(X[:, i], window_length=win, polyorder=poly)

    for i in range(X.shape[1]):
        lo, hi = X[:, i].min(), X[:, i].max()
        if hi - lo > 1e-8:
            X[:, i] = (X[:, i] - lo) / (hi - lo)

    return X


def detect_scene_boundaries(
    signal: np.ndarray,
    penalty: float = 3.0,
) -> list[int]:
    """
    Coarse scene segmentation via Ruptures Pelt(l2).

    Parameters
    ----------
    signal  : preprocessed signal, shape (T, C)
    penalty : Pelt penalty parameter

    Returns list of boundary indices (exclusive end positions, last element == T).
    """
    if len(signal) < 2:
        return [len(signal)]
    return rpt.Pelt(model="l2").fit(signal).predict(pen=penalty)


def detect_movement_boundaries(
    signal: np.ndarray,
    penalty: float = 2.0,
) -> list[int]:
    """
    Granular camera-movement segmentation via Ruptures Pelt(l1).

    Receives the already-preprocessed signal slice for one scene — does NOT
    preprocess again.

    Parameters
    ----------
    signal  : preprocessed signal slice, shape (T, C)
    penalty : Pelt penalty parameter

    Returns list of boundary indices (exclusive end positions, last element == T).
    """
    if len(signal) < 3:
        return [len(signal)]
    try:
        return rpt.Pelt(model="l1").fit(signal).predict(pen=penalty)
    except Exception:
        return [len(signal)]


def movement_stats(
    signal_slice: np.ndarray,
    timestamps: np.ndarray,
    scene_id: int,
    subsegment_id: int,
) -> CameraMovement:
    """
    Compute CameraMovement statistics for a single movement segment.

    Entry/exit velocity = mean derivative over the first/last 5% of frames
    (minimum 1 frame). Monotonicity via Spearman correlation.

    Parameters
    ----------
    signal_slice : preprocessed signal for this movement, shape (T, 3+)
                   columns 0=pan, 1=tilt, 2=zoom
    timestamps   : shape (T,) timestamps in seconds
    """
    n = len(signal_slice)
    dt = float(np.median(np.diff(timestamps))) if n > 1 else 1.0
    win = max(1, int(np.ceil(n * 0.05)))

    channels = ("pan", "tilt", "zoom")
    stats: dict[str, float] = {}

    for i, ch in enumerate(channels):
        sig = signal_slice[:, i]
        d1 = np.gradient(sig, dt)

        mono = float(spearmanr(np.arange(n), sig).statistic) if n > 2 else float("nan")

        stats[f"{ch}_entry_vel"] = float(np.mean(d1[:win]))
        stats[f"{ch}_exit_vel"] = float(np.mean(d1[-win:]))
        stats[f"{ch}_monotonicity"] = mono
        stats[f"{ch}_mean_abs_deriv"] = float(np.mean(np.abs(d1)))
        stats[f"{ch}_std_deriv"] = float(np.std(d1))

    return CameraMovement(
        scene_id=scene_id,
        subsegment_id=subsegment_id,
        start_time=float(timestamps[0]),
        end_time=float(timestamps[-1]),
        **stats,
    )
