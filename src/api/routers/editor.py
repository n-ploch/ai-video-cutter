"""Editor agent trigger and human-in-the-loop resume endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_storage
from api.schemas.requests import EditorResumeRequest, EditorTriggerRequest
from api.schemas.responses import TaskResponse
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


@router.post("/{project_name}/editor", response_model=TaskResponse, status_code=202)
def trigger_editor(
    project_name: str,
    body: EditorTriggerRequest,
    storage: ProjectStorage = Depends(get_storage),
):
    """Trigger the timeline assembly editor agent for a project.

    Requires a storyboard (``storyboard/latest.json``) and segment descriptions
    to already exist.  Runs asynchronously — poll status for progress.
    """
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    # Guard: block if any video pipeline task is still running.
    _check_videos_ready(project, storage, project_name)

    # Guard: block if an editor task is genuinely in flight right now.
    # Only STARTED and RETRY indicate an active task — PENDING means unknown/expired
    # in Celery and must not be treated as "running" (it would permanently block re-runs
    # after the Redis result TTL expires).
    existing_ed_id = project.task_ids.get("editor_task_id")
    if existing_ed_id:
        from celery.result import AsyncResult
        from worker.celery_app import app as celery_app
        if AsyncResult(existing_ed_id, app=celery_app).state in ("STARTED", "RETRY"):
            raise HTTPException(status_code=409, detail="An editor task is already running for this project.")

    if not (storage.get_project_path(project_name) / "storyboard" / "latest.json").exists():
        raise HTTPException(
            status_code=422,
            detail="No storyboard found. Run the storyboard agent first.",
        )

    from worker.agent_tasks import task_run_editor
    result = task_run_editor.delay(
        project_name,
        human_in_the_loop=body.human_in_the_loop or None,
        storyboard_version=body.storyboard_version,
    )

    project.task_ids["editor_task_id"] = result.id
    storage.save_project(project)

    log.info("trigger_editor: project=%s task_id=%s storyboard_version=%s", project_name, result.id, body.storyboard_version)
    return TaskResponse(task_id=result.id, status="queued")


@router.post("/{project_name}/editor/resume", response_model=TaskResponse, status_code=202)
def resume_editor(
    project_name: str,
    body: EditorResumeRequest,
    storage: ProjectStorage = Depends(get_storage),
):
    """Resume an editor run that paused at a human-review gate.

    ``gate_overrides`` is a dict of human-supplied decisions injected into
    the LangGraph state before resuming, e.g.::

        {"gate2_overrides": {"scene_001": {"chain_index": 0}},
         "flagged_scene_ids": ["scene_002"]}
    """
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    from worker.agent_tasks import task_run_editor
    result = task_run_editor.delay(
        project_name,
        thread_id=body.thread_id,
        gate_overrides=body.gate_overrides or None,
    )

    project.task_ids["editor_task_id"] = result.id
    project.task_ids["editor_thread_id"] = body.thread_id
    storage.save_project(project)

    log.info("resume_editor: project=%s thread_id=%s task_id=%s", project_name, body.thread_id, result.id)
    return TaskResponse(task_id=result.id, status="queued")


@router.get("/{project_name}/editor/versions")
def list_editor_versions(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    """Return metadata for all timeline versions of a project.

    Each entry includes ``version``, ``created_at``, ``storyboard_version``,
    and ``brief_snippet`` (first 120 chars of the user brief from the storyboard
    reference embedded in the timeline).
    """
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    entries = storage.list_versioned(project_name, "timeline")
    result = []
    for entry in entries:
        try:
            data = storage.load_json(project_name, f"timeline/v{entry['version']}.json")
            sb = data.get("storyboard") or {}
            storyboard_version = sb.get("version")
            brief = (sb.get("user_brief") or "")[:120] or None
        except Exception:
            storyboard_version = None
            brief = None
        result.append({**entry, "storyboard_version": storyboard_version, "brief_snippet": brief})
    return result


@router.get("/{project_name}/editor")
def get_timeline(
    project_name: str,
    version: int | None = Query(default=None),
    storage: ProjectStorage = Depends(get_storage),
):
    """Return a timeline output for a project.

    If ``version`` is provided, load that specific version (e.g. ``?version=2``).
    Otherwise returns the latest timeline.
    """
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    if version is not None:
        path = f"timeline/v{version}.json"
        if not (storage.get_project_path(project_name) / "timeline" / f"v{version}.json").exists():
            raise HTTPException(status_code=404, detail=f"Timeline version {version} not found.")
    else:
        path = "timeline/latest.json"
        if not (storage.get_project_path(project_name) / "timeline" / "latest.json").exists():
            raise HTTPException(status_code=404, detail="No timeline found. Run the editor agent first.")

    from core.schemas.editor import TimelineOutput
    return storage.load_json(project_name, path, schema=TimelineOutput)
