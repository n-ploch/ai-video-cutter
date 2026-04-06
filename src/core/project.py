from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.schemas.video import VideoFile


class ProjectStatus(str, Enum):
    created = "created"
    analyzing = "analyzing"
    ready = "ready"


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    video_files: list[VideoFile] = []
    status: ProjectStatus = ProjectStatus.created
    # Celery task IDs keyed by purpose, e.g.:
    #   {video_hash: chain_root_task_id, "storyboard_task_id": ...,
    #    "storyboard_thread_id": ..., "editor_task_id": ...}
    task_ids: dict[str, str] = Field(default_factory=dict)
