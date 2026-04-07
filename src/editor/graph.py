"""LangGraph timeline assembly agent graph."""
from __future__ import annotations

import logging
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from core.config import EditorConfig
from core.schemas.editor import TimelineOutput
from core.storage import ProjectStorage
from editor.nodes import (
    deduplicate_candidates_node,
    make_assemble_scenes_node,
    make_build_index_node,
    make_fill_gaps_node,
    make_persist_timeline_node,
    make_retrieve_candidates_node,
    make_review_timeline_node,
    make_stitch_scenes_node,
)
from editor.state import EditorState
from storyboard.llm import create_llm

log = logging.getLogger(__name__)


# ── Routing ────────────────────────────────────────────────────────────────────

def _route_after_assemble(cfg: EditorConfig):
    def route(state: EditorState) -> str:
        if cfg.skip_stitching:
            return "persist_timeline" if cfg.skip_review else "review_timeline"
        return "stitch_scenes"
    return route


def _route_after_stitch(cfg: EditorConfig):
    def route(state: EditorState) -> str:
        return "persist_timeline" if cfg.skip_review else "review_timeline"
    return route


def _route_review(state: EditorState) -> str:
    review = state.get("review") or {}
    if not review.get("has_structural_issues", False):
        return "persist_timeline"
    if state["gate2_round"] >= state["max_gate2_rounds"]:
        log.warning(
            "graph: max gate2 rounds (%d) reached — forcing finish despite structural issues",
            state["max_gate2_rounds"],
        )
        return "persist_timeline"
    return "assemble_scenes"


# ── Graph builder ──────────────────────────────────────────────────────────────

_EDITOR_INTERRUPT_NODES = [
    "assemble_scenes",    # Gate 1: post-dedup, pre-assembly
    "review_timeline",    # Gate 2: post-stitch, human sets flagged_scene_ids
    "persist_timeline",   # Gate 3: final approval
]


def _build_uncompiled_graph(
    cfg: EditorConfig,
    storage: ProjectStorage,
    project_name: str,
) -> StateGraph:
    """Return the raw (uncompiled) StateGraph shared by build_graph variants."""
    analyst_llm = create_llm(cfg.narrative_analyst)
    selector_llm = create_llm(cfg.editorial_selector)
    stitcher_llm = create_llm(cfg.stitching_agent)
    reviewer_llm = create_llm(cfg.reviewer)

    graph = StateGraph(EditorState)

    graph.add_node("build_embedding_index", make_build_index_node(cfg))
    graph.add_node("retrieve_candidates", make_retrieve_candidates_node(cfg))
    graph.add_node("deduplicate_candidates", deduplicate_candidates_node)
    graph.add_node("fill_gaps", make_fill_gaps_node(cfg))
    graph.add_node("assemble_scenes", make_assemble_scenes_node(analyst_llm, selector_llm, cfg))
    graph.add_node("stitch_scenes", make_stitch_scenes_node(stitcher_llm, cfg))
    graph.add_node("review_timeline", make_review_timeline_node(reviewer_llm))
    graph.add_node("persist_timeline", make_persist_timeline_node(storage, project_name))

    graph.add_edge(START, "build_embedding_index")
    graph.add_edge("build_embedding_index", "retrieve_candidates")
    graph.add_edge("retrieve_candidates", "deduplicate_candidates")
    graph.add_edge("deduplicate_candidates", "fill_gaps")
    graph.add_edge("fill_gaps", "assemble_scenes")

    after_assemble_targets = {"stitch_scenes", "review_timeline", "persist_timeline"}
    graph.add_conditional_edges(
        "assemble_scenes",
        _route_after_assemble(cfg),
        {t: t for t in after_assemble_targets},
    )
    after_stitch_targets = {"review_timeline", "persist_timeline"}
    graph.add_conditional_edges(
        "stitch_scenes",
        _route_after_stitch(cfg),
        {t: t for t in after_stitch_targets},
    )
    graph.add_conditional_edges(
        "review_timeline",
        _route_review,
        {
            "persist_timeline": "persist_timeline",
            "assemble_scenes": "assemble_scenes",
        },
    )
    graph.add_edge("persist_timeline", END)
    return graph


def build_graph(
    cfg: EditorConfig,
    storage: ProjectStorage,
    project_name: str,
):
    """Build and compile the timeline assembly LangGraph graph (CLI / in-process use)."""
    graph = _build_uncompiled_graph(cfg, storage, project_name)

    if cfg.human_in_the_loop:
        from langgraph.checkpoint.memory import MemorySaver  # type: ignore

        checkpointer = MemorySaver()
        return graph.compile(
            checkpointer=checkpointer,
            interrupt_before=_EDITOR_INTERRUPT_NODES,
        )

    return graph.compile()


def build_graph_with_checkpointer(
    cfg: EditorConfig,
    storage: ProjectStorage,
    project_name: str,
    checkpointer,
    human_in_the_loop: bool | None = None,
):
    """Build and compile the editor graph with an external checkpointer.

    Used by the Celery worker layer so that graph state is persisted to Redis
    (via ``RedisSaver``) rather than in-process memory.

    ``human_in_the_loop`` overrides ``cfg.human_in_the_loop`` when provided.
    """
    hitl = human_in_the_loop if human_in_the_loop is not None else cfg.human_in_the_loop
    graph = _build_uncompiled_graph(cfg, storage, project_name)
    interrupt_nodes = _EDITOR_INTERRUPT_NODES if hitl else []
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes,
    )


# ── Helper: detect storyboard version from symlink ────────────────────────────

def _detect_storyboard_version(storage: ProjectStorage, project_name: str) -> int:
    """Read the symlink target of storyboard/latest.json to determine version."""
    symlink = storage.get_project_path(project_name) / "storyboard" / "latest.json"
    try:
        target = symlink.resolve().stem   # e.g. "v2" → stem = "v2"
        if target.startswith("v") and target[1:].isdigit():
            return int(target[1:])
    except Exception:
        pass
    return 0


# ── run() entry point ──────────────────────────────────────────────────────────

def run(
    project_name: str,
    cfg: EditorConfig,
    storage: ProjectStorage,
) -> TimelineOutput:
    """Run the full timeline assembly graph and return the persisted output."""
    from core.schemas.segment import Segment, SegmentBase, SegmentDescription, build_combined_view
    from core.schemas.storyboard import StoryboardOutput

    # ── Load segments (same pattern as storyboard.graph.run) ──────────────────
    segments: list[Segment] = []
    videos_dir = storage.get_project_path(project_name) / "videos"
    for seg_file in sorted(videos_dir.rglob("segments/segments.json")):
        video_hash = seg_file.parts[seg_file.parts.index("videos") + 1]
        rel_base = f"videos/{video_hash}/segments/segments.json"
        rel_desc = f"videos/{video_hash}/segments/descriptions.json"
        try:
            bases: list[SegmentBase] = storage.load_json(project_name, rel_base, schema=SegmentBase)
            descs: list[SegmentDescription] = storage.load_json(project_name, rel_desc, schema=SegmentDescription)
        except FileNotFoundError:
            log.warning(
                "editor: skipping %s — descriptions not found, run 'vc process --describe' first.",
                video_hash,
            )
            continue
        segments.extend(build_combined_view(bases, descs))

    if not segments:
        log.warning("editor: no combined segments found for project '%s'.", project_name)

    # ── Load storyboard ────────────────────────────────────────────────────────
    storyboard_data: StoryboardOutput = storage.load_json(
        project_name, "storyboard/latest.json", schema=StoryboardOutput
    )
    storyboard_version = _detect_storyboard_version(storage, project_name)

    # ── Build and run graph ────────────────────────────────────────────────────
    compiled = build_graph(cfg, storage, project_name)

    initial_state: EditorState = {
        "project_name": project_name,
        "storyboard_version": storyboard_version,
        "scenes": [s.model_dump() for s in storyboard_data.scenes],
        "segments": [s.model_dump(mode="json") for s in segments],
        "scene_candidates": {},
        "deduped_candidates": {},
        "gap_warnings": [],
        "narrative_analyses": {},
        "chains_per_scene": {},
        "chain_selections": {},
        "boundaries": [],
        "stitch_decisions": [],
        "gate2_round": 0,
        "gate2_overrides": {},
        "flagged_scene_ids": [],
        "review": None,
        "approved": False,
        "max_gate2_rounds": cfg.max_gate2_rounds,
        "min_candidates_per_scene": cfg.min_candidates_per_scene,
        "top_k_candidates": cfg.top_k_candidates,
        "top_k_chains": cfg.top_k_chains,
    }

    from core.tracing import flush_langfuse, get_langfuse_handler

    handler = get_langfuse_handler(session_id=project_name, tags=["editor"])
    config: dict = {"configurable": {"thread_id": project_name}} if cfg.human_in_the_loop else {}
    if handler:
        config["callbacks"] = [handler]
    compiled.invoke(initial_state, config=config)
    flush_langfuse()

    return storage.load_json(project_name, "timeline/latest.json", schema=TimelineOutput)
