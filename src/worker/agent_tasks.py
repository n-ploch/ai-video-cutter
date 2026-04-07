"""LangGraph agent Celery tasks (queue: agents).

Both storyboard and editor tasks follow the same pattern:
  1. Use a Redis checkpointer (RedisSaver) so graph state survives worker exit.
  2. Run the compiled graph via invoke().
  3. After invoke() returns, check get_state().next:
     - Empty → graph ran to completion → return {"status": "complete"}.
     - Non-empty → graph hit an interrupt_before gate → return
       {"status": "awaiting_human", "thread_id": ..., "paused_at": [...]}.
  4. The API resume endpoint injects human feedback via update_state() and
     dispatches a new task with the same thread_id to continue.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from worker.celery_app import app

log = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _get_storage_and_settings(project_name: str):
    from core.config import AppSettings
    from core.storage_factory import make_storage

    app_settings = AppSettings.from_env()
    storage = make_storage(
        storage_backend=app_settings.storage_backend,
        storage_root=app_settings.storage_root,
        default_config=app_settings.default_config_path,
    )
    settings = app_settings.load_settings(project_name)
    return storage, settings


@contextmanager
def _make_checkpointer():
    """Context manager yielding a Redis-backed LangGraph checkpointer."""
    try:
        from langgraph.checkpoint.redis import RedisSaver  # type: ignore
        with RedisSaver.from_conn_string(_REDIS_URL) as checkpointer:
            yield checkpointer
    except ImportError:
        # Fallback for environments where langgraph-checkpoint-redis is not
        # installed (e.g. running tests with CELERY_TASK_ALWAYS_EAGER).
        from langgraph.checkpoint.memory import MemorySaver
        log.warning("langgraph-checkpoint-redis not installed — using MemorySaver (HITL won't persist across tasks)")
        yield MemorySaver()


@app.task(
    bind=True,
    name="agents.storyboard",
    queue="agents",
    acks_late=True,
    max_retries=1,
    time_limit=1800,
    soft_time_limit=1740,
)
def task_run_storyboard(
    self,
    project_name: str,
    user_brief: str,
    thread_id: str | None = None,
    human_in_the_loop: bool | None = None,
) -> dict:
    """Run (or resume) the storyboard LangGraph agent.

    Args:
        project_name: Project identifier.
        user_brief:   Creative brief (used on fresh runs; ignored on resume).
        thread_id:    If provided, resumes from the stored LangGraph checkpoint
                      instead of starting a fresh run.

    Returns a dict with ``status`` set to ``"complete"`` or
    ``"awaiting_human"``.  On ``"awaiting_human"`` the caller should call
    the resume API endpoint once the human has reviewed.
    """
    from storyboard.graph import build_graph_with_checkpointer

    self.update_state(
        state="STARTED",
        meta={"current_step": "storyboard", "project": project_name},
    )

    storage, settings = _get_storage_and_settings(project_name)
    cfg = settings.storyboard
    effective_thread_id = thread_id or project_name
    langgraph_config = {"configurable": {"thread_id": effective_thread_id}}

    with _make_checkpointer() as checkpointer:
        compiled = build_graph_with_checkpointer(cfg, storage, project_name, checkpointer, human_in_the_loop)

        if thread_id is None:
            # ── Fresh run: build initial state from segments + brief ──────────────
            from core.schemas.segment import SegmentBase, SegmentDescription, build_combined_view
            from storyboard.graph import _format_video_descriptions

            segments = []
            videos_dir = storage.get_project_path(project_name) / "videos"
            for seg_file in sorted(videos_dir.rglob("segments/segments.json")):
                video_hash = seg_file.parts[seg_file.parts.index("videos") + 1]
                try:
                    bases = storage.load_json(project_name, f"videos/{video_hash}/segments/segments.json", schema=SegmentBase)
                    descs = storage.load_json(project_name, f"videos/{video_hash}/segments/descriptions.json", schema=SegmentDescription)
                except FileNotFoundError:
                    log.warning("task_run_storyboard: skipping %s — descriptions not found", video_hash)
                    continue
                segments.extend(build_combined_view(bases, descs))

            video_descriptions = _format_video_descriptions(segments)

            initial_state = {
                "project_name": project_name,
                "user_brief": user_brief,
                "video_descriptions": video_descriptions,
                "story": "",
                "narration_beats": [],
                "scenes": [],
                "story_judge_narrative_quality": 0.0,
                "story_judge_brief_adherence": 0.0,
                "story_judge_context_adherence": 0.0,
                "story_judge_total_score": 0.0,
                "story_judge_feedback": "",
                "story_judge_decision": "",
                "story_revision_count": 0,
                "judge_score": 0.0,
                "judge_feedback": "",
                "judge_decision": "",
                "revision_count": 0,
                "max_revisions": cfg.max_revisions,
            }
            compiled.invoke(initial_state, config=langgraph_config)
        else:
            # ── Resume: LangGraph reloads state from Redis checkpoint ─────────────
            compiled.invoke(None, config=langgraph_config)

        # Check whether the graph paused at an interrupt_before gate.
        state_snapshot = compiled.get_state(langgraph_config)
        if state_snapshot.next:
            paused_at = list(state_snapshot.next)
            log.info(
                "task_run_storyboard: project=%s paused at %s (thread=%s)",
                project_name, paused_at, effective_thread_id,
            )
            return {
                "status": "awaiting_human",
                "thread_id": effective_thread_id,
                "project_name": project_name,
                "paused_at": paused_at,
            }

    log.info("task_run_storyboard: project=%s complete", project_name)
    return {
        "status": "complete",
        "thread_id": effective_thread_id,
        "project_name": project_name,
        "paused_at": [],
    }


@app.task(
    bind=True,
    name="agents.editor",
    queue="agents",
    acks_late=True,
    max_retries=1,
    time_limit=2700,
    soft_time_limit=2640,
)
def task_run_editor(
    self,
    project_name: str,
    thread_id: str | None = None,
    gate_overrides: dict | None = None,
    human_in_the_loop: bool | None = None,
) -> dict:
    """Run (or resume) the editor LangGraph agent.

    Args:
        project_name:  Project identifier.
        thread_id:     Resume from checkpoint if provided; fresh run otherwise.
        gate_overrides: Human-supplied overrides injected into LangGraph state
                        before resuming (e.g. ``{"gate2_overrides": {...}}``)
                        Ignored on fresh runs.

    Returns a dict with ``status`` set to ``"complete"`` or
    ``"awaiting_human"``.
    """
    from editor.graph import build_graph_with_checkpointer

    self.update_state(
        state="STARTED",
        meta={"current_step": "editor", "project": project_name},
    )

    storage, settings = _get_storage_and_settings(project_name)
    cfg = settings.editor
    effective_thread_id = thread_id or project_name
    langgraph_config = {"configurable": {"thread_id": effective_thread_id}}

    with _make_checkpointer() as checkpointer:
        compiled = build_graph_with_checkpointer(cfg, storage, project_name, checkpointer, human_in_the_loop)

        if thread_id is None:
            # ── Fresh run: build initial state ────────────────────────────────────
            from core.schemas.segment import SegmentBase, SegmentDescription, build_combined_view
            from core.schemas.storyboard import StoryboardOutput
            from editor.graph import _detect_storyboard_version

            segments = []
            videos_dir = storage.get_project_path(project_name) / "videos"
            for seg_file in sorted(videos_dir.rglob("segments/segments.json")):
                video_hash = seg_file.parts[seg_file.parts.index("videos") + 1]
                try:
                    bases = storage.load_json(project_name, f"videos/{video_hash}/segments/segments.json", schema=SegmentBase)
                    descs = storage.load_json(project_name, f"videos/{video_hash}/segments/descriptions.json", schema=SegmentDescription)
                except FileNotFoundError:
                    log.warning("task_run_editor: skipping %s — descriptions not found", video_hash)
                    continue
                segments.extend(build_combined_view(bases, descs))

            storyboard_data: StoryboardOutput = storage.load_json(
                project_name, "storyboard/latest.json", schema=StoryboardOutput
            )
            storyboard_version = _detect_storyboard_version(storage, project_name)

            initial_state = {
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
            compiled.invoke(initial_state, config=langgraph_config)
        else:
            # ── Resume: optionally inject human overrides into checkpoint ─────────
            if gate_overrides:
                compiled.update_state(langgraph_config, gate_overrides)
            compiled.invoke(None, config=langgraph_config)

        state_snapshot = compiled.get_state(langgraph_config)
        if state_snapshot.next:
            paused_at = list(state_snapshot.next)
            log.info(
                "task_run_editor: project=%s paused at %s (thread=%s)",
                project_name, paused_at, effective_thread_id,
            )
            return {
                "status": "awaiting_human",
                "thread_id": effective_thread_id,
                "project_name": project_name,
                "paused_at": paused_at,
            }

    log.info("task_run_editor: project=%s complete", project_name)
    return {
        "status": "complete",
        "thread_id": effective_thread_id,
        "project_name": project_name,
        "paused_at": [],
    }
