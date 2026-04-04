from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.schemas.video import ProcessingConfig, SegmentationConfig
from core.storage import ProjectStorage
from video.pipeline import default_pipeline

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = typer.Typer(add_completion=False)


@app.command()
def process(
    video: Annotated[Path, typer.Argument(help="Path to video file")],
    flow_fps: float = typer.Option(4.0, help="Frames per second for optical flow pass"),
    target_width: int = typer.Option(640, help="Resize width for optical flow frames"),
    fd_penalty: float = typer.Option(3.0, help="Pelt l2 penalty for scene boundaries"),
    subseg_penalty: float = typer.Option(2.0, help="Pelt l1 penalty for movement boundaries"),
    savgol_window: int = typer.Option(11, help="Savitzky-Golay smoothing window"),
    savgol_poly: int = typer.Option(2, help="Savitzky-Golay polynomial order"),
    hwaccel: Optional[str] = typer.Option(None, help="ffmpeg hwaccel backend (e.g. videotoolbox, cuda)"),
    storage_root: Path = typer.Option(Path("local/data/projects"), help="Project storage root"),
):
    """Run a video through the optical-flow segmentation pipeline."""
    if not video.exists():
        typer.echo(f"Error: {video} does not exist", err=True)
        raise typer.Exit(1)

    proc_config = ProcessingConfig(
        target_fps=flow_fps,
        target_width=target_width,
        hwaccel=hwaccel,
    )
    seg_config = SegmentationConfig(
        fd_penalty=fd_penalty,
        subseg_penalty=subseg_penalty,
        savgol_window=savgol_window,
        savgol_poly=savgol_poly,
    )
    storage = ProjectStorage(root=storage_root)

    ctx = default_pipeline(proc_config, seg_config, storage).run(video)

    out_dir = storage.get_project_path(ctx.project_id) / "analysis"
    typer.echo(
        f"Done. Project: {ctx.project_id}  "
        f"Segments: {len(ctx.segments)}  "
        f"Output: {out_dir}/"
    )


if __name__ == "__main__":
    app()
