"""VLM description Celery tasks (queue: vlm).

Pipeline:
    task_flow_and_segment → task_vlm_global → chord(N × task_vlm_segment) → task_vlm_collect

task_vlm_global:
    Runs global video analysis, saves vlm.json, then fans out one task_vlm_segment
    per segment via a Celery chord.  Uses self.replace() so the chord replaces the
    current task in the workflow — nothing follows task_vlm_global in the chain.

task_vlm_segment:
    Extracts a single clip (reuses existing) and runs VLM analysis for that segment.
    One independent, retryable task per segment.

task_vlm_collect:
    Chord callback.  Receives the list of per-segment results, persists
    descriptions.json, marks the "described" manifest step complete, and
    transitions project.status to ready when all project videos are described.
"""
from __future__ import annotations

import logging

from video.vlm import _analyze_global, _analyze_segment
from video.vlm_backend import create_vlm_backend
from worker.celery_app import app

log = logging.getLogger(__name__)


def _get_storage_and_settings(project_name: str):
    from core.config import AppSettings
    from core.storage_factory import make_storage

    app_settings = AppSettings.from_env()
    storage = make_storage(
        storage_backend=app_settings.storage_backend,
        storage_root=app_settings.storage_root,
        default_config=app_settings.default_config_path,
    )
    settings = app_settings.load_settings(project_name)
    return storage, settings


# ── Global analysis → chord dispatch ─────────────────────────────────────────

@app.task(
    bind=True,
    name="vlm.global",
    queue="vlm",
    acks_late=True,
    max_retries=1,
    time_limit=3600,
    soft_time_limit=3540,
)
def task_vlm_global(self, prev: dict) -> None:
    """Run global video analysis then fan out per-segment tasks via chord.

    Receives the return dict from ``task_flow_and_segment``.  Calls
    ``self.replace()`` to swap itself for a Celery chord — nothing should
    follow this task in the pipeline chain.
    """
    from celery import chord, group
    from core.schemas.segment import SegmentBase
    from core.schemas.video_description import VideoDescription

    project_name = prev["project_name"]
    video_hash = prev["video_hash"]
    downsampled_key = prev["downsampled_key"]
    video_storage_key = prev["video_storage_key"]

    self.update_state(
        state="STARTED",
        meta={"current_step": "vlm_global", "project": project_name, "video_hash": video_hash},
    )

    storage, settings = _get_storage_and_settings(project_name)

    segments: list[SegmentBase] = storage.load_json(
        project_name,
        f"videos/{video_hash}/segments/segments.json",
        schema=SegmentBase,
    )

    vlm_cfg = settings.vlm
    backend = create_vlm_backend(vlm_cfg)
    try:
        with storage.backend.local_path(downsampled_key) as ds_path:
            log.info("task_vlm_global: running global analysis project=%s hash=%s", project_name, video_hash)
            video_vlm = _analyze_global(backend, ds_path)

        video_desc = VideoDescription(
            video_id=video_hash,
            video_file=video_storage_key.split("/")[-1],
            vlm=video_vlm,
        )
        storage.save_json(project_name, f"videos/{video_hash}/descriptions/vlm.json", video_desc)
        log.info("task_vlm_global: global description saved project=%s hash=%s", project_name, video_hash)

        # Ensure clips directory exists before segment tasks run.
        clips_dir = (
            storage.get_project_path(project_name)
            / "videos" / video_hash / "segments" / "clips"
        )
        clips_dir.mkdir(parents=True, exist_ok=True)

        global_summary = video_vlm.description
    finally:
        backend.close()

    # Pass full segment dicts so task_vlm_segment can reconstruct SegmentBase.
    segment_tasks = group(
        task_vlm_segment.s(
            project_name,
            video_hash,
            seg.model_dump(),
            global_summary,
            downsampled_key,
            video_storage_key,
        )
        for seg in segments
    )

    log.info(
        "task_vlm_global: dispatching chord of %d segment tasks project=%s hash=%s",
        len(segments), project_name, video_hash,
    )
    self.replace(chord(segment_tasks, task_vlm_collect.s(project_name, video_hash)))


# ── Per-segment extract + describe ────────────────────────────────────────────

@app.task(
    bind=True,
    name="vlm.segment",
    queue="vlm",
    acks_late=True,
    max_retries=2,
    time_limit=600,
    soft_time_limit=540,
    rate_limit="30/m",
)
def task_vlm_segment(
    self,
    project_name: str,
    video_hash: str,
    segment_data: dict,
    global_summary: str,
    downsampled_key: str,
    video_storage_key: str,
) -> dict | None:
    """Extract a clip and run VLM analysis for one segment.

    Args:
        project_name:    Project identifier.
        video_hash:      Content hash of the source video.
        segment_data:    ``SegmentBase.model_dump()`` for the segment to process.
        global_summary:  VLM description of the full video (from task_vlm_global).
        downsampled_key: Storage key for the downsampled video.
        video_storage_key: Storage key for the original video file.

    Returns:
        ``SegmentDescription.model_dump()`` on success, or ``None`` on analysis
        failure (the segment is skipped but the chord continues).
    """
    from core.schemas.segment import SegmentBase
    from video.clip import extract_clip

    storage, settings = _get_storage_and_settings(project_name)
    vlm_cfg = settings.vlm

    segment = SegmentBase.model_validate(segment_data)
    segment_id = segment.segment_id

    clips_dir = (
        storage.get_project_path(project_name)
        / "videos" / video_hash / "segments" / "clips"
    )
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_path = clips_dir / f"seg_{segment_id}.mp4"

    with storage.backend.local_path(downsampled_key) as ds_path:
        if not clip_path.exists():
            log.info("task_vlm_segment: extracting clip segment=%s project=%s", segment_id, project_name)
            extract_clip(ds_path, segment.start, segment.end, clip_path)
        else:
            log.info("task_vlm_segment: reusing clip segment=%s project=%s", segment_id, project_name)

    backend = create_vlm_backend(vlm_cfg)
    try:
        log.info("task_vlm_segment: analysing segment=%s project=%s", segment_id, project_name)
        # Pass empty all_segments list — full context is in global_summary; individual
        # per-segment analysis does not require the complete segment list.
        desc = _analyze_segment(backend, clip_path, segment, global_summary, [])
    finally:
        backend.close()

    if desc is None:
        log.warning("task_vlm_segment: analysis returned None for segment=%s project=%s", segment_id, project_name)
        return None

    return desc.model_dump()


# ── Chord callback: collect + persist ─────────────────────────────────────────

@app.task(
    bind=True,
    name="vlm.collect",
    queue="vlm",
    acks_late=True,
    max_retries=1,
    time_limit=300,
)
def task_vlm_collect(self, segment_results: list, project_name: str, video_hash: str) -> dict:
    """Aggregate per-segment VLM results and persist.

    Chord callback — receives a list with one entry per segment task (in
    dispatch order).  Each entry is either a ``SegmentDescription`` dict or
    ``None`` (analysis failed for that segment).
    """
    from core.schemas.segment import SegmentDescription
    from core.tracing import flush_langfuse

    self.update_state(
        state="STARTED",
        meta={"current_step": "vlm_collect", "project": project_name, "video_hash": video_hash},
    )

    storage, settings = _get_storage_and_settings(project_name)

    descriptions: list[SegmentDescription] = []
    for result in segment_results:
        if result is None:
            continue
        try:
            descriptions.append(SegmentDescription.model_validate(result))
        except Exception as exc:
            log.warning("task_vlm_collect: invalid segment result skipped: %s", exc)

    storage.save_json(
        project_name,
        f"videos/{video_hash}/segments/descriptions.json",
        descriptions,
    )
    log.info(
        "task_vlm_collect: saved %d descriptions project=%s hash=%s",
        len(descriptions), project_name, video_hash,
    )

    storage.mark_step_complete(project_name, video_hash, "described", settings)

    # Transition project status to ready when all videos in the project are described.
    manifest = storage._load_manifest(project_name)
    all_described = all(
        entry.get("processing", {}).get("described") is not None
        for entry in manifest.get("videos", {}).values()
    )
    if all_described:
        from core.project import ProjectStatus
        project = storage.get_project(project_name)
        project.status = ProjectStatus.ready
        storage.save_project(project)
        log.info("task_vlm_collect: all videos described — project status → ready project=%s", project_name)

    flush_langfuse()

    return {
        "project_name": project_name,
        "video_hash": video_hash,
        "status": "described",
        "description_count": len(descriptions),
    }
