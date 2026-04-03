from __future__ import annotations

import subprocess
from pathlib import Path

from core.schemas.video import ProcessingConfig


class DownsampleError(Exception):
    pass


def downsample_video(
    input_path: Path | str,
    output_path: Path | str,
    config: ProcessingConfig,
) -> Path:
    """
    Downsample *input_path* to the target fps and resolution defined in *config*.

    Uses ffmpeg with:
      -vf scale={target_width}:-2    (height auto-calculated, divisible by 2)
      -r {target_fps}
      -an                            (drop audio)

    Returns the path to the written output file.
    Raises DownsampleError on ffmpeg failure.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise DownsampleError(f"Input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    hwaccel_args = ["-hwaccel", config.hwaccel] if config.hwaccel else []
    cmd = [
        "ffmpeg",
        "-y",                              # overwrite
        *hwaccel_args,
        "-i", str(input_path),
        "-vf", f"scale={config.target_width}:-2",
        "-r", str(config.target_fps),
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise DownsampleError(
            f"ffmpeg failed:\n{result.stderr[-2000:]}"
        )

    return output_path
