from __future__ import annotations

import hashlib

from pydantic import BaseModel


# ── Camera movement (from optical flow + ruptures) ────────────────────────────

class CameraMovement(BaseModel):
    movement_id: int
    start_time: float
    end_time: float
    pan_entry_vel: float = 0.0
    tilt_entry_vel: float = 0.0
    zoom_entry_vel: float = 0.0
    pan_exit_vel: float = 0.0
    tilt_exit_vel: float = 0.0
    zoom_exit_vel: float = 0.0
    pan_monotonicity: float = 0.0
    tilt_monotonicity: float = 0.0
    zoom_monotonicity: float = 0.0
    pan_mean_abs_deriv: float = 0.0
    tilt_mean_abs_deriv: float = 0.0
    zoom_mean_abs_deriv: float = 0.0
    pan_std_deriv: float = 0.0
    tilt_std_deriv: float = 0.0
    zoom_std_deriv: float = 0.0


# ── Stable segment (optical flow + ruptures output) ───────────────────────────

class SegmentBase(BaseModel):
    """Segment produced by optical-flow analysis + change-point detection.

    This is the stable, rarely-recomputed layer. It changes only when the
    video processing config changes (detected via config_hash).
    """
    segment_id: str         # deterministic short hash: sha256(source_video:index)[:8]
    video_file: str         # original filename (e.g. "DJI_0135.MP4")
    source_video: str       # content-hash of the source video file
    start: float            # seconds
    end: float              # seconds
    camera_movements: list[CameraMovement] = []


# ── VLM sub-models for SegmentDescription ─────────────────────────────────────

class TechnicalSpecsReasoning(BaseModel):
    framing: str = ""
    movement: str = ""
    angle: str = ""


class TechnicalSpecs(BaseModel):
    framing: str = ""   # Wide Shot | Medium Shot | Close-Up | etc.
    movement: str = ""  # Static | Pan Left | Tracking Shot | etc.
    angle: str = ""     # Eye Level | High Angle | Bird's Eye View | etc.
    reasoning: TechnicalSpecsReasoning = TechnicalSpecsReasoning()


class ColorProfile(BaseModel):
    dominant_colors: list[str] = []  # "#RRGGBB" strings
    lighting_type: str = ""          # Natural/Golden Hour | Overcast | etc.
    temperature: str = ""            # warm | cool | neutral


class Highlight(BaseModel):
    description: str = ""
    keywords: list[str] = []
    start: str = ""   # "HH:MM:SS.mmm"
    end: str = ""     # "HH:MM:SS.mmm"


class QualityScore(BaseModel):
    rating: str = ""       # excellent | good | medium | bad
    reasoning: str = ""


# ── VLM description (may be regenerated independently) ───────────────────────

class SegmentDescription(BaseModel):
    """VLM-generated description for a segment.

    Stored separately from SegmentBase so VLM results can be regenerated
    without rerunning optical flow / segmentation.
    """
    segment_id: str         # echoed back from the prompt, matches SegmentBase.segment_id
    description: str = ""
    technical_specs: TechnicalSpecs | None = None
    color_profile: ColorProfile | None = None
    highlights: list[Highlight] = []
    quality_score: QualityScore | None = None
    segment_tags: list[str] = []


# ── Merged view (used by all downstream code) ─────────────────────────────────

class Segment(SegmentBase):
    """Merged view of SegmentBase + VLM description(s).

    ``vlm`` is a list to support multiple VLM runs / revisions per segment.
    Defaults to empty when no VLM description exists yet.
    """
    vlm: list[SegmentDescription] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_segment_id(source_video: str, index: int) -> str:
    """Generate a deterministic 8-char segment ID from video hash + segment index."""
    return hashlib.sha256(f"{source_video}:{index}".encode()).hexdigest()[:8]


def build_combined_view(
    segments: list[SegmentBase],
    descriptions: list[SegmentDescription],
) -> list[Segment]:
    """Join SegmentBase list with SegmentDescription list on segment_id.

    Multiple descriptions per segment are grouped into ``vlm`` list (supports
    re-runs / revisions). Segments with no description get ``vlm=[]``.
    Descriptions whose segment_id does not match any segment are silently ignored.
    """
    desc_by_id: dict[str, list[SegmentDescription]] = {}
    for d in descriptions:
        desc_by_id.setdefault(d.segment_id, []).append(d)

    return [
        Segment(**seg.model_dump(), vlm=desc_by_id.get(seg.segment_id, []))
        for seg in segments
    ]
