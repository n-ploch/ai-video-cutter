"""Unit tests for editor/tools/embedding.py.

Model loading is mocked — no transformer weights downloaded during testing.
Module-level globals (_INDEX_MATRIX, _INDEX_IDS) are reset per test.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import editor.tools.embedding as emb_module
from editor.tools.embedding import (
    build_segment_index,
    compute_embeddings,
    get_index,
    retrieve_candidates,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_embedding_globals():
    """Ensure module-level index globals are cleared before and after each test."""
    emb_module._INDEX_MATRIX = None
    emb_module._INDEX_IDS = None
    yield
    emb_module._INDEX_MATRIX = None
    emb_module._INDEX_IDS = None


def _mock_model(dim: int = 8):
    """Return (tokenizer_mock, model_mock) that produce deterministic embeddings."""
    import torch

    tokenizer = MagicMock()
    tokenizer.return_value = {
        "input_ids": torch.zeros(1, 4, dtype=torch.long),
        "attention_mask": torch.ones(1, 4, dtype=torch.long),
    }
    # Make tokenizer callable like the real one: tokenizer(texts, ...) → dict
    def _tok_call(texts, **kwargs):
        n = len(texts) if isinstance(texts, list) else 1
        return {
            "input_ids": torch.zeros(n, 4, dtype=torch.long),
            "attention_mask": torch.ones(n, 4, dtype=torch.long),
        }
    tokenizer.side_effect = _tok_call

    class _FakeOutput:
        def __init__(self, n, d):
            self.last_hidden_state = torch.ones(n, 4, d)

    model = MagicMock()
    model.side_effect = lambda **kwargs: _FakeOutput(
        kwargs["input_ids"].shape[0], dim
    )

    return tokenizer, model


def _mock_cfg(top_k: int = 3, alpha: float = 0.7, model: str = "fake-model"):
    from core.config import EditorConfig
    return EditorConfig(
        top_k_candidates=top_k,
        candidate_alpha=alpha,
        embedding_model=model,
    )


def _make_segment(seg_id: str, description: str = "", tags: list[str] | None = None) -> dict:
    return {
        "segment_id": seg_id,
        "start": 0.0,
        "end": 5.0,
        "vlm": [{"description": description, "highlights": [], "segment_tags": tags or []}],
    }


# ── get_index() ───────────────────────────────────────────────────────────────

def test_get_index_raises_before_build():
    with pytest.raises(RuntimeError, match="build_segment_index"):
        get_index()


# ── compute_embeddings() ──────────────────────────────────────────────────────

def test_compute_embeddings_empty_list():
    result = compute_embeddings([], "any-model")
    assert result.shape[0] == 0


def test_compute_embeddings_returns_l2_normalized(tmp_path):
    tok, model = _mock_model(dim=8)
    with patch("editor.tools.embedding._load_model", return_value=(tok, model)):
        result = compute_embeddings(["hello world", "second text"], "fake-model")

    assert result.shape == (2, 8)
    # Each row should be unit-norm (L2 normalised)
    norms = np.linalg.norm(result, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


# ── build_segment_index() ─────────────────────────────────────────────────────

def test_build_segment_index_sets_globals():
    segments = [_make_segment("s1", "desc"), _make_segment("s2", "desc")]
    tok, model = _mock_model()
    with patch("editor.tools.embedding._load_model", return_value=(tok, model)):
        build_segment_index(segments, "fake-model")

    mat, ids = get_index()
    assert mat.shape[0] == 2
    assert ids == ["s1", "s2"]


def test_build_segment_index_no_vlm_falls_back_to_segment_id():
    """Segment missing 'vlm' key uses segment_id as text — no crash."""
    segments = [{"segment_id": "bare-seg", "start": 0.0, "end": 3.0}]
    tok, model = _mock_model()
    with patch("editor.tools.embedding._load_model", return_value=(tok, model)):
        build_segment_index(segments, "fake-model")

    _, ids = get_index()
    assert ids == ["bare-seg"]


def test_build_segment_index_empty_vlm_list_falls_back():
    """Segment with vlm=[] (empty list) falls back to segment_id."""
    segments = [{"segment_id": "empty-vlm", "start": 0.0, "end": 2.0, "vlm": []}]
    tok, model = _mock_model()
    with patch("editor.tools.embedding._load_model", return_value=(tok, model)):
        build_segment_index(segments, "fake-model")

    _, ids = get_index()
    assert ids == ["empty-vlm"]


# ── retrieve_candidates() ─────────────────────────────────────────────────────

def _setup_index(seg_ids: list[str], dim: int = 8):
    """Directly populate module globals with deterministic embeddings."""
    rng = np.random.default_rng(42)
    mat = rng.random((len(seg_ids), dim)).astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    emb_module._INDEX_MATRIX = mat / np.where(norms < 1e-9, 1.0, norms)
    emb_module._INDEX_IDS = seg_ids


def test_retrieve_candidates_returns_top_k():
    seg_ids = ["s1", "s2", "s3", "s4", "s5"]
    segments = [_make_segment(sid) for sid in seg_ids]
    _setup_index(seg_ids)

    cfg = _mock_cfg(top_k=3)
    scene = {"narration_segment": "action", "scene_description": "fast cut", "keywords": ["action"]}

    tok, model = _mock_model()
    with patch("editor.tools.embedding._load_model", return_value=(tok, model)):
        results = retrieve_candidates(scene, segments, emb_module._INDEX_MATRIX, seg_ids, cfg)

    assert len(results) <= 3


def test_retrieve_candidates_missing_segment_skipped():
    """If index_ids contains an ID not in segments list, it is silently skipped."""
    _setup_index(["s1", "ghost-id"])  # ghost-id not in segments
    segments = [_make_segment("s1")]

    cfg = _mock_cfg(top_k=5)
    scene = {"narration_segment": "text", "scene_description": "desc", "keywords": []}

    tok, model = _mock_model()
    with patch("editor.tools.embedding._load_model", return_value=(tok, model)):
        results = retrieve_candidates(scene, segments, emb_module._INDEX_MATRIX, ["s1", "ghost-id"], cfg)

    returned_ids = [r.segment_id for r in results]
    assert "ghost-id" not in returned_ids
    assert "s1" in returned_ids


def test_retrieve_candidates_empty_scene_keywords_no_division_error():
    """Empty keywords list produces kw_score=0.0 without division by zero."""
    seg_ids = ["s1"]
    segments = [_make_segment("s1", tags=["outdoor"])]
    _setup_index(seg_ids)

    cfg = _mock_cfg(top_k=5)
    scene = {"narration_segment": "text", "scene_description": "desc", "keywords": []}

    tok, model = _mock_model()
    with patch("editor.tools.embedding._load_model", return_value=(tok, model)):
        results = retrieve_candidates(scene, segments, emb_module._INDEX_MATRIX, seg_ids, cfg)

    assert results[0].keyword_score == pytest.approx(0.0)
