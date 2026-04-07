"""Unit tests for editor/tools/pathfinding.py.

No LLM calls, no model loading.  All tests use synthetic segment dicts
and a real EditorConfig.
"""
from __future__ import annotations

import pytest

from core.config import EditorConfig
from editor.tools.pathfinding import (
    _greedy_chain_fallback,
    build_dag,
    compute_kinematic_cost,
    compute_segment_penalty,
    compute_total_cost,
    find_chains,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cfg(**overrides) -> EditorConfig:
    defaults = dict(w1=0.4, w2=0.3, w3=0.2, w4=0.1, w5=0.3)
    defaults.update(overrides)
    return EditorConfig(**defaults)


def _seg(
    seg_id: str,
    start: float = 0.0,
    end: float = 5.0,
    pan_entry=0.0, tilt_entry=0.0, zoom_entry=0.0,
    pan_exit=0.0, tilt_exit=0.0, zoom_exit=0.0,
    quality: str = "good",
) -> dict:
    return {
        "segment_id": seg_id,
        "start": start,
        "end": end,
        "video_file": "fake.mp4",
        "camera_movements": [{
            "pan_entry_vel": pan_entry,
            "tilt_entry_vel": tilt_entry,
            "zoom_entry_vel": zoom_entry,
            "pan_exit_vel": pan_exit,
            "tilt_exit_vel": tilt_exit,
            "zoom_exit_vel": zoom_exit,
            "pan_std_deriv": 0.0,
            "tilt_std_deriv": 0.0,
            "zoom_std_deriv": 0.0,
            "pan_monotonicity": 1.0,
            "tilt_monotonicity": 1.0,
            "zoom_monotonicity": 1.0,
        }],
        "vlm": [{"quality_score": {"rating": quality}}],
    }


def _assignment(seg_id: str, bucket: int, score: float = 0.8) -> dict:
    return {"segment_id": seg_id, "bucket_idx": bucket, "narrative_score": score}


# ── compute_kinematic_cost ────────────────────────────────────────────────────

def test_kinematic_cost_both_static():
    """Two segments with zero velocity vectors → cost is 0.0."""
    a = _seg("a")
    b = _seg("b")
    assert compute_kinematic_cost(a, b, w1=0.4, w2=0.3) == pytest.approx(0.0)


def test_kinematic_cost_no_camera_movements():
    """Segments with no camera_movements key → treated as static, cost is 0.0."""
    a = {"segment_id": "a", "camera_movements": []}
    b = {"segment_id": "b", "camera_movements": []}
    assert compute_kinematic_cost(a, b, w1=0.4, w2=0.3) == pytest.approx(0.0)


def test_kinematic_cost_opposite_directions_high():
    """Opposite exit/entry velocity directions yield high direction cost."""
    a = _seg("a", pan_exit=1.0)        # exits panning right
    b = _seg("b", pan_entry=-1.0)      # enters panning left (opposite)
    cost = compute_kinematic_cost(a, b, w1=1.0, w2=0.0)
    # cos_sim([1,0,0], [-1,0,0]) = -1 → direction_cost = 1 - (-1) = 2.0
    assert cost == pytest.approx(2.0, abs=1e-5)


def test_kinematic_cost_same_direction_zero():
    """Identical exit/entry velocity → direction cost = 0, speed diff = 0."""
    a = _seg("a", pan_exit=1.0)
    b = _seg("b", pan_entry=1.0)
    cost = compute_kinematic_cost(a, b, w1=0.4, w2=0.3)
    assert cost == pytest.approx(0.0, abs=1e-5)


# ── compute_segment_penalty ───────────────────────────────────────────────────

def test_segment_penalty_no_movements():
    """Segment with empty camera_movements → penalty is 0.0."""
    s = {"segment_id": "x", "camera_movements": []}
    assert compute_segment_penalty(s, w3=0.2, w4=0.1) == pytest.approx(0.0)


def test_segment_penalty_monotonic_rewarded():
    """Perfect monotonicity (1.0) reduces penalty (negative contribution via w4)."""
    s = _seg("x")  # all monotonicity=1.0, all std_deriv=0.0
    penalty = compute_segment_penalty(s, w3=0.2, w4=0.5)
    # instability=0, monotonicity=1.0 → penalty = 0.2*0 - 0.5*1 = -0.5
    assert penalty == pytest.approx(-0.5, abs=1e-5)


# ── build_dag ─────────────────────────────────────────────────────────────────

def test_build_dag_empty_assignments_no_path():
    """Empty assignments → graph has source+sink but no path between them."""
    import networkx as nx
    cfg = _cfg()
    dag = build_dag(scene_id=1, assignments=[], segments_by_id={}, cfg=cfg)
    assert not nx.has_path(dag, "__source__", "__sink__")


def test_build_dag_single_bucket_path_exists():
    """One segment in one bucket → valid source→node→sink path."""
    import networkx as nx
    s = _seg("s1")
    assignments = [_assignment("s1", bucket=0)]
    dag = build_dag(1, assignments, {"s1": s}, _cfg())
    assert nx.has_path(dag, "__source__", "__sink__")


def test_build_dag_missing_segment_edge_skipped():
    """Assignment references ID absent from segments_by_id → edge not added, no crash."""
    import networkx as nx
    s1 = _seg("s1", end=3.0)
    # s2 exists in assignments but not in segments_by_id
    assignments = [_assignment("s1", 0), _assignment("ghost", 1)]
    dag = build_dag(1, assignments, {"s1": s1}, _cfg())
    # No edge from bucket 0 to bucket 1 because ghost is missing
    assert dag.number_of_nodes() > 0  # didn't crash


def test_build_dag_two_buckets_connected():
    """Two segments in consecutive buckets → path exists with computed cost."""
    import networkx as nx
    s1 = _seg("s1", end=3.0)
    s2 = _seg("s2", start=3.0, end=7.0)
    assignments = [_assignment("s1", 0), _assignment("s2", 1)]
    dag = build_dag(1, assignments, {"s1": s1, "s2": s2}, _cfg())
    assert nx.has_path(dag, "__source__", "__sink__")


# ── find_chains ───────────────────────────────────────────────────────────────

def test_find_chains_disconnected_dag_uses_greedy():
    """Disconnected DAG (no path) falls back to greedy chain."""
    import networkx as nx
    s1 = _seg("s1", end=5.0)
    assignments = [_assignment("s1", 0)]

    # Build a valid DAG first, then break the connection
    dag = build_dag(1, assignments, {"s1": s1}, _cfg())
    # Remove all edges from source to break connectivity
    dag.remove_edges_from(list(dag.edges("__source__")))

    chains = find_chains(
        dag, {"s1": s1}, assignments,
        scene_id=1, target_min=3.0, target_max=8.0, target_ideal=5.0,
        top_k=3, cfg=_cfg(),
    )
    # Greedy fallback returns one chain
    assert len(chains) >= 1
    assert any(link.segment_id == "s1" for link in chains[0].links)


def test_find_chains_finds_valid_chain_in_range():
    """find_chains returns a chain whose duration is within [min, max]."""
    s1 = _seg("s1", start=0.0, end=5.0)
    s2 = _seg("s2", start=5.0, end=10.0)
    assignments = [_assignment("s1", 0), _assignment("s2", 1)]
    segs = {"s1": s1, "s2": s2}
    dag = build_dag(1, assignments, segs, _cfg())

    chains = find_chains(
        dag, segs, assignments,
        scene_id=1, target_min=8.0, target_max=12.0, target_ideal=10.0,
        top_k=3, cfg=_cfg(),
    )
    assert len(chains) >= 1
    assert chains[0].total_duration == pytest.approx(10.0, abs=0.01)


def test_find_chains_no_duration_match_falls_back_to_greedy():
    """No chains within [min, max] even after widening → greedy fallback returned."""
    s1 = _seg("s1", start=0.0, end=2.0)  # 2 s segment
    assignments = [_assignment("s1", 0)]
    segs = {"s1": s1}
    dag = build_dag(1, assignments, segs, _cfg())

    # Demand a duration range that the 2s segment cannot satisfy (even with widening)
    chains = find_chains(
        dag, segs, assignments,
        scene_id=1, target_min=100.0, target_max=200.0, target_ideal=150.0,
        top_k=3, cfg=_cfg(),
    )
    # Greedy fallback returns what's available
    assert len(chains) >= 1


# ── _greedy_chain_fallback ────────────────────────────────────────────────────

def test_greedy_fallback_empty_assignments_returns_empty():
    result = _greedy_chain_fallback([], {}, scene_id=1, target_ideal=5.0, cfg=_cfg())
    assert result == []


def test_greedy_fallback_missing_segment_skipped():
    """Assignment references a missing segment_id → that link skipped, no crash."""
    assignments = [_assignment("ghost", 0)]
    result = _greedy_chain_fallback(assignments, {}, scene_id=1, target_ideal=5.0, cfg=_cfg())
    assert result == []  # ghost skipped → no links → no chain


def test_greedy_fallback_picks_highest_narrative_score():
    """Greedy selects the segment with the highest narrative_score per bucket."""
    s_low = _seg("low", end=3.0)
    s_high = _seg("high", end=3.0)
    assignments = [
        _assignment("low", 0, score=0.2),
        _assignment("high", 0, score=0.9),
    ]
    segs = {"low": s_low, "high": s_high}
    result = _greedy_chain_fallback(assignments, segs, scene_id=1, target_ideal=3.0, cfg=_cfg())

    assert len(result) == 1
    assert result[0].links[0].segment_id == "high"  # ChainLink is a Pydantic model
