"""Inter-scene boundary cost computation and swap candidate search."""
from __future__ import annotations

from typing import TYPE_CHECKING

from editor.tools.pathfinding import compute_kinematic_cost

if TYPE_CHECKING:
    from core.config import EditorConfig


def compute_boundary_cost(seg_a: dict, seg_b: dict, cfg: EditorConfig) -> float:
    """Kinematic cost at an inter-scene boundary.

    Uses only C_kin (no quality multiplier — boundary quality is about motion
    continuity, not content rating of the incoming segment).
    """
    return compute_kinematic_cost(seg_a, seg_b, cfg.w1, cfg.w2)


def find_swap_candidates(
    current_entry_seg_id: str,
    candidates: list[dict],  # CandidateInfo dicts for the incoming scene
    segments_by_id: dict[str, dict],
    predecessor_seg: dict,
    cfg: EditorConfig,
    top_n: int = 3,
) -> list[str]:
    """Return up to top_n alternative entry segment IDs that reduce boundary cost.

    Excludes the current entry segment and returns candidates sorted by
    ascending boundary cost (cheapest transition first).
    """
    current_cost = compute_boundary_cost(
        predecessor_seg,
        segments_by_id.get(current_entry_seg_id, {}),
        cfg,
    )

    scored: list[tuple[float, str]] = []
    for cand in candidates:
        sid = cand["segment_id"]
        if sid == current_entry_seg_id:
            continue
        seg = segments_by_id.get(sid)
        if seg is None:
            continue
        cost = compute_boundary_cost(predecessor_seg, seg, cfg)
        if cost < current_cost:
            scored.append((cost, sid))

    scored.sort(key=lambda x: x[0])
    return [sid for _, sid in scored[:top_n]]
