"""Tests for storyboard and editor Celery agent tasks.

Focus: fresh-run vs resume branching, gate-override injection, and
checkpoint-resume behaviour with MemorySaver (no Redis required).
All LLM calls are mocked; no real LangGraph nodes execute.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_compiled_mock(paused_at: list[str] | None = None):
    """Return a MagicMock compiled-graph whose get_state() reports paused_at."""
    compiled = MagicMock()
    snapshot = MagicMock()
    snapshot.next = paused_at or []
    compiled.get_state.return_value = snapshot
    return compiled


def _mock_storage_and_settings_for_storyboard():
    """Return (storage, settings) mocks sufficient for task_run_storyboard."""
    storage = MagicMock()
    storage.get_project_path.return_value = MagicMock()
    storage.get_project_path.return_value.rglob.return_value = []  # no segment files

    settings = MagicMock()
    settings.storyboard.human_in_the_loop = False
    settings.storyboard.max_revisions = 3
    return storage, settings


def _mock_storage_and_settings_for_editor():
    """Return (storage, settings) mocks sufficient for task_run_editor."""
    storage = MagicMock()
    storage.get_project_path.return_value = MagicMock()
    storage.get_project_path.return_value.rglob.return_value = []  # no segment files

    from core.schemas.storyboard import StoryboardOutput
    storyboard_data = MagicMock(spec=StoryboardOutput)
    storyboard_data.scenes = []
    storyboard_data.user_brief = ""
    storage.load_json.return_value = storyboard_data

    settings = MagicMock()
    settings.editor.human_in_the_loop = False
    settings.editor.max_gate2_rounds = 2
    settings.editor.min_candidates_per_scene = 3
    settings.editor.top_k_candidates = 15
    settings.editor.top_k_chains = 5
    return storage, settings


# ── Storyboard task ───────────────────────────────────────────────────────────

def test_storyboard_fresh_run_invokes_initial_state():
    """Fresh run (thread_id=None) calls invoke(initial_state, ...), not invoke(None, ...)."""
    from worker.agent_tasks import task_run_storyboard

    compiled = _make_compiled_mock()
    storage, settings = _mock_storage_and_settings_for_storyboard()

    with patch("worker.agent_tasks._get_storage_and_settings", return_value=(storage, settings)):
        with patch("worker.agent_tasks._make_checkpointer") as mock_cm:
            from langgraph.checkpoint.memory import MemorySaver
            mock_cm.return_value.__enter__ = MagicMock(return_value=MemorySaver())
            mock_cm.return_value.__exit__ = MagicMock(return_value=False)

            with patch("storyboard.graph.build_graph_with_checkpointer", return_value=compiled):
                with patch.object(task_run_storyboard, "update_state"):
                    result = task_run_storyboard.run("proj", "a brief", thread_id=None)

    # invoke() should have been called with a dict as the first arg (initial_state)
    assert compiled.invoke.called
    first_call_input = compiled.invoke.call_args_list[0][0][0]
    assert isinstance(first_call_input, dict)
    assert first_call_input["user_brief"] == "a brief"
    assert result["status"] == "complete"


def test_storyboard_resume_invokes_none():
    """Resume (thread_id provided) calls invoke(None, ...) to reload checkpoint."""
    from worker.agent_tasks import task_run_storyboard

    compiled = _make_compiled_mock(paused_at=["some_node"])
    storage, settings = _mock_storage_and_settings_for_storyboard()

    with patch("worker.agent_tasks._get_storage_and_settings", return_value=(storage, settings)):
        with patch("worker.agent_tasks._make_checkpointer") as mock_cm:
            from langgraph.checkpoint.memory import MemorySaver
            mock_cm.return_value.__enter__ = MagicMock(return_value=MemorySaver())
            mock_cm.return_value.__exit__ = MagicMock(return_value=False)

            with patch("storyboard.graph.build_graph_with_checkpointer", return_value=compiled):
                with patch.object(task_run_storyboard, "update_state"):
                    result = task_run_storyboard.run("proj", "", thread_id="existing-thread")

    first_call_input = compiled.invoke.call_args_list[0][0][0]
    assert first_call_input is None  # must pass None on resume


def test_storyboard_paused_returns_awaiting_human():
    """When graph pauses at an interrupt, status is 'awaiting_human'."""
    from worker.agent_tasks import task_run_storyboard

    compiled = _make_compiled_mock(paused_at=["director"])
    storage, settings = _mock_storage_and_settings_for_storyboard()

    with patch("worker.agent_tasks._get_storage_and_settings", return_value=(storage, settings)):
        with patch("worker.agent_tasks._make_checkpointer") as mock_cm:
            from langgraph.checkpoint.memory import MemorySaver
            mock_cm.return_value.__enter__ = MagicMock(return_value=MemorySaver())
            mock_cm.return_value.__exit__ = MagicMock(return_value=False)

            with patch("storyboard.graph.build_graph_with_checkpointer", return_value=compiled):
                with patch.object(task_run_storyboard, "update_state"):
                    result = task_run_storyboard.run("proj", "brief")

    assert result["status"] == "awaiting_human"
    assert result["paused_at"] == ["director"]
    assert result["thread_id"] == "proj"  # defaults to project_name


# ── Editor task ───────────────────────────────────────────────────────────────

def test_editor_fresh_run_invokes_initial_state():
    """Fresh run (thread_id=None) calls invoke(initial_state, ...)."""
    from worker.agent_tasks import task_run_editor

    compiled = _make_compiled_mock()
    storage, settings = _mock_storage_and_settings_for_editor()

    with patch("worker.agent_tasks._get_storage_and_settings", return_value=(storage, settings)):
        with patch("worker.agent_tasks._make_checkpointer") as mock_cm:
            from langgraph.checkpoint.memory import MemorySaver
            mock_cm.return_value.__enter__ = MagicMock(return_value=MemorySaver())
            mock_cm.return_value.__exit__ = MagicMock(return_value=False)

            with patch("editor.graph.build_graph_with_checkpointer", return_value=compiled):
                with patch("editor.graph._detect_storyboard_version", return_value="v1"):
                    with patch.object(task_run_editor, "update_state"):
                        result = task_run_editor.run("proj", thread_id=None)

    first_call_input = compiled.invoke.call_args_list[0][0][0]
    assert isinstance(first_call_input, dict)
    assert result["status"] == "complete"


def test_editor_resume_applies_gate_overrides_before_invoke():
    """On resume, gate_overrides are injected via update_state() before invoke(None)."""
    from worker.agent_tasks import task_run_editor

    compiled = _make_compiled_mock(paused_at=["gate_node"])
    storage, settings = _mock_storage_and_settings_for_editor()

    overrides = {"gate2_overrides": {"scene_1": {"chain_index": 2}}, "flagged_scene_ids": [1]}

    with patch("worker.agent_tasks._get_storage_and_settings", return_value=(storage, settings)):
        with patch("worker.agent_tasks._make_checkpointer") as mock_cm:
            from langgraph.checkpoint.memory import MemorySaver
            mock_cm.return_value.__enter__ = MagicMock(return_value=MemorySaver())
            mock_cm.return_value.__exit__ = MagicMock(return_value=False)

            with patch("editor.graph.build_graph_with_checkpointer", return_value=compiled):
                with patch("editor.graph._detect_storyboard_version", return_value="v1"):
                    with patch.object(task_run_editor, "update_state"):
                        task_run_editor.run("proj", thread_id="existing-thread", gate_overrides=overrides)

    # update_state should be called with the overrides before invoke
    compiled.update_state.assert_called_once()
    update_call_kwargs = compiled.update_state.call_args[0][1]  # second positional arg
    assert update_call_kwargs == overrides

    # invoke should follow with None
    first_call_input = compiled.invoke.call_args_list[0][0][0]
    assert first_call_input is None


def test_editor_resume_no_overrides_skips_update_state():
    """On resume with no gate_overrides, update_state is NOT called."""
    from worker.agent_tasks import task_run_editor

    compiled = _make_compiled_mock()
    storage, settings = _mock_storage_and_settings_for_editor()

    with patch("worker.agent_tasks._get_storage_and_settings", return_value=(storage, settings)):
        with patch("worker.agent_tasks._make_checkpointer") as mock_cm:
            from langgraph.checkpoint.memory import MemorySaver
            mock_cm.return_value.__enter__ = MagicMock(return_value=MemorySaver())
            mock_cm.return_value.__exit__ = MagicMock(return_value=False)

            with patch("editor.graph.build_graph_with_checkpointer", return_value=compiled):
                with patch("editor.graph._detect_storyboard_version", return_value="v1"):
                    with patch.object(task_run_editor, "update_state"):
                        task_run_editor.run("proj", thread_id="thread", gate_overrides=None)

    compiled.update_state.assert_not_called()


# ── Checkpoint resume (MemorySaver integration) ───────────────────────────────

def test_langgraph_checkpoint_resume_continues_from_interrupt():
    """A graph paused at interrupt_before resumes from the paused node on second invoke."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import StateGraph, START, END

    # Minimal graph: node_a (interrupt here) → node_b
    class S(dict):
        pass

    visited = []

    def node_a(state):
        visited.append("a")
        return {}

    def node_b(state):
        visited.append("b")
        return {}

    builder = StateGraph(dict)
    builder.add_node("node_a", node_a)
    builder.add_node("node_b", node_b)
    builder.add_edge(START, "node_a")
    builder.add_edge("node_a", "node_b")
    builder.add_edge("node_b", END)

    checkpointer = MemorySaver()
    compiled = builder.compile(checkpointer=checkpointer, interrupt_before=["node_b"])
    cfg = {"configurable": {"thread_id": "t1"}}

    # First run: pauses before node_b
    compiled.invoke({}, config=cfg)
    assert visited == ["a"]
    assert compiled.get_state(cfg).next == ("node_b",)

    # Resume: continues from node_b
    compiled.invoke(None, config=cfg)
    assert "b" in visited


def test_langgraph_no_checkpoint_invoke_none_raises():
    """invoke(None, ...) on a thread with no prior checkpoint raises EmptyInputError.

    This documents the current behaviour: the task_run_storyboard / task_run_editor
    resume path will raise if the checkpoint was lost (e.g. Redis flush).
    Callers must handle this and restart with a fresh initial_state.
    """
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.errors import EmptyInputError
    from langgraph.graph import END, START, StateGraph

    def node_a(state):
        return {}

    builder = StateGraph(dict)
    builder.add_node("node_a", node_a)
    builder.add_edge(START, "node_a")
    builder.add_edge("node_a", END)

    checkpointer = MemorySaver()
    compiled = builder.compile(checkpointer=checkpointer)
    cfg = {"configurable": {"thread_id": "nonexistent-thread"}}

    with pytest.raises(EmptyInputError):
        compiled.invoke(None, config=cfg)
