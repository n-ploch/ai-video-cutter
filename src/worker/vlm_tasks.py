"""VLM description Celery task (queue: vlm).

Receives the output dict from task_flow_and_segment.  Reloads segments from
storage (PersistStep already wrote them), then runs VLMStep which:
  1. Uploads the downsampled video to Gemini File API for global analysis.
  2. Extracts per-segment clips (reuses existing clips).
  3. Uploads each clip for per-segment analysis.
  4. Writes descriptions.json and marks the "described" manifest step.
"""
from __future__ import annotations

import logging

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


@app.task(
    bind=True,
    name="vlm.describe",
    queue="vlm",
    acks_late=True,
    max_retries=2,
    time_limit=7200,
    soft_time_limit=7140,
)
def task_vlm_describe(self, prev: dict) -> dict:
    """Run VLM scene description for all segments of a video.

    Receives the return dict from ``task_flow_and_segment``.  Can also be
    called standalone with the same dict shape if re-running descriptions.
    """
    from core.schemas.segment import SegmentBase
    from video.pipeline import PipelineContext
    from video.vlm import VLMStep

    project_name = prev["project_name"]
    video_hash = prev["video_hash"]
    downsampled_key = prev["downsampled_key"]
    video_storage_key = prev["video_storage_key"]

    self.update_state(
        state="STARTED",
        meta={"current_step": "vlm_describe", "project": project_name, "video_hash": video_hash},
    )

    storage, settings = _get_storage_and_settings(project_name)

    # Reload segments saved by PersistStep — avoids any numpy serialisation.
    segments: list[SegmentBase] = storage.load_json(
        project_name,
        f"videos/{video_hash}/segments/segments.json",
        schema=SegmentBase,
    )

    with (
        storage.backend.local_path(video_storage_key) as video_path,
        storage.backend.local_path(downsampled_key) as ds_path,
    ):
        ctx = PipelineContext(
            video_path=video_path,
            project_name=project_name,
            project_id=project_name,
            video_hash=video_hash,
            segments=segments,
            downsampled_path=ds_path,
        )
        vlm_step = VLMStep(storage, settings)
        vlm_step.check_inputs(ctx)
        vlm_step.run(ctx)

    from core.tracing import flush_langfuse
    flush_langfuse()

    log.info(
        "task_vlm_describe: project=%s hash=%s → %d descriptions",
        project_name, video_hash, len(segments),
    )
    return {
        "project_name": project_name,
        "video_hash": video_hash,
        "status": "described",
        "description_count": len(segments),
    }
