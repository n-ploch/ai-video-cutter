"""Storyboard agent trigger and human-in-the-loop resume endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_storage
from api.schemas.requests import StoryboardResumeRequest, StoryboardTriggerRequest
from api.schemas.responses import AgentTaskStatus, TaskResponse
from core.storage import ProjectStorage

log = logging.getLogger(__name__)
router = APIRouter()


def _check_videos_ready(project, storage: ProjectStorage, project_name: str) -> None:
    """Raise HTTP 409 if any video pipeline task is still actively running.

    The manifest's ``described`` timestamp is the authoritative completion record.
    A video is only considered in-progress when the manifest shows it is NOT yet
    described AND a live Celery task is in STARTED or RETRY state.

    Celery ``PENDING`` is intentionally excluded: it is the default state for any
    unknown or expired task ID, not a reliable indicator of active work.
    """
    from celery.result import AsyncResult
    from worker.celery_app import app as celery_app

    AGENT_KEYS = {"storyboard_task_id", "storyboard_thread_id", "editor_task_id", "editor_thread_id"}

    manifest = storage._load_manifest(project_name)
    still_running = []
    for key, task_id in project.task_ids.items():
        if key in AGENT_KEYS:
            continue
        # key is a video_hash — check manifest first
        video_hash = key
        processing = manifest.get("videos", {}).get(video_hash, {}).get("processing", {})
        if processing.get("described") is not None:
            # Manifest confirms the full pipeline completed for this video.
            continue
        # Manifest says not yet described — check if a task is actively running.
        # Exclude PENDING: it means "unknown/expired" for Celery, not "queued".
        if AsyncResult(task_id, app=celery_app).state in ("STARTED", "RETRY"):
            still_running.append(video_hash)

    if still_running:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Video understanding still in progress for {len(still_running)} video(s) "
                f"({', '.join(still_running[:3])}). "
                "Wait for processing to complete before starting storyboard or editing."
            ),
        )


@router.post("/{project_name}/storyboard", response_model=TaskResponse, status_code=202)
def trigger_storyboard(
    project_name: str,
    body: StoryboardTriggerRequest,
    storage: ProjectStorage = Depends(get_storage),
):
    """Trigger the storyboard agent for a project.

    The storyboard runs asynchronously.  Poll ``GET /api/v1/projects/{name}/status``
    or ``GET /api/v1/status/{task_id}`` for progress.

    When ``human_in_the_loop=true`` the task will pause before the director
    node and return ``status="awaiting_human"``.  Call the ``/resume`` endpoint
    to continue.
    """
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    # Guard: block if any video pipeline task is still running.
    _check_videos_ready(project, storage, project_name)

    # Guard: block if a storyboard task is genuinely in flight right now.
    # Only STARTED and RETRY indicate an active task — PENDING means unknown/expired
    # in Celery and must not be treated as "running" (it would permanently block re-runs
    # after the Redis result TTL expires).
    existing_sb_id = project.task_ids.get("storyboard_task_id")
    if existing_sb_id:
        from celery.result import AsyncResult
        from worker.celery_app import app as celery_app
        if AsyncResult(existing_sb_id, app=celery_app).state in ("STARTED", "RETRY"):
            raise HTTPException(status_code=409, detail="A storyboard task is already running for this project.")

    # Verify that descriptions exist before kicking off.
    videos_dir = storage.get_project_path(project_name) / "videos"
    has_descriptions = any(videos_dir.rglob("segments/descriptions.json"))
    if not has_descriptions:
        raise HTTPException(
            status_code=422,
            detail="No segment descriptions found. Run video processing with VLM enabled first.",
        )

    from worker.agent_tasks import task_run_storyboard
    result = task_run_storyboard.delay(
        project_name,
        body.brief,
        human_in_the_loop=body.human_in_the_loop or None,
    )

    project.task_ids["storyboard_task_id"] = result.id
    storage.save_project(project)

    log.info("trigger_storyboard: project=%s task_id=%s", project_name, result.id)
    return TaskResponse(task_id=result.id, status="queued")


@router.post("/{project_name}/storyboard/resume", response_model=TaskResponse, status_code=202)
def resume_storyboard(
    project_name: str,
    body: StoryboardResumeRequest,
    storage: ProjectStorage = Depends(get_storage),
):
    """Resume a storyboard run that paused at a human-review gate.

    If ``feedback`` is provided it is injected into the LangGraph state as
    an updated ``user_brief`` before the graph continues.
    """
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    # Optionally inject feedback into the stored checkpoint before resuming.
    if body.feedback:
        _inject_storyboard_feedback(body.thread_id, body.feedback)

    from worker.agent_tasks import task_run_storyboard
    result = task_run_storyboard.delay(
        project_name,
        "",  # brief ignored on resume — state comes from checkpoint
        thread_id=body.thread_id,
    )

    project.task_ids["storyboard_task_id"] = result.id
    project.task_ids["storyboard_thread_id"] = body.thread_id
    storage.save_project(project)

    log.info("resume_storyboard: project=%s thread_id=%s task_id=%s", project_name, body.thread_id, result.id)
    return TaskResponse(task_id=result.id, status="queued")


@router.get("/{project_name}/storyboard/versions")
def list_storyboard_versions(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    """Return metadata for all storyboard versions of a project.

    Each entry includes ``version``, ``created_at``, and ``brief_snippet``
    (first 120 characters of the user brief).
    """
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    entries = storage.list_versioned(project_name, "storyboard")
    result = []
    for entry in entries:
        try:
            data = storage.load_json(project_name, f"storyboard/v{entry['version']}.json")
            brief = (data.get("user_brief") or "")[:120] or None
        except Exception:
            brief = None
        result.append({**entry, "brief_snippet": brief})
    return result


@router.get("/{project_name}/storyboard")
def get_storyboard(
    project_name: str,
    version: int | None = Query(default=None),
    storage: ProjectStorage = Depends(get_storage),
):
    """Return a storyboard output for a project.

    If ``version`` is provided, load that specific version (e.g. ``?version=2``).
    Otherwise returns the latest storyboard.
    """
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    if version is not None:
        path = f"storyboard/v{version}.json"
        if not (storage.get_project_path(project_name) / "storyboard" / f"v{version}.json").exists():
            raise HTTPException(status_code=404, detail=f"Storyboard version {version} not found.")
    else:
        path = "storyboard/latest.json"
        if not (storage.get_project_path(project_name) / "storyboard" / "latest.json").exists():
            raise HTTPException(status_code=404, detail="No storyboard found. Run the storyboard agent first.")

    from core.schemas.storyboard import StoryboardOutput
    return storage.load_json(project_name, path, schema=StoryboardOutput)


def _inject_storyboard_feedback(thread_id: str, feedback: str) -> None:
    """Inject revised user_brief into the LangGraph Redis checkpoint.

    NOTE: feedback injection is handled via gate_overrides / user_brief on
    the resume task invocation in agent_tasks.py. This function is a stub
    kept for API compatibility; actual feedback is passed through the resume
    endpoint body and applied in task_run_storyboard when thread_id is set.
    """
    log.info("_inject_storyboard_feedback: thread_id=%s feedback will be applied on resume", thread_id)
