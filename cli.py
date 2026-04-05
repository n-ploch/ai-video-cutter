from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.config import Settings
from core.schemas.segment import SegmentBase
from core.schemas.video import ProcessingConfig, SegmentationConfig
from core.storage import ProjectStorage, hash_video_file
from video.pipeline import PipelineContext, default_pipeline

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = typer.Typer(add_completion=False)

_REPO_ROOT = Path(__file__).parent
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "default.yaml"

load_dotenv(_REPO_ROOT / ".env", override=False)


@app.command()
def process(
    video: Annotated[Path, typer.Argument(help="Path to video file")],
    config_path: Path = typer.Option(
        _DEFAULT_CONFIG,
        "--config",
        help="Path to YAML config file",
    ),
    # Per-run overrides — defaults shown come from config file at runtime.
    downsample_fps: Optional[float] = typer.Option(None, help="Frames per second for the downsampled file (null = native)"),
    flow_fps: Optional[float] = typer.Option(None, help="Frames per second for optical flow streaming"),
    target_width: Optional[int] = typer.Option(None, help="Resize width for downsampling and optical flow frames"),
    fd_penalty: Optional[float] = typer.Option(None, help="Pelt l2 penalty for scene boundaries"),
    subseg_penalty: Optional[float] = typer.Option(None, help="Pelt l1 penalty for movement boundaries"),
    savgol_window: Optional[int] = typer.Option(None, help="Savitzky-Golay smoothing window"),
    savgol_poly: Optional[int] = typer.Option(None, help="Savitzky-Golay polynomial order"),
    hwaccel: Optional[str] = typer.Option(None, help="ffmpeg hwaccel backend (e.g. videotoolbox, cuda)"),
    storage_root: Path = typer.Option(Path("local/data/projects"), help="Project storage root"),
    project_name: Optional[str] = typer.Option(None, help="Project name (defaults to video stem)"),
    force: bool = typer.Option(False, "--force", help="Reprocess even if already up to date"),
    describe: bool = typer.Option(False, "--describe", help="Run VLM scene description after segmentation"),
):
    """Run a video through the optical-flow segmentation pipeline."""
    if not video.exists():
        typer.echo(f"Error: {video} does not exist", err=True)
        raise typer.Exit(1)

    settings = Settings.load(config_path)
    storage = ProjectStorage(root=storage_root, default_config=config_path)
    name = project_name or video.stem
    video_hash = hash_video_file(video)

    segmented_current = not force and storage.is_step_current(name, video_hash, "segmented", settings)

    if segmented_current:
        if not describe or storage.is_step_current(name, video_hash, "described", settings):
            out_dir = storage.get_project_path(name) / "analysis"
            typer.echo(
                f"Already processed. Project: {name}  Output: {out_dir}/  "
                f"(use --force to reprocess)"
            )
            raise typer.Exit(0)

        # Segmentation is current but VLM description is missing/stale.
        # Skip optical flow + segmentation entirely; run only VLMStep.
        if describe:
            from video.vlm import VLMStep

            segments = storage.load_json(
                name,
                f"videos/{video_hash}/segments/segments.json",
                schema=SegmentBase,
            )
            fmt = settings.video.downsample.output_format
            downsampled = (
                storage.get_project_path(name)
                / "videos" / video_hash
                / f"{video.stem}_downsampled.{fmt}"
            )
            ctx = PipelineContext(
                video_path=video,
                project_name=name,
                project_id=name,
                video_hash=video_hash,
                segments=segments,
                downsampled_path=downsampled if downsampled.exists() else None,
            )
            VLMStep(storage, settings).run(ctx)
            typer.echo(
                f"Done. Project: {name}  "
                f"Segments described: {len(segments)}  "
                f"Output: {storage.get_project_path(name) / 'videos' / video_hash}/"
            )
            raise typer.Exit(0)

    proc_config = ProcessingConfig(
        target_fps=downsample_fps if downsample_fps is not None else settings.video.downsample.target_fps,
        target_width=target_width if target_width is not None else settings.video.downsample.target_width,
        hwaccel=hwaccel if hwaccel is not None else settings.video.hwaccel,
    )
    seg_config = SegmentationConfig(
        fd_penalty=fd_penalty if fd_penalty is not None else settings.video.segmentation.fd_penalty,
        subseg_penalty=subseg_penalty if subseg_penalty is not None else settings.video.segmentation.subseg_penalty,
        savgol_window=savgol_window if savgol_window is not None else settings.video.segmentation.savgol_window,
        savgol_poly=savgol_poly if savgol_poly is not None else settings.video.segmentation.savgol_poly,
    )

    ctx = default_pipeline(
        proc_config, seg_config, storage, config=settings, include_vlm=describe,
        flow_fps=flow_fps,
    ).run(video, project_name=name)

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


@app.command()
def storyboard(
    project_name: Annotated[str, typer.Argument(help="Name of an already-processed project")],
    brief: Annotated[str, typer.Option("--brief", "-b", help="Creative brief for the story")],
    config_path: Path = typer.Option(
        _DEFAULT_CONFIG,
        "--config",
        help="Path to YAML config file",
    ),
    storage_root: Path = typer.Option(Path("local/data/projects"), help="Project storage root"),
):
    """Run the storyboard agent on a processed project.

    Reads segment descriptions from storage, then runs the LangGraph pipeline
    (story writer → narrator → director → judge) to produce a versioned storyboard.
    """
    from storyboard.graph import run as run_storyboard

    settings = Settings.load(config_path)
    storage = ProjectStorage(root=storage_root, default_config=config_path)

    typer.echo(f"Running storyboard agent for project '{project_name}' …")
    output = run_storyboard(
        project_name=project_name,
        user_brief=brief,
        cfg=settings.storyboard,
        storage=storage,
    )

    out_dir = storage.get_project_path(project_name) / "storyboard"
    typer.echo(
        f"Done.  Scenes: {len(output.scenes)}  "
        f"Revisions: {output.revision_count}  "
        f"Score: {output.judge_result.score:.2f}  "
        f"Output: {out_dir}/latest.json"
    )


@app.command()
def edit(
    project_name: Annotated[str, typer.Argument(help="Name of a project that has a storyboard")],
    config_path: Path = typer.Option(
        _DEFAULT_CONFIG,
        "--config",
        help="Path to YAML config file",
    ),
    storage_root: Path = typer.Option(Path("local/data/projects"), help="Project storage root"),
):
    """Run the timeline assembly agent on a project that has a storyboard.

    Reads segment data + storyboard/latest.json, then runs the LangGraph
    pipeline (embedding index → candidates → assembly → stitching → review)
    to produce a versioned timeline saved under timeline/latest.json.
    """
    from editor.graph import run as run_editor

    settings = Settings.load(config_path)
    storage = ProjectStorage(root=storage_root, default_config=config_path)

    typer.echo(f"Running timeline assembly agent for project '{project_name}' …")
    output = run_editor(
        project_name=project_name,
        cfg=settings.editor,
        storage=storage,
    )

    out_dir = storage.get_project_path(project_name) / "timeline"
    typer.echo(
        f"Done.  Scenes: {len(output.scenes)}  "
        f"Duration: {output.total_duration:.1f}s  "
        f"Segments: {output.total_segments}  "
        f"Output: {out_dir}/latest.json"
    )


if __name__ == "__main__":
    app()
