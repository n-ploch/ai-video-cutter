"""
Camera Trajectory Estimation Pipeline
======================================
Estimates per-frame camera pose from drone footage using SuperPoint + LightGlue
feature matching and Essential Matrix decomposition.

Output per frame: pan_deg, tilt_deg, roll_deg, translation_dir (unit vec), inlier_ratio
Segmentation: ruptures Pelt on the 6-DOF signal [pan, tilt, roll, tx, ty, tz]

Dependencies:
    pip install lightglue opencv-contrib-python ruptures tqdm ffmpeg-python

Usage:
    python scripts/camera_trajectory.py local/videos/DJI_xxx.MP4
    python scripts/camera_trajectory.py local/videos/DJI_xxx.MP4 --fps 5 --penalty 3.0
"""

import cv2
import numpy as np
import json
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Generator
import argparse

import ffmpeg
import pandas as pd
import torch
import ruptures as rpt
from scipy.signal import medfilt
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class PoseFrame:
    frame_idx: int
    timestamp: float
    pan_deg: float
    tilt_deg: float
    roll_deg: float
    translation_dir: list   # unit vector [tx, ty, tz]
    inlier_ratio: float
    n_matches: int

@dataclass
class TrajectorySegment:
    segment_id: int
    start_time: float
    end_time: float
    n_frames: int
    mean_pan_deg: float
    mean_tilt_deg: float
    mean_roll_deg: float

@dataclass
class TrajectoryConfig:
    fps: float = 3.0
    width: int = 640
    # Physical camera parameters — DJI Mini 4 Pro defaults
    focal_length_mm: float = 6.72    # actual focal length (not 35mm equiv)
    sensor_width_mm: float = 9.7     # sensor width used for 4K video (full width, 16:9 crop)
    # Distortion coefficients [k1, k2, p1, p2] — set to None to skip correction.
    # DJI Mini 4 Pro does not publish calibration data; run cv2.calibrateCamera on a
    # checkerboard to get your unit's exact values. Approximate values for similar
    # DJI wide cameras: k1≈-0.03, k2≈0.01, p1≈0, p2≈0.
    dist_coeffs: Optional[list] = None
    min_matches: int = 30
    ruptures_penalty: float = 3.0
    device: str = "auto"


# ---------------------------------------------------------------------------
# Frame extraction (same pattern as scene_selection.py)
# ---------------------------------------------------------------------------
def stream_frames(
    video_path: str, fps: float = 5.0, width: int = 640
) -> Generator[tuple[np.ndarray, float, float], None, None]:
    """
    Stream frames from a video using FFmpeg with hardware acceleration (VideoToolbox on Mac).
    Yields (frame_rgb, timestamp_seconds, read_time_seconds) one frame at a time.
    """
    try:
        probe = ffmpeg.probe(video_path)
    except ffmpeg.Error as e:
        raise RuntimeError(
            f"ffprobe failed on {video_path!r}:\n{e.stderr.decode(errors='replace')}"
        ) from e

    video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    if video_stream is None:
        raise ValueError(f"No video stream found in {video_path}")

    orig_w = int(video_stream["width"])
    orig_h = int(video_stream["height"])

    aspect_ratio = orig_h / orig_w
    target_height = int(width * aspect_ratio)
    if target_height % 2 != 0:
        target_height += 1

    frame_bytes = width * target_height * 3

    log.info(
        f"Streaming {video_path}: {orig_w}x{orig_h} → {width}x{target_height} "
        f"@ {fps}fps"
    )

    process = (
        ffmpeg
        .input(video_path, hwaccel="videotoolbox")
        .filter("fps", fps=fps)
        .filter("scale", width, target_height)
        .output("pipe:", format="rawvideo", pix_fmt="rgb24")
        .run_async(pipe_stdout=True, quiet=True)
    )

    frame_idx = 1
    try:
        while True:
            start_read = time.time()
            raw_data = process.stdout.read(frame_bytes)
            read_time = time.time() - start_read

            if len(raw_data) != frame_bytes:
                break

            timestamp = frame_idx / fps
            yield (
                np.frombuffer(raw_data, dtype="uint8").reshape((target_height, width, 3)).copy(),
                timestamp,
                read_time,
            )
            frame_idx += 1
    finally:
        process.stdout.close()
        process.wait()


def get_duration(video_path: str) -> float:
    probe = ffmpeg.probe(video_path)
    return float(probe["format"]["duration"])


# ---------------------------------------------------------------------------
# Camera intrinsics
# ---------------------------------------------------------------------------
def build_intrinsics(
    frame_shape: tuple,
    focal_length_mm: float = 6.72,
    sensor_width_mm: float = 9.7,
) -> np.ndarray:
    """
    Build camera matrix K from physical lens/sensor specs.

    DJI Mini 4 Pro defaults:
      focal_length_mm = 6.72  (actual focal length, not 35mm equiv)
      sensor_width_mm = 9.7   (full sensor width; 4K video uses full width, crops height)

    f_px = focal_length_mm / (sensor_width_mm / image_width_px)
         = focal_length_mm * image_width_px / sensor_width_mm
    """
    H, W = frame_shape[:2]
    f = focal_length_mm * W / sensor_width_mm
    return np.array([
        [f,  0,  W / 2],
        [0,  f,  H / 2],
        [0,  0,      1],
    ], dtype=np.float64)


# ---------------------------------------------------------------------------
# Feature matching via HuggingFace SuperPoint + LightGlue
# ---------------------------------------------------------------------------
class SuperPointLightGlue:
    """
    SuperPoint + LightGlue keypoint matching via HuggingFace transformers.
    Takes two RGB frames and returns matched pixel coordinates.
    """

    HF_MODEL = "ETH-CVG/lightglue_superpoint"

    def __init__(self, device: str):
        from transformers import AutoImageProcessor, LightGlueForKeypointMatching
        from PIL import Image as PILImage
        self._PILImage = PILImage

        self.device = device
        log.info(f"Loading SuperPoint+LightGlue from HuggingFace on {device}")
        self.processor = AutoImageProcessor.from_pretrained(self.HF_MODEL)
        self.model = (
            LightGlueForKeypointMatching.from_pretrained(self.HF_MODEL)
            .eval()
            .to(device)
        )
        log.info("SuperPoint+LightGlue ready")

    def match(
        self, frame0_rgb: np.ndarray, frame1_rgb: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Match keypoints between two RGB frames.
        Returns (pts0, pts1) as (N, 2) float32 arrays in pixel coordinates.
        """
        img0 = self._PILImage.fromarray(frame0_rgb)
        img1 = self._PILImage.fromarray(frame1_rgb)

        inputs = self.processor(images=[img0, img1], return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)

        # list[tuple[tuple[int,int]]] — one entry per batch item, each a pair of (H,W)
        image_sizes = [
            ((frame0_rgb.shape[0], frame0_rgb.shape[1]),
             (frame1_rgb.shape[0], frame1_rgb.shape[1]))
        ]
        results = self.processor.post_process_keypoint_matching(
            outputs, image_sizes, threshold=0.0
        )
        result = results[0]
        pts0 = result["keypoints0"].cpu().numpy().astype(np.float32)
        pts1 = result["keypoints1"].cpu().numpy().astype(np.float32)
        return pts0, pts1


# ---------------------------------------------------------------------------
# Pose estimation via Essential Matrix
# ---------------------------------------------------------------------------
def estimate_pose(
    pts0: np.ndarray,
    pts1: np.ndarray,
    K: np.ndarray,
    min_matches: int = 30,
    dist_coeffs: Optional[np.ndarray] = None,
) -> Optional[dict]:
    """
    Estimate relative camera pose from 2D-2D correspondences.
    Uses Essential Matrix decomposition — no PnP, no depth required.

    If dist_coeffs is provided, keypoints are undistorted before the Essential
    Matrix is computed, improving inlier ratio on cameras with barrel distortion.

    Returns dict with pan_deg, tilt_deg, roll_deg, translation_dir, inlier_ratio
    or None if not enough matches.
    """
    if len(pts0) < min_matches:
        return None

    if dist_coeffs is not None:
        pts0 = cv2.undistortPoints(
            pts0.reshape(-1, 1, 2), K, dist_coeffs, P=K
        ).reshape(-1, 2)
        pts1 = cv2.undistortPoints(
            pts1.reshape(-1, 1, 2), K, dist_coeffs, P=K
        ).reshape(-1, 2)

    E, mask = cv2.findEssentialMat(
        pts0, pts1, K,
        method=cv2.USAC_MAGSAC,
        prob=0.999,
        threshold=1.0,
    )

    if E is None or mask is None:
        return None

    _, R, t, mask = cv2.recoverPose(E, pts0, pts1, K, mask=mask)

    n_inliers = int(mask.sum())
    inlier_ratio = n_inliers / len(mask)

    # Reject degenerate solutions: require enough inliers and a decent ratio
    if n_inliers < min_matches or inlier_ratio < 0.1:
        return None

    # Decompose R into yaw/pitch/roll via Rodrigues axis-angle
    angles, _ = cv2.Rodrigues(R)

    return {
        "pan_deg":         float(np.degrees(angles[1, 0])),   # yaw
        "tilt_deg":        float(np.degrees(angles[0, 0])),   # pitch
        "roll_deg":        float(np.degrees(angles[2, 0])),   # roll
        "translation_dir": t.flatten().tolist(),               # unit vector
        "inlier_ratio":    inlier_ratio,
    }


# ---------------------------------------------------------------------------
# Trajectory segmentation
# ---------------------------------------------------------------------------
class TrajectorySegmenter:
    """Ruptures Pelt change point detection on 6-DOF pose signal."""

    def __init__(self, penalty: float = 3.0):
        self.penalty = penalty

    def detect_boundaries(
        self, poses_6dof: np.ndarray, timestamps: np.ndarray
    ) -> list[float]:
        """
        Detect trajectory segment boundaries.

        Args:
            poses_6dof: (N, 6) array [pan, tilt, roll, tx, ty, tz]
            timestamps:  (N,) array of frame timestamps

        Returns:
            List of boundary timestamps (not including start/end).
        """
        if len(poses_6dof) < 4:
            return []

        # Median filter to suppress isolated spikes before segmentation
        X = poses_6dof.copy().astype(np.float64)
        for i in range(X.shape[1]):
            X[:, i] = medfilt(X[:, i], kernel_size=5)

        # Min-max normalize each dimension independently
        for i in range(X.shape[1]):
            col_min, col_max = X[:, i].min(), X[:, i].max()
            if col_max - col_min > 1e-8:
                X[:, i] = (X[:, i] - col_min) / (col_max - col_min)

        try:
            model = rpt.Pelt(model="l1").fit(X)
            breakpoints = model.predict(pen=self.penalty)
        except Exception as e:
            log.warning(f"Ruptures segmentation failed: {e}")
            return []

        # breakpoints includes the last index (len), exclude it
        bp_indices = [b - 1 for b in breakpoints if b < len(timestamps)]
        return [float(timestamps[i]) for i in bp_indices]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
class CameraTrajectoryPipeline:
    """
    Streams drone video, estimates per-frame camera pose via SuperPoint + LightGlue
    + Essential Matrix decomposition, then segments based on 6-DOF trajectory.
    """

    def __init__(self, config: TrajectoryConfig):
        self.config = config

        device = config.device
        if device == "auto":
            device = (
                "cuda" if torch.cuda.is_available()
                else "mps" if torch.backends.mps.is_available()
                else "cpu"
            )
        self.device = device
        log.info(f"Using device: {device}")

        self.matcher = SuperPointLightGlue(device)
        self.segmenter = TrajectorySegmenter(config.ruptures_penalty)

    def analyze(self, video_path: str, output_path: str) -> dict:
        cfg = self.config
        duration = get_duration(video_path)
        total_frames = int(duration * cfg.fps)

        log.info(f"Analyzing {video_path}: ~{total_frames} frames @ {cfg.fps}fps")

        pose_frames: list[PoseFrame] = []
        prev_frame = None
        K = None  # initialized from first frame

        for frame_rgb, timestamp, _ in tqdm(
            stream_frames(video_path, fps=cfg.fps, width=cfg.width),
            total=total_frames,
            desc="Estimating trajectory",
        ):
            frame_idx = len(pose_frames)

            if K is None:
                K = build_intrinsics(
                    frame_rgb.shape, cfg.focal_length_mm, cfg.sensor_width_mm
                )
                log.info(
                    f"Intrinsics K (f={cfg.focal_length_mm}mm, "
                    f"sensor={cfg.sensor_width_mm}mm):\n{K}"
                )

            dist = (
                np.array(cfg.dist_coeffs, dtype=np.float64)
                if cfg.dist_coeffs is not None else None
            )

            if prev_frame is not None:
                pts0, pts1 = self.matcher.match(prev_frame, frame_rgb)
                n_matches = len(pts0)
                pose = estimate_pose(pts0, pts1, K, cfg.min_matches, dist)
            else:
                n_matches = 0
                pose = None

            if pose is not None:
                pf = PoseFrame(
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                    pan_deg=pose["pan_deg"],
                    tilt_deg=pose["tilt_deg"],
                    roll_deg=pose["roll_deg"],
                    translation_dir=pose["translation_dir"],
                    inlier_ratio=pose["inlier_ratio"],
                    n_matches=n_matches,
                )
            else:
                # No valid pose: fill with zeros (tracking lost)
                pf = PoseFrame(
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                    pan_deg=0.0,
                    tilt_deg=0.0,
                    roll_deg=0.0,
                    translation_dir=[0.0, 0.0, 0.0],
                    inlier_ratio=0.0,
                    n_matches=n_matches,
                )

            pose_frames.append(pf)
            prev_frame = frame_rgb

        # Build 6-DOF array for segmentation
        poses_6dof = np.array([
            [f.pan_deg, f.tilt_deg, f.roll_deg,
             f.translation_dir[0], f.translation_dir[1], f.translation_dir[2]]
            for f in pose_frames
        ], dtype=np.float32)

        timestamps = np.array([f.timestamp for f in pose_frames])
        inlier_ratios_arr = np.array([f.inlier_ratio for f in pose_frames])

        # Interpolate frames where pose estimation failed (inlier_ratio == 0)
        # so ruptures sees a continuous signal rather than artificial zero plateaus
        bad = inlier_ratios_arr < 0.1
        if bad.any() and (~bad).sum() >= 2:
            for col in range(poses_6dof.shape[1]):
                s = pd.Series(poses_6dof[:, col].astype(np.float64))
                s[bad] = np.nan
                poses_6dof[:, col] = s.interpolate(
                    method="linear", limit_direction="both"
                ).values.astype(np.float32)
            log.info(f"Interpolated {bad.sum()} frames with no valid pose")

        boundaries = self.segmenter.detect_boundaries(poses_6dof, timestamps)

        # Build segments
        boundary_times = [0.0] + boundaries + [duration]
        segments = []
        for i in range(len(boundary_times) - 1):
            t_start, t_end = boundary_times[i], boundary_times[i + 1]
            seg_frames = [
                f for f in pose_frames if t_start <= f.timestamp < t_end
            ]
            if not seg_frames:
                continue
            seg = TrajectorySegment(
                segment_id=len(segments),
                start_time=t_start,
                end_time=t_end,
                n_frames=len(seg_frames),
                mean_pan_deg=float(np.mean([f.pan_deg for f in seg_frames])),
                mean_tilt_deg=float(np.mean([f.tilt_deg for f in seg_frames])),
                mean_roll_deg=float(np.mean([f.roll_deg for f in seg_frames])),
            )
            segments.append(seg)

        result = {
            "video_path": video_path,
            "backend": "superpoint_lightglue",
            "fps": cfg.fps,
            "duration": duration,
            "n_frames": len(pose_frames),
            "device": self.device,
            "focal_length_mm": cfg.focal_length_mm,
            "sensor_width_mm": cfg.sensor_width_mm,
            "dist_coeffs": cfg.dist_coeffs,
            "ruptures_penalty": cfg.ruptures_penalty,
            "frames": [asdict(f) for f in pose_frames],
            "segments": [asdict(s) for s in segments],
            "boundaries": boundaries,
        }

        # Save JSON
        json_path = output_path + ".trajectory.json"
        with open(json_path, "w") as fh:
            json.dump(result, fh, indent=2)
        log.info(f"Saved trajectory JSON → {json_path}")

        # Save NPZ
        npz_path = output_path + ".trajectory.npz"
        np.savez_compressed(
            npz_path,
            poses_6dof=poses_6dof,
            timestamps=timestamps,
            inlier_ratios=np.array([f.inlier_ratio for f in pose_frames]),
            n_matches=np.array([f.n_matches for f in pose_frames]),
        )
        log.info(f"Saved trajectory NPZ  → {npz_path}")

        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Camera trajectory estimation from drone footage."
    )
    parser.add_argument("video", help="Path to input .MP4 file")
    parser.add_argument("--fps",         type=float, default=3.0,
                        help="Frames per second to sample (default: 3)")
    parser.add_argument("--width",       type=int,   default=640,
                        help="Frame width for processing (default: 640)")
    parser.add_argument("--focal-length", type=float, default=6.72,
                        help="Actual focal length in mm (default: 6.72, DJI Mini 4 Pro)")
    parser.add_argument("--sensor-width", type=float, default=9.7,
                        help="Sensor width in mm used for video (default: 9.7, DJI Mini 4 Pro)")
    parser.add_argument("--dist-coeffs",  type=float, nargs=4,
                        metavar=("K1", "K2", "P1", "P2"), default=None,
                        help="Lens distortion coefficients k1 k2 p1 p2. "
                             "Omit to skip correction (requires checkerboard calibration). "
                             "Example: --dist-coeffs -0.03 0.01 0 0")
    parser.add_argument("--penalty",      type=float, default=3.0,
                        help="Ruptures Pelt penalty — higher = fewer segments (default: 3.0)")
    parser.add_argument("--min-matches",  type=int,   default=30,
                        help="Minimum inlier matches to accept a pose estimate (default: 30)")
    parser.add_argument("--device",       default="auto",
                        choices=["auto", "mps", "cpu", "cuda"],
                        help="Compute device (default: auto)")
    parser.add_argument("--reanalyze",    action="store_true",
                        help="Recompute even if output already exists")
    args = parser.parse_args()

    video_path = args.video
    output_path = str(Path(video_path).with_suffix(""))

    json_path = output_path + ".trajectory.json"
    if Path(json_path).exists() and not args.reanalyze:
        log.info(f"Output already exists: {json_path}. Use --reanalyze to recompute.")
        return

    config = TrajectoryConfig(
        fps=args.fps,
        width=args.width,
        focal_length_mm=args.focal_length,
        sensor_width_mm=args.sensor_width,
        dist_coeffs=args.dist_coeffs,
        min_matches=args.min_matches,
        ruptures_penalty=args.penalty,
        device=args.device,
    )

    pipeline = CameraTrajectoryPipeline(config)
    result = pipeline.analyze(video_path, output_path)

    log.info(
        f"Done. {result['n_frames']} frames, "
        f"{len(result['segments'])} segments, "
        f"{len(result['boundaries'])} boundaries."
    )


if __name__ == "__main__":
    main()
