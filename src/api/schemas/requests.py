"""API request schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_\-]+$")


class StoryboardTriggerRequest(BaseModel):
    brief: str = Field(..., min_length=1)
    human_in_the_loop: bool = False


class StoryboardResumeRequest(BaseModel):
    thread_id: str
    # Optional revised brief injected into the LangGraph state before resuming.
    feedback: str | None = None


class EditorTriggerRequest(BaseModel):
    human_in_the_loop: bool = False


class EditorResumeRequest(BaseModel):
    thread_id: str
    # Human-supplied per-scene overrides, keyed by scene_id.
    gate_overrides: dict = Field(default_factory=dict)


class ExportRequest(BaseModel):
    version: str = "latest"
    rate: float = Field(default=30.0, gt=0)
