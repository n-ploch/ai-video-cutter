"""Embedding index and candidate retrieval for the timeline assembly agent."""
from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from core.config import EditorConfig
    from core.schemas.editor import CandidateInfo

log = logging.getLogger(__name__)

# ── Module-level index (set once per graph run, avoids putting large arrays in state) ──
_INDEX_MATRIX: np.ndarray | None = None
_INDEX_IDS: list[str] | None = None


@functools.lru_cache(maxsize=4)
def _load_model(model_name: str):
    """Load tokenizer + model once and cache.  Uses AutoTokenizer + AutoModel."""
    from transformers import AutoModel, AutoTokenizer  # type: ignore

    log.info("embedding: loading model '%s'", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    return tokenizer, model


def compute_embeddings(texts: list[str], model_name: str) -> np.ndarray:
    """Embed a list of texts.  Returns L2-normalised matrix shape (N, D)."""
    import torch  # type: ignore

    if not texts:
        return np.zeros((0, 1), dtype=np.float32)

    tokenizer, model = _load_model(model_name)

    with torch.no_grad():
        encoded = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        output = model(**encoded)
        # Mean-pool last hidden state over non-padding tokens
        mask = encoded["attention_mask"].unsqueeze(-1).float()  # (B, T, 1)
        hidden = output.last_hidden_state                        # (B, T, D)
        pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
        embeddings = pooled.cpu().numpy().astype(np.float32)

    # L2 normalise each row
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    return embeddings / norms


def build_segment_index(segments: list[dict], model_name: str) -> None:
    """Compute embeddings for all segments and store in module-level globals."""
    global _INDEX_MATRIX, _INDEX_IDS

    texts: list[str] = []
    seg_ids: list[str] = []

    for seg in segments:
        sid = seg["segment_id"]
        vlm_list = seg.get("vlm", [])
        if vlm_list:
            desc = vlm_list[0].get("description", "") or ""
            highlight_texts = " ".join(
                h.get("description", "") for h in vlm_list[0].get("highlights", [])
            )
            text = (desc + " " + highlight_texts).strip() or sid
        else:
            text = sid
        texts.append(text)
        seg_ids.append(sid)

    log.info("embedding: encoding %d segments with model '%s'", len(texts), model_name)
    _INDEX_MATRIX = compute_embeddings(texts, model_name)
    _INDEX_IDS = seg_ids


def get_index() -> tuple[np.ndarray, list[str]]:
    """Return the module-level embedding index.  Raises if not yet built."""
    if _INDEX_MATRIX is None or _INDEX_IDS is None:
        raise RuntimeError("Embedding index has not been built yet. Call build_segment_index() first.")
    return _INDEX_MATRIX, _INDEX_IDS


def retrieve_candidates(
    scene: dict,
    segments: list[dict],
    index_matrix: np.ndarray,
    index_ids: list[str],
    cfg: EditorConfig,
) -> list[CandidateInfo]:
    """Return the top-k candidate segments for a scene.

    Combines cosine embedding similarity and keyword Jaccard overlap.
    """
    from core.schemas.editor import CandidateInfo

    scene_text = (scene.get("scene_description", "") + " " + " ".join(scene.get("keywords", []))).strip()
    query_vec = compute_embeddings([scene_text], cfg.embedding_model)[0]  # shape (D,)

    # Cosine similarity (index already L2-normalised, query also normalised above)
    emb_scores: np.ndarray = index_matrix @ query_vec  # (N,)

    # Keyword Jaccard
    scene_kws = frozenset(k.lower() for k in scene.get("keywords", []))
    seg_tags_map: dict[str, frozenset] = {}
    for seg in segments:
        vlm_list = seg.get("vlm", [])
        tags = frozenset(
            t.lower() for t in (vlm_list[0].get("segment_tags", []) if vlm_list else [])
        )
        seg_tags_map[seg["segment_id"]] = tags

    seg_by_id = {s["segment_id"]: s for s in segments}

    candidates: list[CandidateInfo] = []
    for idx, sid in enumerate(index_ids):
        seg = seg_by_id.get(sid)
        if seg is None:
            continue
        emb_score = float(emb_scores[idx])
        seg_tags = seg_tags_map.get(sid, frozenset())
        union = scene_kws | seg_tags
        kw_score = len(scene_kws & seg_tags) / len(union) if union else 0.0
        combined = cfg.candidate_alpha * emb_score + (1.0 - cfg.candidate_alpha) * kw_score

        vlm_list = seg.get("vlm", [])
        quality_rating = "good"
        if vlm_list and vlm_list[0].get("quality_score"):
            quality_rating = vlm_list[0]["quality_score"].get("rating", "good") or "good"

        duration = float(seg.get("end", 0.0)) - float(seg.get("start", 0.0))

        candidates.append(CandidateInfo(
            segment_id=sid,
            embedding_score=emb_score,
            keyword_score=kw_score,
            combined_score=combined,
            quality_rating=quality_rating,
            duration=duration,
        ))

    # Sort descending by combined score and take top-k
    candidates.sort(key=lambda c: c.combined_score, reverse=True)
    return candidates[: cfg.top_k_candidates]
