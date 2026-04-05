"""Cost functions, DAG construction, and k-shortest chain pathfinding."""
from __future__ import annotations

import itertools
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from core.config import EditorConfig
    from core.schemas.editor import BucketAssignment, Chain

log = logging.getLogger(__name__)

# ── Quality multipliers ────────────────────────────────────────────────────────

QUALITY_MULTIPLIER: dict[str, float] = {
    "excellent": 0.5,
    "good": 1.0,
    "medium": 2.0,
    "fair": 2.0,    # alias used in system spec
    "bad": 5.0,
    "poor": 5.0,    # alias used in system spec
}


def _quality_multiplier(rating: str) -> float:
    return QUALITY_MULTIPLIER.get((rating or "good").lower(), 1.0)


# ── Velocity helpers ───────────────────────────────────────────────────────────

def entry_velocity(seg: dict) -> np.ndarray:
    """[pan_entry_vel, tilt_entry_vel, zoom_entry_vel] from first CameraMovement."""
    movements = seg.get("camera_movements", [])
    if not movements:
        return np.zeros(3, dtype=np.float64)
    m = movements[0]
    return np.array([
        m.get("pan_entry_vel", 0.0),
        m.get("tilt_entry_vel", 0.0),
        m.get("zoom_entry_vel", 0.0),
    ], dtype=np.float64)


def exit_velocity(seg: dict) -> np.ndarray:
    """[pan_exit_vel, tilt_exit_vel, zoom_exit_vel] from last CameraMovement."""
    movements = seg.get("camera_movements", [])
    if not movements:
        return np.zeros(3, dtype=np.float64)
    m = movements[-1]
    return np.array([
        m.get("pan_exit_vel", 0.0),
        m.get("tilt_exit_vel", 0.0),
        m.get("zoom_exit_vel", 0.0),
    ], dtype=np.float64)


# ── Cost functions ─────────────────────────────────────────────────────────────

def compute_kinematic_cost(seg_i: dict, seg_j: dict, w1: float, w2: float) -> float:
    """Kinematic mismatch cost C_kin between exit of seg_i and entry of seg_j."""
    eps = 1e-8
    v_out = exit_velocity(seg_i)
    v_in = entry_velocity(seg_j)
    norm_out = float(np.linalg.norm(v_out))
    norm_in = float(np.linalg.norm(v_in))

    # Both static — no kinematic penalty
    if norm_out < eps and norm_in < eps:
        return 0.0

    cos_sim = float(np.dot(v_out, v_in)) / (norm_out * norm_in + eps)
    direction_cost = 1.0 - cos_sim

    speed_diff = abs(norm_out - norm_in) / (max(norm_out, norm_in) + eps)

    return w1 * direction_cost + w2 * speed_diff


def compute_segment_penalty(seg: dict, w3: float, w4: float) -> float:
    """Intrinsic segment penalty P_seg from internal motion quality of seg."""
    movements = seg.get("camera_movements", [])
    if not movements:
        return 0.0
    m = movements[0]
    instability = float(np.mean([
        m.get("pan_std_deriv", 0.0),
        m.get("tilt_std_deriv", 0.0),
        m.get("zoom_std_deriv", 0.0),
    ]))
    monotonicity = float(np.mean([
        abs(m.get("pan_monotonicity", 0.0)),
        abs(m.get("tilt_monotonicity", 0.0)),
        abs(m.get("zoom_monotonicity", 0.0)),
    ]))
    return w3 * instability - w4 * monotonicity


def compute_total_cost(
    seg_i: dict,
    seg_j: dict,
    nar_score_j: float,
    cfg: EditorConfig,
) -> float:
    """Full edge cost C_total(i→j) = Q_j * (C_kin + P_seg(j) + C_nar(j))."""
    vlm_list = seg_j.get("vlm", [])
    rating = "good"
    if vlm_list and vlm_list[0].get("quality_score"):
        rating = vlm_list[0]["quality_score"].get("rating", "good") or "good"

    Q_j = _quality_multiplier(rating)
    C_kin = compute_kinematic_cost(seg_i, seg_j, cfg.w1, cfg.w2)
    P_seg = compute_segment_penalty(seg_j, cfg.w3, cfg.w4)
    C_nar = cfg.w5 * (1.0 - float(nar_score_j))

    return Q_j * (C_kin + P_seg + C_nar)


# ── DAG construction ───────────────────────────────────────────────────────────

_SOURCE = "__source__"
_SINK = "__sink__"


def build_dag(
    scene_id: int,
    assignments: list[dict],  # list of BucketAssignment dicts
    segments_by_id: dict[str, dict],
    cfg: EditorConfig,
) -> object:  # nx.DiGraph
    """Build a directed acyclic graph for pathfinding through the bucket sequence.

    Nodes: (segment_id, bucket_idx) pairs, plus virtual __source__ and __sink__.
    Edges connect bucket n → n+1 only (monotonic traversal).
    """
    import networkx as nx  # type: ignore

    G = nx.DiGraph()
    G.add_node(_SOURCE)
    G.add_node(_SINK)

    # Group assignments by bucket
    by_bucket: dict[int, list[dict]] = {}
    for a in assignments:
        by_bucket.setdefault(a["bucket_idx"], []).append(a)

    if not by_bucket:
        return G

    bucket_idxs = sorted(by_bucket.keys())
    first_bucket = bucket_idxs[0]
    last_bucket = bucket_idxs[-1]

    # Add all segment-bucket nodes
    for b_idx, bucket_assignments in by_bucket.items():
        for a in bucket_assignments:
            node = (a["segment_id"], b_idx)
            G.add_node(node, segment_id=a["segment_id"], bucket_idx=b_idx,
                       narrative_score=a["narrative_score"])

    # Source → first bucket (weight 0 — no incoming edge cost)
    for a in by_bucket.get(first_bucket, []):
        G.add_edge(_SOURCE, (a["segment_id"], first_bucket), weight=0.0)

    # Last bucket → sink (weight 0)
    for a in by_bucket.get(last_bucket, []):
        G.add_edge((a["segment_id"], last_bucket), _SINK, weight=0.0)

    # Edges between adjacent buckets
    for i, b_cur in enumerate(bucket_idxs[:-1]):
        b_next = bucket_idxs[i + 1]
        for a_i in by_bucket.get(b_cur, []):
            for a_j in by_bucket.get(b_next, []):
                # Allow same physical segment in different buckets
                seg_i = segments_by_id.get(a_i["segment_id"])
                seg_j = segments_by_id.get(a_j["segment_id"])
                if seg_i is None or seg_j is None:
                    continue
                cost = compute_total_cost(seg_i, seg_j, a_j["narrative_score"], cfg)
                G.add_edge(
                    (a_i["segment_id"], b_cur),
                    (a_j["segment_id"], b_next),
                    weight=cost,
                )

    return G


# ── Pathfinding ────────────────────────────────────────────────────────────────

def _path_to_chain(
    path: list,
    scene_id: int,
    segments_by_id: dict[str, dict],
    nar_scores: dict[str, float],
    target_ideal: float,
    cfg: EditorConfig,
) -> Chain | None:
    """Convert a source-to-sink path into a Chain object."""
    from core.schemas.editor import Chain, ChainLink

    inner = [n for n in path if n not in (_SOURCE, _SINK)]
    if not inner:
        return None

    links: list[ChainLink] = []
    total_cost = 0.0
    total_duration = 0.0

    for pos, node in enumerate(inner):
        seg_id, bucket_idx = node
        seg = segments_by_id.get(seg_id)
        if seg is None:
            return None
        duration = float(seg.get("end", 0.0)) - float(seg.get("start", 0.0))
        total_duration += duration

        edge_cost = 0.0
        if pos > 0:
            prev_seg_id = inner[pos - 1][0]
            prev_seg = segments_by_id.get(prev_seg_id)
            if prev_seg is not None:
                nar_score = nar_scores.get(seg_id, 0.5)
                edge_cost = compute_total_cost(prev_seg, seg, nar_score, cfg)
                total_cost += edge_cost

        links.append(ChainLink(
            segment_id=seg_id,
            bucket_idx=bucket_idx,
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            video_file=seg.get("video_file", ""),
            edge_cost=edge_cost,
        ))

    return Chain(
        scene_id=scene_id,
        links=links,
        total_cost=total_cost,
        total_duration=total_duration,
        duration_delta=abs(total_duration - target_ideal),
    )


def _greedy_chain_fallback(
    assignments: list[dict],
    segments_by_id: dict[str, dict],
    scene_id: int,
    target_ideal: float,
    cfg: EditorConfig,
) -> list[Chain]:
    """Return a single best-effort chain: highest narrative-score segment per bucket."""
    from core.schemas.editor import Chain, ChainLink

    by_bucket: dict[int, list[dict]] = {}
    for a in assignments:
        by_bucket.setdefault(a["bucket_idx"], []).append(a)

    links: list[ChainLink] = []
    total_cost = 0.0
    total_duration = 0.0
    prev_seg: dict | None = None

    for b_idx in sorted(by_bucket.keys()):
        best = max(by_bucket[b_idx], key=lambda a: a["narrative_score"])
        seg = segments_by_id.get(best["segment_id"])
        if seg is None:
            continue
        duration = float(seg.get("end", 0.0)) - float(seg.get("start", 0.0))
        total_duration += duration
        edge_cost = 0.0
        if prev_seg is not None:
            edge_cost = compute_total_cost(prev_seg, seg, best["narrative_score"], cfg)
            total_cost += edge_cost
        links.append(ChainLink(
            segment_id=best["segment_id"],
            bucket_idx=b_idx,
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            video_file=seg.get("video_file", ""),
            edge_cost=edge_cost,
        ))
        prev_seg = seg

    if not links:
        return []
    return [Chain(
        scene_id=scene_id,
        links=links,
        total_cost=total_cost,
        total_duration=total_duration,
        duration_delta=abs(total_duration - target_ideal),
    )]


def find_chains(
    dag,
    segments_by_id: dict[str, dict],
    assignments: list[dict],
    scene_id: int,
    target_min: float,
    target_max: float,
    target_ideal: float,
    top_k: int,
    cfg: EditorConfig,
) -> list[Chain]:
    """Find the top-k lowest-cost chains within the target duration range.

    Uses Yen's k-shortest paths (networkx.simple_paths.shortest_simple_paths).
    Falls back to a greedy chain when no path satisfies the duration constraint.
    """
    import networkx as nx  # type: ignore

    nar_scores: dict[str, float] = {a["segment_id"]: a["narrative_score"] for a in assignments}

    if not nx.has_path(dag, _SOURCE, _SINK):
        log.warning("find_chains: scene %d DAG is disconnected — using greedy fallback", scene_id)
        return _greedy_chain_fallback(assignments, segments_by_id, scene_id, target_ideal, cfg)

    # Try with progressively widened duration tolerance
    lo, hi = target_min, target_max
    for attempt in range(4):  # original + 3 widening passes
        accepted: list[Chain] = []
        path_gen = nx.shortest_simple_paths(dag, _SOURCE, _SINK, weight="weight")
        for path in itertools.islice(path_gen, top_k * 10):
            chain = _path_to_chain(path, scene_id, segments_by_id, nar_scores, target_ideal, cfg)
            if chain is None:
                continue
            if lo <= chain.total_duration <= hi:
                accepted.append(chain)
                if len(accepted) >= top_k:
                    break

        if accepted:
            accepted.sort(key=lambda c: c.duration_delta)
            return accepted[:top_k]

        if attempt < 3:
            factor = 1.2 ** (attempt + 1)
            mid = (lo + hi) / 2.0
            lo = mid - (mid - target_min) * factor
            hi = mid + (target_max - mid) * factor
            log.debug(
                "find_chains: scene %d no chains in [%.1f, %.1f], widening to [%.1f, %.1f]",
                scene_id, target_min, target_max, lo, hi,
            )

    # Final fallback: greedy
    log.warning("find_chains: scene %d — no chains after widening, using greedy fallback", scene_id)
    return _greedy_chain_fallback(assignments, segments_by_id, scene_id, target_ideal, cfg)
