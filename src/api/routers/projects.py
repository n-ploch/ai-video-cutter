"""Project CRUD and configuration endpoints."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_app_settings, get_storage
from api.schemas.requests import CreateProjectRequest
from api.schemas.responses import ConfigResponse, ProjectDetailResponse, ProjectResponse
from core.config import AppSettings, Settings
from core.storage import ProjectStorage

log = logging.getLogger(__name__)
router = APIRouter()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _project_to_response(project, storage: ProjectStorage) -> ProjectResponse:
    project_dir = storage.get_project_path(project.name)
    has_storyboard = (project_dir / "storyboard" / "latest.json").exists()
    has_timeline = (project_dir / "timeline" / "latest.json").exists()
    return ProjectResponse(
        id=project.id,
        name=project.name,
        status=project.status.value,
        created_at=project.created_at,
        video_count=len(project.video_files),
        has_storyboard=has_storyboard,
        has_timeline=has_timeline,
    )


@router.get("", response_model=list[ProjectResponse])
def list_projects(storage: ProjectStorage = Depends(get_storage)):
    return [_project_to_response(p, storage) for p in storage.list_projects()]


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    body: CreateProjectRequest,
    storage: ProjectStorage = Depends(get_storage),
    app_settings: AppSettings = Depends(get_app_settings),
):
    project_dir = storage.get_project_path(body.name)
    if (project_dir / "project.json").exists():
        raise HTTPException(status_code=409, detail=f"Project '{body.name}' already exists")
    project = storage.create_project(body.name, [])
    return _project_to_response(project, storage)


@router.get("/{project_name}", response_model=ProjectDetailResponse)
def get_project(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    try:
        project = storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    from api.routers.status import _build_project_detail
    return _build_project_detail(project, storage)


@router.delete("/{project_name}", status_code=204)
def delete_project(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
):
    project_dir = storage.get_project_path(project_name)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    import shutil
    shutil.rmtree(project_dir)


@router.get("/{project_name}/config", response_model=ConfigResponse)
def get_config(
    project_name: str,
    storage: ProjectStorage = Depends(get_storage),
    app_settings: AppSettings = Depends(get_app_settings),
):
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    settings = app_settings.load_settings(project_name)
    return ConfigResponse(
        config=settings.model_dump(mode="json"),
        config_hash=settings.config_hash,
    )


@router.patch("/{project_name}/config", response_model=ConfigResponse)
def update_config(
    project_name: str,
    body: dict,
    storage: ProjectStorage = Depends(get_storage),
    app_settings: AppSettings = Depends(get_app_settings),
):
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    config_path = storage.get_project_path(project_name) / "config.yaml"
    current = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    merged = _deep_merge(current or {}, body)

    try:
        validated = Settings.model_validate(merged)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    config_path.write_text(yaml.dump(merged, default_flow_style=False, sort_keys=False))
    log.info("update_config: project=%s new config_hash=%s", project_name, validated.config_hash)
    return ConfigResponse(config=validated.model_dump(mode="json"), config_hash=validated.config_hash)
