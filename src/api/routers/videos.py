"""Video upload and pipeline management endpoints."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_app_settings, get_storage
from api.schemas.responses import VideoProcessingStatus, VideoUploadResponse
from core.config import AppSettings
from core.storage import ProjectStorage, hash_video_file

log = logging.getLogger(__name__)
router = APIRouter()


def _manifest_to_status(
    video_hash: str,
    entry: dict,
    project: object,
) -> VideoProcessingStatus:
    celery_task_id = project.task_ids.get(video_hash)
    celery_state = None
    current_step = None

    if celery_task_id:
        from celery.result import AsyncResult
        from worker.celery_app import app as celery_app
        result = AsyncResult(celery_task_id, app=celery_app)
        celery_state = result.state
        if celery_state == "STARTED" and isinstance(result.info, dict):
            current_step = result.info.get("current_step")

    # Derive current_step from manifest when Celery isn't reporting it.
    if current_step is None:
        steps = entry.get("processing", {})
        completed = [s for s, v in steps.items() if v is not None]
        if completed:
            current_step = completed[-1]

    return VideoProcessingStatus(
        video_hash=video_hash,
        filename=entry.get("filename", ""),
        steps=entry.get("processing", {}),
        config_hash=entry.get("config_hash"),
        storage_key=entry.get("storage_key"),
        celery_task_id=celery_task_id,
        celery_state=celery_state,
        current_step=current_step,
    )


@router.get("/{project_name}/videos", response_model=list[VideoProcessingStatus])
def list_videos(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    manifest = storage._load_manifest(project_name)
    return [
        _manifest_to_status(h, entry, project)
        for h, entry in manifest.get("videos", {}).items()
    ]


@router.get("/{project_name}/videos/{video_hash}/status", response_model=VideoProcessingStatus)
def get_video_status(
    project_name: str,
    video_hash: str,
    storage: ProjectStorage = Depends(get_storage),
):
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    manifest = storage._load_manifest(project_name)
    entry = manifest.get("videos", {}).get(video_hash)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Video '{video_hash}' not found in project")

    return _manifest_to_status(video_hash, entry, project)


@router.post("/{project_name}/videos", response_model=VideoUploadResponse, status_code=202)
async def upload_video(
    project_name: str,
    file: UploadFile = File(...),
    include_vlm: bool = True,
    storage: ProjectStorage = Depends(get_storage),
    app_settings: AppSettings = Depends(get_app_settings),
):
    """Upload a video file and trigger the processing pipeline.

    The file is streamed to a temporary location, hashed, then moved into
    project storage.  A Celery chain (downsample → flow+segment → vlm) is
    dispatched and the root task ID is returned.
    """
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    suffix = Path(file.filename).suffix if file.filename else ".mp4"

    # Stream upload to a temp file to avoid loading into memory.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            shutil.copyfileobj(file.file, tmp)
        finally:
            file.file.close()

    try:
        video_hash = hash_video_file(tmp_path)

        # Destination key: {project_name}/videos/{hash}/original{suffix}
        storage_key = f"{project_name}/videos/{video_hash}/original{suffix}"
        dest_path = storage.root / storage_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Idempotent: if the same file was uploaded before, skip the copy.
        if not dest_path.exists():
            shutil.move(str(tmp_path), dest_path)
        else:
            tmp_path.unlink(missing_ok=True)

        # Register in manifest (idempotent).
        storage.add_video(project_name, dest_path)

        # Write storage_key into the manifest entry so workers can find the file.
        manifest = storage._load_manifest(project_name)
        if video_hash in manifest["videos"]:
            manifest["videos"][video_hash]["storage_key"] = storage_key
            storage._save_manifest(project_name, manifest)

        # Dispatch Celery chain.
        from worker.video_tasks import build_video_pipeline_chain
        chain = build_video_pipeline_chain(project_name, storage_key, include_vlm=include_vlm)
        async_result = chain.apply_async()
        root_task_id = async_result.id

        # Persist task ID in project so the status endpoint can query it.
        project.task_ids[video_hash] = root_task_id
        storage.save_project(project)

        log.info(
            "upload_video: project=%s hash=%s task_id=%s",
            project_name, video_hash, root_task_id,
        )
        return VideoUploadResponse(
            video_hash=video_hash,
            filename=file.filename or f"video{suffix}",
            task_id=root_task_id,
            status="queued",
        )

    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
