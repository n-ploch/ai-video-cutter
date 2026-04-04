from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator

import numpy as np

from core.schemas.video import ProcessingConfig
from video.ingest import probe_video


def stream_frames(
    video_path: Path | str,
    config: ProcessingConfig,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """
    Stream frames from *video_path* as BGR numpy arrays via ffmpeg stdout pipe.

    Yields (frame_index, timestamp_seconds, frame_bgr) one frame at a time.
    Only one frame is held in memory at any point.

    Frame dimensions: (height, target_width, 3), dtype uint8, BGR channel order.
    """
    video_path = Path(video_path)
    info = probe_video(video_path)

    # Compute scaled height (ffmpeg -2 rounds to nearest even number)
    scale_factor = config.target_width / info.width
    raw_h = int(info.height * scale_factor)
    target_height = raw_h if raw_h % 2 == 0 else raw_h + 1

    frame_bytes = config.target_width * target_height * 3

    hwaccel_args = ["-hwaccel", config.hwaccel] if config.hwaccel else []
    cmd = [
        "ffmpeg",
        *hwaccel_args,
        "-i", str(video_path),
        "-vf", f"fps={config.target_fps},scale={config.target_width}:{target_height}",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-an",
        "pipe:1",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_index = 0
    try:
        while True:
            raw = proc.stdout.read(frame_bytes)
            if len(raw) != frame_bytes:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                (target_height, config.target_width, 3)
            ).copy()
            timestamp = (frame_index + 1) / config.target_fps
            yield frame_index, timestamp, frame
            frame_index += 1
    finally:
        proc.stdout.close()
        proc.wait()


def extract_frame(
    video_path: Path | str,
    timestamp: float,
    width: int = 640,
    hwaccel: str | None = None,
) -> np.ndarray:
    """
    Decode a single BGR frame at *timestamp* seconds from *video_path*.

    Returns array of shape (H, W, 3), dtype uint8, BGR.
    Raises RuntimeError if ffmpeg cannot decode the frame.
    """
    video_path = Path(video_path)
    info = probe_video(video_path)
    scale_factor = width / info.width
    raw_h = int(info.height * scale_factor)
    target_height = raw_h if raw_h % 2 == 0 else raw_h + 1
    frame_bytes = width * target_height * 3

    hwaccel_args = ["-hwaccel", hwaccel] if hwaccel else []
    cmd = [
        "ffmpeg",
        *hwaccel_args,
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", f"scale={width}:{target_height}",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "pipe:1",
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or len(result.stdout) != frame_bytes:
        raise RuntimeError(
            f"Failed to extract frame at {timestamp}s from {video_path}: "
            f"{result.stderr[-500:].decode(errors='replace')}"
        )

    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(
        (target_height, width, 3)
    ).copy()
