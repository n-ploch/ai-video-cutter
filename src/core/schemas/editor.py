"""Pydantic schemas for the timeline assembly (editor) agent."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ── Retrieval ──────────────────────────────────────────────────────────────────

class CandidateInfo(BaseModel):
    segment_id: str
    embedding_score: float
    keyword_score: float
    combined_score: float
    quality_rating: str   # "excellent" | "good" | "medium" | "bad"
    duration: float


# ── Phase A: Narrative Analysis (LLM structured output) ───────────────────────

class BucketDefinition(BaseModel):
    bucket_idx: int
    description: str        # e.g. "establishing shot", "action climax"
    min_duration: float     # seconds
    max_duration: float     # seconds
    required: bool = True


class BucketAssignment(BaseModel):
    segment_id: str
    bucket_idx: int = 0          # default to first bucket if LLM omits it
    narrative_score: float = 0.5 # default to neutral score if LLM omits it


class NarrativeAnalysis(BaseModel):
    """Phase A LLM output: per-scene duration target + bucket structure + candidate scoring."""
    scene_id: int
    target_duration_min: float
    target_duration_max: float
    target_duration_ideal: float
    buckets: list[BucketDefinition]
    assignments: list[BucketAssignment]
    pruned_segment_ids: list[str]
    reasoning: str


# ── Phase B / C: Chains ────────────────────────────────────────────────────────

class ChainLink(BaseModel):
    segment_id: str
    bucket_idx: int
    start: float
    end: float
    video_file: str
    edge_cost: float    # C_total for the transition INTO this segment (0.0 for first)


class Chain(BaseModel):
    scene_id: int
    links: list[ChainLink]
    total_cost: float
    total_duration: float
    duration_delta: float   # abs(total_duration - target_duration_ideal)


class ChainSelection(BaseModel):
    """Phase C LLM output: editorial chain selection."""
    scene_id: int
    selected_chain_index: int   # 0-based index into the top-k chains offered
    reasoning: str
    override_notes: str = ""    # filled by human at Gate 2


# ── Stage 6: Stitching ─────────────────────────────────────────────────────────

class BoundaryInfo(BaseModel):
    scene_id_a: int
    scene_id_b: int
    segment_id_a: str       # last segment of scene A
    segment_id_b: str       # first segment of scene B
    kinematic_cost: float
    flagged: bool


class StitchDecision(BaseModel):
    """Stitching agent LLM output per flagged boundary."""
    boundary_idx: int
    action: Literal["transition", "swap_entry", "swap_exit", "accept"]
    transition_type: str = ""       # e.g. "dissolve", "dip_to_black"
    swap_segment_id: str = ""       # replacement segment ID
    reasoning: str


# ── Stage 8: Automated Review ─────────────────────────────────────────────────

class SceneReviewNote(BaseModel):
    scene_id: int | None = None
    issue: str
    severity: Literal["minor", "structural"]
    suggestion: str


class TimelineReview(BaseModel):
    """Reviewer LLM output: structural quality assessment of the full timeline."""
    overall_score: float
    scene_notes: list[SceneReviewNote]
    has_structural_issues: bool
    auto_fix_applied: list[str]     # descriptions of minor fixes the LLM applied
    decision: Literal["approve", "revise"]


# ── Final persisted artifact ───────────────────────────────────────────────────

class TimelineSegmentEntry(BaseModel):
    position: int           # 1-based ordering in the final cut
    scene_id: int
    segment_id: str
    video_file: str
    source_video: str       # content-hash of source video
    start: float
    end: float
    duration: float
    bucket_idx: int
    quality_rating: str
    edge_cost: float
    stitch_action: str = "cut"  # "cut" | "dissolve" | etc. — set by stitching stage


class SceneTimeline(BaseModel):
    scene_id: int
    scene_description: str
    chain_cost: float
    total_duration: float
    entries: list[TimelineSegmentEntry]


class TimelineOutput(BaseModel):
    """Versioned output of the timeline assembly agent."""
    project_name: str
    storyboard_version: int
    scenes: list[SceneTimeline]
    boundaries: list[BoundaryInfo]
    stitch_decisions: list[StitchDecision]
    review: TimelineReview | None = None
    gate2_round: int = 0
    approved: bool = False
    total_duration: float
    total_segments: int
