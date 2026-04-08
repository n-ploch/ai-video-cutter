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


class StoryJudgeResult(BaseModel):
    narrative_quality: float
    brief_adherence: float
    context_adherence: float
    total_score: float
    feedback: str
    decision: Literal["approve", "revise"]


class JudgeResult(BaseModel):
    score: float
    feedback: str
    decision: Literal["approve", "revise", "escalate"]


class StoryboardOutput(BaseModel):
    user_brief: str
    story: str
    narration_beats: list[NarrationBeat]
    scenes: list[StoryboardScene]
    story_judge_result: StoryJudgeResult | None = None
    story_revision_count: int = 0
    judge_result: JudgeResult
    revision_count: int
