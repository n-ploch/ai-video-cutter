"""API response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class VideoProcessingStatus(BaseModel):
    video_hash: str
    filename: str
    # step → ISO timestamp (None = not yet completed)
    steps: dict[str, str | None]
    config_hash: str | None
    storage_key: str | None
    celery_task_id: str | None
    celery_state: str | None   # PENDING | STARTED | SUCCESS | FAILURE | RETRY
    current_step: str | None   # Most informative step name for the UI


class AgentTaskStatus(BaseModel):
    task_id: str | None = None
    celery_state: str | None = None
    has_output: bool = False
    awaiting_human: bool = False
    thread_id: str | None = None
    paused_at: list[str] = []


class ProjectResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime
    video_count: int
    has_storyboard: bool
    has_timeline: bool


class ProjectDetailResponse(ProjectResponse):
    videos: list[VideoProcessingStatus]
    storyboard: AgentTaskStatus
    editor: AgentTaskStatus
    config: dict


class VideoUploadResponse(BaseModel):
    video_hash: str
    filename: str
    task_id: str
    status: str = "queued"


class TaskResponse(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class ConfigResponse(BaseModel):
    config: dict
    config_hash: str


class ExportResponse(BaseModel):
    version: str
    otio_url: str
    total_segments: int
    total_duration: float
