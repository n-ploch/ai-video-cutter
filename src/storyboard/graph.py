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
    make_story_judge_node,
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


def _route_story_judge(state: StoryboardState) -> str:
    return "narrator" if state["story_judge_decision"] == "approve" else "story_writer"


def _route_judge(state: StoryboardState) -> str:
    decision = state["judge_decision"]
    if decision == "approve":
        return "persist"
    if decision == "escalate":
        return "story_writer"
    return "director"


def _build_uncompiled_graph(
    cfg: StoryboardConfig,
    storage: ProjectStorage,
    project_name: str,
) -> StateGraph:
    """Return the raw (uncompiled) StateGraph shared by build_graph variants."""
    story_writer_llm = create_llm(cfg.story_writer)
    story_judge_llm = create_llm(cfg.story_judge)
    narrator_llm = create_llm(cfg.narrator)
    director_llm = create_llm(cfg.director)
    judge_llm = create_llm(cfg.judge)

    graph = StateGraph(StoryboardState)

    graph.add_node("story_writer", make_story_writer_node(story_writer_llm))
    graph.add_node("story_judge", make_story_judge_node(story_judge_llm, cfg.review_threshold, cfg.context_threshold))
    graph.add_node("narrator", make_narrator_node(narrator_llm))
    graph.add_node("director", make_director_node(director_llm))
    graph.add_node("judge", make_judge_node(judge_llm, cfg.review_threshold))
    graph.add_node("persist", make_persist_node(storage, project_name))

    graph.add_edge(START, "story_writer")
    graph.add_edge("story_writer", "story_judge")
    graph.add_conditional_edges(
        "story_judge",
        _route_story_judge,
        {"narrator": "narrator", "story_writer": "story_writer"},
    )
    graph.add_edge("narrator", "director")
    graph.add_edge("director", "judge")
    graph.add_conditional_edges(
        "judge",
        _route_judge,
        {"persist": "persist", "story_writer": "story_writer", "director": "director"},
    )
    graph.add_edge("persist", END)
    return graph


def build_graph(
    cfg: StoryboardConfig,
    storage: ProjectStorage,
    project_name: str,
):
    """Build and compile the storyboard LangGraph graph (CLI / in-process use)."""
    graph = _build_uncompiled_graph(cfg, storage, project_name)

    if cfg.human_in_the_loop:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        return graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["director"],
        )

    return graph.compile()


def build_graph_with_checkpointer(
    cfg: StoryboardConfig,
    storage: ProjectStorage,
    project_name: str,
    checkpointer,
    human_in_the_loop: bool | None = None,
):
    """Build and compile the storyboard graph with an external checkpointer.

    Used by the Celery worker layer so that graph state is persisted to Redis
    (via ``RedisSaver``) rather than in-process memory, enabling the worker
    to exit after hitting an interrupt and resume in a subsequent task.

    ``human_in_the_loop`` overrides ``cfg.human_in_the_loop`` when provided,
    allowing the API caller to enable/disable gates per-request without
    modifying the project config on disk.
    """
    hitl = human_in_the_loop if human_in_the_loop is not None else cfg.human_in_the_loop
    graph = _build_uncompiled_graph(cfg, storage, project_name)
    interrupt_nodes = ["director"] if hitl else []
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes,
    )


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
        # story judge
        "story_judge_narrative_quality": 0.0,
        "story_judge_brief_adherence": 0.0,
        "story_judge_context_adherence": 0.0,
        "story_judge_total_score": 0.0,
        "story_judge_feedback": "",
        "story_judge_decision": "",
        "story_revision_count": 0,
        # storyboard judge
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
