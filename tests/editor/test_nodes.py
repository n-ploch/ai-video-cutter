"""Tests for editor LangGraph node implementations.

Focus: review_timeline fallback when LLM returns None.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from core.schemas.editor import TimelineReview
from editor.nodes import make_review_timeline_node


def _minimal_editor_state(**overrides) -> dict:
    base = {
        "segments": [],
        "scenes": [],
        "boundaries": [],
        "chain_selections": {},
    }
    base.update(overrides)
    return base


def _make_review_llm(return_value) -> MagicMock:
    """Return a mock LLM whose with_structured_output(...).invoke() returns return_value."""
    structured = MagicMock()
    structured.invoke.return_value = return_value

    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


# ── Fallback on None ──────────────────────────────────────────────────────────

def test_review_fallback_on_none_llm_response():
    """When LLM returns None, the node creates a fallback approving TimelineReview."""
    llm = _make_review_llm(return_value=None)
    node = make_review_timeline_node(llm)

    result = node(_minimal_editor_state())

    review = result["review"]
    assert review["decision"] == "approve"
    assert review["has_structural_issues"] is False
    assert review["overall_score"] == pytest.approx(0.5)
    assert review["scene_notes"] == []


def test_review_fallback_logs_warning(caplog):
    """Fallback on None response logs a warning."""
    llm = _make_review_llm(return_value=None)
    node = make_review_timeline_node(llm)

    with caplog.at_level(logging.WARNING, logger="editor.nodes"):
        node(_minimal_editor_state())

    assert any("None" in r.message or "fallback" in r.message.lower() for r in caplog.records)


def test_review_passes_through_valid_response():
    """When LLM returns a valid TimelineReview, it is used unchanged."""
    valid_review = TimelineReview(
        overall_score=0.9,
        scene_notes=[],
        has_structural_issues=False,
        auto_fix_applied=[],
        decision="approve",
    )
    llm = _make_review_llm(return_value=valid_review)
    node = make_review_timeline_node(llm)

    result = node(_minimal_editor_state())

    assert result["review"]["overall_score"] == pytest.approx(0.9)
    assert result["review"]["decision"] == "approve"


def test_review_structural_issues_preserved():
    """has_structural_issues=True is preserved when LLM returns it."""
    flagged_review = TimelineReview(
        overall_score=0.3,
        scene_notes=[],
        has_structural_issues=True,
        auto_fix_applied=[],
        decision="revise",
    )
    llm = _make_review_llm(return_value=flagged_review)
    node = make_review_timeline_node(llm)

    result = node(_minimal_editor_state())

    assert result["review"]["has_structural_issues"] is True
    assert result["review"]["decision"] == "revise"
