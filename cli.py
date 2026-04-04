from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.config import Settings
from core.schemas.video import ProcessingConfig, SegmentationConfig
from core.storage import ProjectStorage, hash_video_file
from video.pipeline import default_pipeline

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = typer.Typer(add_completion=False)

_REPO_ROOT = Path(__file__).parent
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "default.yaml"


@app.command()
def process(
    video: Annotated[Path, typer.Argument(help="Path to video file")],
    config_path: Path = typer.Option(
        _DEFAULT_CONFIG,
        "--config",
        help="Path to YAML config file",
    ),
    # Per-run overrides — defaults shown come from config file at runtime.
    flow_fps: Optional[float] = typer.Option(None, help="Frames per second for optical flow pass"),
    target_width: Optional[int] = typer.Option(None, help="Resize width for optical flow frames"),
    fd_penalty: Optional[float] = typer.Option(None, help="Pelt l2 penalty for scene boundaries"),
    subseg_penalty: Optional[float] = typer.Option(None, help="Pelt l1 penalty for movement boundaries"),
    savgol_window: Optional[int] = typer.Option(None, help="Savitzky-Golay smoothing window"),
    savgol_poly: Optional[int] = typer.Option(None, help="Savitzky-Golay polynomial order"),
    hwaccel: Optional[str] = typer.Option(None, help="ffmpeg hwaccel backend (e.g. videotoolbox, cuda)"),
    storage_root: Path = typer.Option(Path("local/data/projects"), help="Project storage root"),
    project_name: Optional[str] = typer.Option(None, help="Project name (defaults to video stem)"),
    force: bool = typer.Option(False, "--force", help="Reprocess even if already up to date"),
):
    """Run a video through the optical-flow segmentation pipeline."""
    if not video.exists():
        typer.echo(f"Error: {video} does not exist", err=True)
        raise typer.Exit(1)

    settings = Settings.load(config_path)
    storage = ProjectStorage(root=storage_root, default_config=config_path)
    name = project_name or video.stem
    video_hash = hash_video_file(video)
    if not force and storage.is_step_current(name, video_hash, "segmented", settings):
        out_dir = storage.get_project_path(name) / "analysis"
        typer.echo(
            f"Already processed. Project: {name}  Output: {out_dir}/  "
            f"(use --force to reprocess)"
        )
        raise typer.Exit(0)

    proc_config = ProcessingConfig(
        target_fps=flow_fps if flow_fps is not None else settings.video.target_fps,
        target_width=target_width if target_width is not None else settings.video.target_width,
        hwaccel=hwaccel if hwaccel is not None else settings.video.hwaccel,
    )
    seg_config = SegmentationConfig(
        fd_penalty=fd_penalty if fd_penalty is not None else settings.video.segmentation.fd_penalty,
        subseg_penalty=subseg_penalty if subseg_penalty is not None else settings.video.segmentation.subseg_penalty,
        savgol_window=savgol_window if savgol_window is not None else settings.video.segmentation.savgol_window,
        savgol_poly=savgol_poly if savgol_poly is not None else settings.video.segmentation.savgol_poly,
    )

    ctx = default_pipeline(proc_config, seg_config, storage, config=settings).run(video, project_name=name)

    out_dir = storage.get_project_path(ctx.project_id) / "analysis"
    typer.echo(
        f"Done. Project: {ctx.project_id}  "
        f"Segments: {len(ctx.segments)}  "
        f"Output: {out_dir}/"
    )


@app.command()
def create(
    project_name: Annotated[str, typer.Argument(help="Name for the new project")],
    storage_root: Path = typer.Option(Path("local/data/projects"), help="Project storage root"),
    config_path: Path = typer.Option(
        _DEFAULT_CONFIG,
        "--config",
        help="Path to YAML config file (defaults to config/default.yaml)",
    ),
):
    """Create a new project with base folder structure and config.

    Initialises the project directory, copies the default config (with the
    project name injected), and writes an empty video manifest. No video
    processing is run — use 'vc process' to add and analyse videos.
    """
    storage = ProjectStorage(root=storage_root, default_config=config_path)
    project = storage.create_project(project_name, [])
    project_dir = storage.get_project_path(project_name)

    typer.echo(f"Project : {project_name}")
    typer.echo(f"Location: {project_dir}")
    typer.echo(f"Config  : {project_dir / 'config.yaml'}")
    typer.echo(f"Status  : {project.status.value}")


if __name__ == "__main__":
    app()
