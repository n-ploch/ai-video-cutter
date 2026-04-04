from __future__ import annotations

from pydantic import BaseModel


class StoryboardScene(BaseModel):
    index: int
    segment_index: int
    description: str = ""


class NarrationSegment(BaseModel):
    scene_index: int
    narration: str = ""


class Storyboard(BaseModel):
    scenes: list[StoryboardScene] = []
    narration: list[NarrationSegment] = []
