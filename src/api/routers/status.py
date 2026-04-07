"""Unified project status and Celery task status endpoints."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_storage
from api.schemas.responses import (
    AgentTaskStatus,
    ProjectDetailResponse,
    TaskResponse,
    VideoProcessingStatus,
)
from core.storage import ProjectStorage

log = logging.getLogger(__name__)
router = APIRouter()


def _celery_state(task_id: str | None) -> str | None:
    if not task_id:
        return None
    try:
        from celery.result import AsyncResult
        from worker.celery_app import app as celery_app
        return AsyncResult(task_id, app=celery_app).state
    except Exception:
        return None


def _celery_result(task_id: str | None) -> dict | None:
    if not task_id:
        return None
    try:
        from celery.result import AsyncResult
        from worker.celery_app import app as celery_app
        r = AsyncResult(task_id, app=celery_app)
        if r.state == "SUCCESS" and isinstance(r.result, dict):
            return r.result
    except Exception:
        return None
    return None


def _build_video_status(
    video_hash: str,
    entry: dict,
    project,
) -> VideoProcessingStatus:
    """Combine manifest entry + Celery task state into a VideoProcessingStatus."""
    celery_task_id = project.task_ids.get(video_hash)
    celery_state = None
    current_step = None

    if celery_task_id:
        try:
            from celery.result import AsyncResult
            from worker.celery_app import app as celery_app
            result = AsyncResult(celery_task_id, app=celery_app)
            celery_state = result.state
            if celery_state == "STARTED" and isinstance(result.info, dict):
                current_step = result.info.get("current_step")
        except Exception:
            pass

    if current_step is None:
        steps = entry.get("processing", {})
        completed = [s for s, v in steps.items() if v is not None]
        current_step = completed[-1] if completed else None

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


def _build_agent_status(
    task_id: str | None,
    thread_id: str | None,
    has_output: bool,
) -> AgentTaskStatus:
    state = _celery_state(task_id)
    result = _celery_result(task_id)

    awaiting_human = False
    paused_at: list[str] = []
    if result and result.get("status") == "awaiting_human":
        awaiting_human = True
        paused_at = result.get("paused_at", [])

    return AgentTaskStatus(
        task_id=task_id,
        celery_state=state,
        has_output=has_output,
        awaiting_human=awaiting_human,
        thread_id=thread_id,
        paused_at=paused_at,
    )


def _build_project_detail(project, storage: ProjectStorage) -> ProjectDetailResponse:
    project_dir = storage.get_project_path(project.name)
    manifest = storage._load_manifest(project.name)

    videos = [
        _build_video_status(h, entry, project)
        for h, entry in manifest.get("videos", {}).items()
    ]

    has_storyboard = (project_dir / "storyboard" / "latest.json").exists()
    has_timeline = (project_dir / "timeline" / "latest.json").exists()

    storyboard_status = _build_agent_status(
        task_id=project.task_ids.get("storyboard_task_id"),
        thread_id=project.task_ids.get("storyboard_thread_id"),
        has_output=has_storyboard,
    )
    editor_status = _build_agent_status(
        task_id=project.task_ids.get("editor_task_id"),
        thread_id=project.task_ids.get("editor_thread_id"),
        has_output=has_timeline,
    )

    try:
        from core.config import AppSettings
        settings = AppSettings.from_env().load_settings(project.name)
        config_dict = settings.model_dump(mode="json")
    except Exception:
        config_dict = {}

    return ProjectDetailResponse(
        id=project.id,
        name=project.name,
        status=project.status.value,
        created_at=project.created_at,
        video_count=len(project.video_files),
        has_storyboard=has_storyboard,
        has_timeline=has_timeline,
        videos=videos,
        storyboard=storyboard_status,
        editor=editor_status,
        config=config_dict,
    )


@router.get("/projects/{project_name}/status", response_model=ProjectDetailResponse)
def get_project_status(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    """Unified status for a project: videos, storyboard, and editor state."""
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    return _build_project_detail(project, storage)


@router.get("/status/{task_id}", response_model=TaskResponse)
def get_task_status(task_id: str):
    """Return the Celery task state and result for any task ID."""
    try:
        from celery.result import AsyncResult
        from worker.celery_app import app as celery_app

        result = AsyncResult(task_id, app=celery_app)
        state = result.state

        if state == "FAILURE":
            return TaskResponse(task_id=task_id, status=state, error=str(result.result))
        if state == "SUCCESS" and isinstance(result.result, dict):
            return TaskResponse(task_id=task_id, status=state, result=result.result)
        if state == "STARTED" and isinstance(result.info, dict):
            return TaskResponse(task_id=task_id, status=state, result=result.info)
        return TaskResponse(task_id=task_id, status=state)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
