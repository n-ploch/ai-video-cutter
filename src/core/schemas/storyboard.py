from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NarrationBeat(BaseModel):
    id: int
    text: str


class StoryboardScene(BaseModel):
    id: int
    narration_segment: str
    scene_description: str
    reasoning: str
    keywords: list[str]


class JudgeResult(BaseModel):
    score: float
    feedback: str
    decision: Literal["approve", "revise", "escalate"]


class StoryboardOutput(BaseModel):
    story: str
    narration_beats: list[NarrationBeat]
    scenes: list[StoryboardScene]
    judge_result: JudgeResult
    revision_count: int
