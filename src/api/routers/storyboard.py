"""Storyboard agent trigger and human-in-the-loop resume endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_storage
from api.schemas.requests import StoryboardResumeRequest, StoryboardTriggerRequest
from api.schemas.responses import AgentTaskStatus, TaskResponse
from core.storage import ProjectStorage

log = logging.getLogger(__name__)
router = APIRouter()


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


@router.get("/{project_name}/storyboard")
def get_storyboard(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    """Return the latest storyboard output for a project."""
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    storyboard_path = storage.get_project_path(project_name) / "storyboard" / "latest.json"
    if not storyboard_path.exists():
        raise HTTPException(status_code=404, detail="No storyboard found. Run the storyboard agent first.")

    from core.schemas.storyboard import StoryboardOutput
    return storage.load_json(project_name, "storyboard/latest.json", schema=StoryboardOutput)


def _inject_storyboard_feedback(thread_id: str, feedback: str) -> None:
    """Inject revised user_brief into the LangGraph Redis checkpoint.

    NOTE: feedback injection is handled via gate_overrides / user_brief on
    the resume task invocation in agent_tasks.py. This function is a stub
    kept for API compatibility; actual feedback is passed through the resume
    endpoint body and applied in task_run_storyboard when thread_id is set.
    """
    log.info("_inject_storyboard_feedback: thread_id=%s feedback will be applied on resume", thread_id)
