"""LangGraph state definition for the timeline assembly agent."""
from __future__ import annotations

from typing import TypedDict


class EditorState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    project_name: str
    storyboard_version: int
    scenes: list[dict]      # list of StoryboardScene.model_dump()
    segments: list[dict]    # list of Segment.model_dump(mode="json")

    # ── Stage 2: Candidate pools ─────────────────────────────────────────────
    scene_candidates: dict  # {str(scene_id): [CandidateInfo dicts]}

    # ── Stage 3: Post-dedup pools ─────────────────────────────────────────────
    deduped_candidates: dict    # {str(scene_id): [CandidateInfo dicts]}
    gap_warnings: list[str]     # scenes where pool < min_candidates_per_scene

    # ── Stage 5: Per-scene assembly ───────────────────────────────────────────
    narrative_analyses: dict    # {str(scene_id): NarrativeAnalysis dict}
    chains_per_scene: dict      # {str(scene_id): [Chain dicts]}
    chain_selections: dict      # {str(scene_id): ChainSelection dict}

    # ── Stage 6: Stitching ────────────────────────────────────────────────────
    boundaries: list[dict]      # [BoundaryInfo dicts]
    stitch_decisions: list[dict]    # [StitchDecision dicts]

    # ── Stage 7: Human Gate 2 ────────────────────────────────────────────────
    gate2_round: int
    gate2_overrides: dict       # {str(scene_id): {"chain_index": int, "notes": str}}
    flagged_scene_ids: list[int]    # scenes to re-assemble

    # ── Stage 8: Automated review ────────────────────────────────────────────
    review: dict | None         # TimelineReview dict

    # ── Stage 9: Final approval ───────────────────────────────────────────────
    approved: bool

    # ── Config mirrors ────────────────────────────────────────────────────────
    max_gate2_rounds: int
    min_candidates_per_scene: int
    top_k_candidates: int
    top_k_chains: int
