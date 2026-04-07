"""Tests for storyboard LangGraph node implementations.

Focus:
- _parse_json: markdown-fence stripping and error propagation
- narrator_node: behaviour on bad LLM output
- LLM structured-output: documents absence of fallbacks (regression markers)
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

from storyboard.nodes import _parse_json, make_narrator_node


# ── _parse_json ───────────────────────────────────────────────────────────────

def test_parse_json_plain():
    result = _parse_json('{"key": "value", "n": 42}')
    assert result == {"key": "value", "n": 42}


def test_parse_json_list():
    result = _parse_json('[1, 2, 3]')
    assert result == [1, 2, 3]


def test_parse_json_strips_json_fence():
    text = '```json\n{"scenes": ["a", "b"]}\n```'
    result = _parse_json(text)
    assert result == {"scenes": ["a", "b"]}


def test_parse_json_strips_plain_fence():
    text = '```\n[1, 2]\n```'
    result = _parse_json(text)
    assert result == [1, 2]


def test_parse_json_strips_fence_no_trailing_backticks():
    """Fence without closing ``` — still strips the opening line."""
    text = '```json\n{"k": 1}'
    result = _parse_json(text)
    assert result == {"k": 1}


def test_parse_json_invalid_raises():
    """Malformed JSON raises JSONDecodeError — no silent fallback exists.

    This test documents the current no-fallback behaviour.  It will fail if
    a silent swallow is accidentally introduced, acting as a regression guard.
    """
    with pytest.raises(json.JSONDecodeError):
        _parse_json("not valid json {{{")


# ── narrator_node ─────────────────────────────────────────────────────────────

def test_narrator_node_returns_beats_on_valid_json():
    """narrator_node extracts narration_segments from valid LLM JSON output."""
    llm = MagicMock()
    llm.invoke.return_value.content = json.dumps({
        "narration_segments": [
            {"id": 1, "text": "Open on a wide landscape."},
            {"id": 2, "text": "Cut to close-up."},
        ]
    })

    node = make_narrator_node(llm)
    result = node({"story": "A great story.", "narration_beats": []})

    assert result["narration_beats"] == [
        {"id": 1, "text": "Open on a wide landscape."},
        {"id": 2, "text": "Cut to close-up."},
    ]


def test_narrator_node_falls_back_to_list_when_no_key():
    """If LLM returns a list directly (no wrapper key), it is used as-is."""
    llm = MagicMock()
    raw_list = [{"id": 1, "text": "Beat one."}]
    llm.invoke.return_value.content = json.dumps(raw_list)

    node = make_narrator_node(llm)
    result = node({"story": "Story.", "narration_beats": []})

    assert result["narration_beats"] == raw_list


def test_narrator_node_raises_on_invalid_json():
    """narrator_node propagates JSONDecodeError when LLM returns malformed output.

    This is the current behaviour — no retry or fallback in place.
    """
    llm = MagicMock()
    llm.invoke.return_value.content = "I'm sorry, I cannot produce JSON right now."

    node = make_narrator_node(llm)
    with pytest.raises(json.JSONDecodeError):
        node({"story": "Story.", "narration_beats": []})
