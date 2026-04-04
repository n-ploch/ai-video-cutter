from __future__ import annotations

from typing import TypedDict


class StoryboardState(TypedDict):
    project_name: str
    user_brief: str
    video_descriptions: str   # pre-formatted text block passed to every prompt
    story: str
    narration_beats: list[dict]   # [{"id": int, "text": str}]
    scenes: list[dict]            # [{"id", "narration_segment", "scene_description", "reasoning", "keywords"}]
    judge_score: float
    judge_feedback: str
    judge_decision: str           # "approve" | "revise" | "escalate"
    revision_count: int
    max_revisions: int
