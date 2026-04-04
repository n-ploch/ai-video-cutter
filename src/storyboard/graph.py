"""LangGraph storyboard agent graph."""
from __future__ import annotations

import json
import logging

from langgraph.graph import END, START, StateGraph

from core.config import StoryboardConfig
from core.schemas.storyboard import StoryboardOutput
from core.storage import ProjectStorage
from storyboard.llm import create_llm
from storyboard.nodes import (
    make_director_node,
    make_judge_node,
    make_narrator_node,
    make_persist_node,
    make_story_writer_node,
)
from storyboard.state import StoryboardState

log = logging.getLogger(__name__)


def _format_video_descriptions(segments: list[Segment]) -> str:
    """Produce a compact text block of all segment descriptions for use in prompts."""
    lines: list[str] = []
    for seg in segments:
        for desc in seg.vlm:
            lines.append(
                f"[Segment {seg.segment_id} | {seg.start:.1f}s–{seg.end:.1f}s] "
                f"{desc.description}"
            )
    return "\n".join(lines) if lines else "(no segment descriptions available)"


def _route_judge(state: StoryboardState) -> str:
    decision = state["judge_decision"]
    if decision == "approve":
        return "persist"
    if decision == "escalate":
        return "story_writer"
    return "director"


def build_graph(
    cfg: StoryboardConfig,
    storage: ProjectStorage,
    project_name: str,
) -> StateGraph:
    """Build and compile the storyboard LangGraph graph."""
    story_writer_llm = create_llm(cfg.story_writer)
    narrator_llm = create_llm(cfg.narrator)
    director_llm = create_llm(cfg.director)
    judge_llm = create_llm(cfg.judge)

    graph = StateGraph(StoryboardState)

    graph.add_node("story_writer", make_story_writer_node(story_writer_llm))
    graph.add_node("narrator", make_narrator_node(narrator_llm))
    graph.add_node("director", make_director_node(director_llm))
    graph.add_node("judge", make_judge_node(judge_llm, cfg.review_threshold))
    graph.add_node("persist", make_persist_node(storage, project_name))

    graph.add_edge(START, "story_writer")
    graph.add_edge("story_writer", "narrator")
    graph.add_edge("narrator", "director")
    graph.add_edge("director", "judge")
    graph.add_conditional_edges(
        "judge",
        _route_judge,
        {"persist": "persist", "story_writer": "story_writer", "director": "director"},
    )
    graph.add_edge("persist", END)

    if cfg.human_in_the_loop:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        return graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["director"],
        )

    return graph.compile()


def run(
    project_name: str,
    user_brief: str,
    cfg: StoryboardConfig,
    storage: ProjectStorage,
) -> StoryboardOutput:
    """Run the full storyboard agent graph and return the persisted output."""
    from core.schemas.segment import Segment, SegmentBase, SegmentDescription, build_combined_view

    # Build combined Segment views (SegmentBase + SegmentDescription) for all video hashes.
    segments: list[Segment] = []
    videos_dir = storage.get_project_path(project_name) / "videos"
    for seg_file in sorted(videos_dir.rglob("segments/segments.json")):
        video_hash = seg_file.parts[seg_file.parts.index("videos") + 1]
        rel_base = f"videos/{video_hash}/segments/segments.json"
        rel_desc = f"videos/{video_hash}/segments/descriptions.json"
        try:
            bases: list[SegmentBase] = storage.load_json(
                project_name, rel_base, schema=SegmentBase
            )
            descs: list[SegmentDescription] = storage.load_json(
                project_name, rel_desc, schema=SegmentDescription
            )
        except FileNotFoundError:
            log.warning("Skipping %s — descriptions not found, run 'vc process --describe' first.", video_hash)
            continue
        segments.extend(build_combined_view(bases, descs))

    if not segments:
        log.warning("No combined segments found for project '%s'; video context will be empty.", project_name)

    video_descriptions = _format_video_descriptions(segments)

    compiled = build_graph(cfg, storage, project_name)

    initial_state: StoryboardState = {
        "project_name": project_name,
        "user_brief": user_brief,
        "video_descriptions": video_descriptions,
        "story": "",
        "narration_beats": [],
        "scenes": [],
        "judge_score": 0.0,
        "judge_feedback": "",
        "judge_decision": "",
        "revision_count": 0,
        "max_revisions": cfg.max_revisions,
    }

    config = {"configurable": {"thread_id": project_name}} if cfg.human_in_the_loop else {}
    final_state = compiled.invoke(initial_state, config=config)

    # Load and return the persisted output
    return storage.load_json(project_name, "storyboard/latest.json", schema=StoryboardOutput)
