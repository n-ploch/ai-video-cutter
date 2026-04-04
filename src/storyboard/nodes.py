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
    STORY_JUDGE_PROMPT,
    STORY_WRITING_PROMPT,
)
from core.schemas.storyboard import JudgeResult, StoryJudgeResult
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
        log.info("story_writer: writing story (story_revision_count=%d)", state["story_revision_count"])
        prompt = STORY_WRITING_PROMPT.format(
            user_brief=state["user_brief"],
            video_descriptions=state["video_descriptions"],
        )
        if state.get("story_judge_feedback"):
            prompt += f"\n\n### Story editor feedback (revision {state['story_revision_count']})\n{state['story_judge_feedback']}"
        story = _invoke(llm, prompt)
        return {"story": story}
    return story_writer_node


def make_story_judge_node(llm: BaseChatModel, review_threshold: float, context_threshold: float = 0.5):
    structured_llm = llm.with_structured_output(StoryJudgeResult)

    def story_judge_node(state: StoryboardState) -> dict:
        log.info(
            "story_judge: evaluating story (story_revision_count=%d, threshold=%.2f)",
            state["story_revision_count"],
            review_threshold,
        )
        prompt = STORY_JUDGE_PROMPT.format(
            user_brief=state["user_brief"],
            video_descriptions=state["video_descriptions"],
            story=state["story"],
        )
        result: StoryJudgeResult = structured_llm.invoke([HumanMessage(content=prompt)])

        # Override decision: context hard floor takes priority, then threshold / max-revision cap
        if result.context_adherence < context_threshold:
            decision = "revise"
        elif result.total_score >= review_threshold or state["story_revision_count"] >= state["max_revisions"]:
            decision = "approve"
        else:
            decision = "revise"

        log.info(
            "story_judge: narrative=%.2f brief=%.2f context=%.2f total=%.2f decision=%s",
            result.narrative_quality, result.brief_adherence, result.context_adherence,
            result.total_score, decision,
        )
        return {
            "story_judge_narrative_quality": result.narrative_quality,
            "story_judge_brief_adherence": result.brief_adherence,
            "story_judge_context_adherence": result.context_adherence,
            "story_judge_total_score": result.total_score,
            "story_judge_feedback": result.feedback,
            "story_judge_decision": decision,
            "story_revision_count": state["story_revision_count"] + 1,
        }
    return story_judge_node


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
    structured_llm = llm.with_structured_output(JudgeResult)

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
        result: JudgeResult = structured_llm.invoke([HumanMessage(content=prompt)])

        # Override decision based on threshold to ensure consistency
        if result.score >= review_threshold:
            decision = "approve"
        elif state["revision_count"] >= state["max_revisions"]:
            decision = "escalate"
        else:
            decision = "revise"

        log.info("judge: score=%.2f decision=%s", result.score, decision)
        return {
            "judge_score": result.score,
            "judge_feedback": result.feedback,
            "judge_decision": decision,
        }
    return judge_node


def make_persist_node(storage, project_name: str):
    """Persist the final storyboard to versioned project storage."""
    from core.schemas.storyboard import NarrationBeat, StoryboardOutput, StoryboardScene

    def persist_node(state: StoryboardState) -> dict:

        output = StoryboardOutput(
            story=state["story"],
            narration_beats=[NarrationBeat.model_validate(b) for b in state["narration_beats"]],
            scenes=[StoryboardScene.model_validate(s) for s in state["scenes"]],
            story_judge_result=StoryJudgeResult(
                narrative_quality=state["story_judge_narrative_quality"],
                brief_adherence=state["story_judge_brief_adherence"],
                context_adherence=state["story_judge_context_adherence"],
                total_score=state["story_judge_total_score"],
                feedback=state["story_judge_feedback"],
                decision=state["story_judge_decision"],
            ),
            story_revision_count=state["story_revision_count"],
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
