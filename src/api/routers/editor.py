"""Editor agent trigger and human-in-the-loop resume endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_storage
from api.schemas.requests import EditorResumeRequest, EditorTriggerRequest
from api.schemas.responses import TaskResponse
from core.storage import ProjectStorage

log = logging.getLogger(__name__)
router = APIRouter()


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

    if not (storage.get_project_path(project_name) / "storyboard" / "latest.json").exists():
        raise HTTPException(
            status_code=422,
            detail="No storyboard found. Run the storyboard agent first.",
        )

    from worker.agent_tasks import task_run_editor
    result = task_run_editor.delay(
        project_name,
        human_in_the_loop=body.human_in_the_loop or None,
    )

    project.task_ids["editor_task_id"] = result.id
    storage.save_project(project)

    log.info("trigger_editor: project=%s task_id=%s", project_name, result.id)
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


@router.get("/{project_name}/editor")
def get_timeline(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    """Return the latest timeline output for a project."""
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    timeline_path = storage.get_project_path(project_name) / "timeline" / "latest.json"
    if not timeline_path.exists():
        raise HTTPException(status_code=404, detail="No timeline found. Run the editor agent first.")

    from core.schemas.editor import TimelineOutput
    return storage.load_json(project_name, "timeline/latest.json", schema=TimelineOutput)
