"""Clip extraction utilities using ffmpeg-python."""
from __future__ import annotations

from pathlib import Path

import ffmpeg


def extract_clip(
    video_path: Path,
    start: float,
    end: float,
    output_path: Path,
    *,
    fast_seek: bool = True,
) -> Path:
    """Extract a time-bounded clip from *video_path* using stream copy (no re-encode).

    Parameters
    ----------
    video_path:   Source video file.
    start:        Clip start time in seconds.
    end:          Clip end time in seconds.
    output_path:  Destination file path. Parent directory is created if absent.
    fast_seek:    If True, use input-side ``-ss`` (fast but may start on nearest
                  keyframe). If False, seek after decoding (frame-accurate but slower).

    Returns
    -------
    output_path on success. Raises RuntimeError on ffmpeg failure.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = end - start
    if duration <= 0:
        raise ValueError(f"end ({end}) must be greater than start ({start})")

    try:
        if fast_seek:
            # Input-side -ss seeks to the nearest keyframe before `start` (fast).
            # -t must be on the output, not the input: with stream copy, input-side
            # -t is ignored and ffmpeg copies to end-of-file from the keyframe.
            stream = (
                ffmpeg.input(str(video_path), ss=start)
                .output(
                    str(output_path),
                    c="copy",
                    t=duration,
                    avoid_negative_ts="make_zero",
                )
            )
        else:
            stream = (
                ffmpeg.input(str(video_path))
                .filter("trim", start=start, end=end)
                .output(str(output_path), c="copy", avoid_negative_ts="make_zero")
            )

        (
            stream
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise RuntimeError(
            f"ffmpeg failed extracting clip [{start:.3f}s–{end:.3f}s] "
            f"from {video_path}: {stderr}"
        ) from exc

    return output_path
