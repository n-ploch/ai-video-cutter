"""Video pipeline Celery tasks (queue: video).

Dependency chain per video:
    task_downsample → task_flow_and_segment → (task_vlm_describe in vlm_tasks)

Each task reads its inputs from storage and writes outputs back to storage
before returning a plain JSON-serialisable dict.  PipelineContext is NEVER
passed between tasks — it holds numpy arrays that cannot cross task boundaries.
"""
from __future__ import annotations

import logging
from pathlib import Path

from worker.celery_app import app

log = logging.getLogger(__name__)


def _get_storage_and_settings(project_name: str):
    """Load AppSettings from env and create storage + workflow Settings."""
    from core.config import AppSettings
    from core.storage_factory import make_storage

    app_settings = AppSettings.from_env()
    storage = make_storage(
        storage_backend=app_settings.storage_backend,
        storage_root=app_settings.storage_root,
        default_config=app_settings.default_config_path,
    )
    settings = app_settings.load_settings(project_name)
    return storage, settings, app_settings


@app.task(
    bind=True,
    name="video.downsample",
    queue="video",
    acks_late=True,
    max_retries=2,
)
def task_downsample(self, project_name: str, video_storage_key: str) -> dict:
    """Downsample the source video and register it in the manifest.

    Args:
        project_name:      Project identifier.
        video_storage_key: Backend-relative key for the uploaded source file,
                           e.g. ``"my-project/videos/abc123/original.mp4"``.

    Returns a dict passed as the first argument to ``task_flow_and_segment``.
    """
    from core.storage import hash_video_file
    from core.schemas.video import ProcessingConfig
    from video.pipeline import DownsampleStep, PipelineContext

    self.update_state(state="STARTED", meta={"current_step": "downsample", "project": project_name})

    storage, settings, _ = _get_storage_and_settings(project_name)
    proc_config = ProcessingConfig(
        target_fps=settings.video.downsample.target_fps,
        target_width=settings.video.downsample.target_width,
        output_format=settings.video.downsample.output_format,
        hwaccel=settings.video.hwaccel,
    )

    with storage.backend.local_path(video_storage_key) as video_path:
        video_hash = hash_video_file(video_path)

        ctx = PipelineContext(
            video_path=video_path,
            project_name=project_name,
            project_id=project_name,
            video_hash=video_hash,
        )

        step = DownsampleStep(proc_config, storage=storage, config=settings)
        step.check_inputs(ctx)
        step.run(ctx)

        downsampled_key = str(ctx.downsampled_path.relative_to(storage.root))

    log.info("task_downsample: project=%s hash=%s → %s", project_name, video_hash, downsampled_key)
    return {
        "project_name": project_name,
        "video_storage_key": video_storage_key,
        "video_hash": video_hash,
        "downsampled_key": downsampled_key,
    }


@app.task(
    bind=True,
    name="video.flow_and_segment",
    queue="video",
    acks_late=True,
    max_retries=1,
    time_limit=3600,
    soft_time_limit=3540,
)
def task_flow_and_segment(self, prev: dict) -> dict:
    """Optical flow, signal preprocessing, scene segmentation, and persist.

    Receives the return dict from ``task_downsample``.  Runs three pipeline
    steps in a single process so that numpy arrays (raw_signal, timestamps,
    preprocessed_signal) are never serialised between tasks.
    """
    from core.schemas.video import ProcessingConfig, SegmentationConfig
    from video.pipeline import (
        OpticalFlowStep,
        PersistStep,
        PipelineContext,
        PreprocessSignalStep,
        SegmentScenesStep,
    )

    project_name = prev["project_name"]
    video_hash = prev["video_hash"]
    video_storage_key = prev["video_storage_key"]
    downsampled_key = prev["downsampled_key"]

    self.update_state(
        state="STARTED",
        meta={"current_step": "optical_flow", "project": project_name, "video_hash": video_hash},
    )

    storage, settings, _ = _get_storage_and_settings(project_name)
    proc_config = ProcessingConfig(
        target_fps=settings.video.downsample.target_fps,
        target_width=settings.video.downsample.target_width,
        output_format=settings.video.downsample.output_format,
        hwaccel=settings.video.hwaccel,
    )
    seg_config = SegmentationConfig(
        fd_penalty=settings.video.segmentation.fd_penalty,
        subseg_penalty=settings.video.segmentation.subseg_penalty,
        savgol_window=settings.video.segmentation.savgol_window,
        savgol_poly=settings.video.segmentation.savgol_poly,
    )
    flow_fps = settings.video.optical_flow.target_fps

    with (
        storage.backend.local_path(video_storage_key) as video_path,
        storage.backend.local_path(downsampled_key) as ds_path,
    ):
        ctx = PipelineContext(
            video_path=video_path,
            project_name=project_name,
            project_id=project_name,
            video_hash=video_hash,
            downsampled_path=ds_path,
        )

        # ── Optical flow ───────────────────────────────────────────────────────
        flow_step = OpticalFlowStep(proc_config, flow_fps=flow_fps)
        flow_step.check_inputs(ctx)
        flow_step.run(ctx)

        self.update_state(
            state="STARTED",
            meta={"current_step": "segmentation", "project": project_name, "video_hash": video_hash},
        )

        # ── Preprocess + segment ───────────────────────────────────────────────
        PreprocessSignalStep(seg_config).run(ctx)
        SegmentScenesStep(seg_config).run(ctx)

        # ── Persist ────────────────────────────────────────────────────────────
        PersistStep(storage, project_name=project_name, config=settings).run(ctx)

        segment_count = len(ctx.segments)

    log.info(
        "task_flow_and_segment: project=%s hash=%s → %d segments",
        project_name, video_hash, segment_count,
    )
    return {
        "project_name": project_name,
        "video_storage_key": video_storage_key,
        "video_hash": video_hash,
        "downsampled_key": downsampled_key,
        "segment_count": segment_count,
    }


def build_video_pipeline_chain(
    project_name: str,
    video_storage_key: str,
    include_vlm: bool = True,
):
    """Build the Celery chain for a single video.

    Dispatched by the API when a video is uploaded::

        chain = build_video_pipeline_chain("my-project", "my-project/videos/abc123/original.mp4")
        result = chain.apply_async()
    """
    from celery import chain as celery_chain
    from worker.vlm_tasks import task_vlm_global

    c = celery_chain(
        task_downsample.s(project_name, video_storage_key),
        task_flow_and_segment.s(),
    )
    if include_vlm:
        c = c | task_vlm_global.s()
    return c
