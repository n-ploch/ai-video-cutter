"""LangGraph node implementations for the storyboard agent graph."""
from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from core.prompts import (
    NARRATION_PROMPT,
    STORYBOARD_JUDGE_PROMPT,
    STORYBOARD_PROMPT,
    STORY_WRITING_PROMPT,
)
from storyboard.state import StoryboardState

log = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _invoke(llm: BaseChatModel, prompt: str) -> str:
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()


def _parse_json(text: str) -> dict | list:
    # Strip optional markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


# ── nodes ─────────────────────────────────────────────────────────────────────

def make_story_writer_node(llm: BaseChatModel):
    def story_writer_node(state: StoryboardState) -> dict:
        log.info("story_writer: writing story (revision_count=%d)", state["revision_count"])
        prompt = STORY_WRITING_PROMPT.format(
            user_brief=state["user_brief"],
            video_descriptions=state["video_descriptions"],
        )
        story = _invoke(llm, prompt)
        return {"story": story}
    return story_writer_node


def make_narrator_node(llm: BaseChatModel):
    def narrator_node(state: StoryboardState) -> dict:
        log.info("narrator: breaking story into narration beats")
        prompt = NARRATION_PROMPT.format(story=state["story"])
        raw = _invoke(llm, prompt)
        data = _parse_json(raw)
        beats = data.get("narration_segments", data) if isinstance(data, dict) else data
        return {"narration_beats": beats}
    return narrator_node


def make_director_node(llm: BaseChatModel):
    def director_node(state: StoryboardState) -> dict:
        revision = state["revision_count"] + 1
        log.info("director: building storyboard (attempt %d)", revision)

        beats_text = "\n".join(
            f"{b['id']}. {b['text']}" for b in state["narration_beats"]
        )
        prompt = STORYBOARD_PROMPT.format(
            narration_segments=beats_text,
            video_descriptions=state["video_descriptions"],
        )
        # Append judge feedback when revising
        if state.get("judge_feedback"):
            prompt += f"\n\n### Director's note (revision {revision})\n{state['judge_feedback']}"

        raw = _invoke(llm, prompt)
        data = _parse_json(raw)
        scenes = data.get("scenes", data) if isinstance(data, dict) else data
        return {"scenes": scenes, "revision_count": revision}
    return director_node


def make_judge_node(llm: BaseChatModel, review_threshold: float):
    def judge_node(state: StoryboardState) -> dict:
        log.info(
            "judge: evaluating storyboard (revision_count=%d, threshold=%.2f)",
            state["revision_count"],
            review_threshold,
        )
        scenes_text = json.dumps(state["scenes"], indent=2)
        prompt = STORYBOARD_JUDGE_PROMPT.format(
            story=state["story"],
            scenes=scenes_text,
        )
        raw = _invoke(llm, prompt)
        result = _parse_json(raw)

        score: float = float(result.get("score", 0.0))
        feedback: str = result.get("feedback", "")
        decision: str = result.get("decision", "revise")

        # Override decision based on threshold to ensure consistency
        if score >= review_threshold:
            decision = "approve"
        elif state["revision_count"] >= state["max_revisions"]:
            decision = "escalate"
        else:
            decision = "revise"

        log.info("judge: score=%.2f decision=%s", score, decision)
        return {
            "judge_score": score,
            "judge_feedback": feedback,
            "judge_decision": decision,
        }
    return judge_node


def make_persist_node(storage, project_name: str):
    """Persist the final storyboard to versioned project storage."""
    from core.schemas.storyboard import (
        JudgeResult,
        NarrationBeat,
        StoryboardOutput,
        StoryboardScene,
    )

    def persist_node(state: StoryboardState) -> dict:
        output = StoryboardOutput(
            story=state["story"],
            narration_beats=[NarrationBeat.model_validate(b) for b in state["narration_beats"]],
            scenes=[StoryboardScene.model_validate(s) for s in state["scenes"]],
            judge_result=JudgeResult(
                score=state["judge_score"],
                feedback=state["judge_feedback"],
                decision=state["judge_decision"],
            ),
            revision_count=state["revision_count"],
        )
        version = storage.save_versioned(project_name, "storyboard", output)
        log.info("persist: saved storyboard v%d for project '%s'", version, project_name)
        return {}
    return persist_node
