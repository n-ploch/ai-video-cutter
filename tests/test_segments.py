"""Tests for Pydantic segment schemas and build_combined_view."""
from __future__ import annotations

from core.schemas.segment import (
    CameraMovement,
    ColorProfile,
    Highlight,
    QualityScore,
    Segment,
    SegmentBase,
    SegmentDescription,
    TechnicalSpecs,
    TechnicalSpecsReasoning,
    build_combined_view,
    make_segment_id,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_movement(movement_id: int = 0) -> CameraMovement:
    return CameraMovement(
        movement_id=movement_id,
        start_time=0.0,
        end_time=3.0,
        pan_entry_vel=0.1,
        tilt_entry_vel=0.0,
        zoom_entry_vel=0.0,
        pan_exit_vel=0.2,
        tilt_exit_vel=0.0,
        zoom_exit_vel=0.0,
        pan_monotonicity=0.9,
        tilt_monotonicity=0.0,
        zoom_monotonicity=0.0,
        pan_mean_abs_deriv=0.05,
        tilt_mean_abs_deriv=0.0,
        zoom_mean_abs_deriv=0.0,
        pan_std_deriv=0.01,
        tilt_std_deriv=0.0,
        zoom_std_deriv=0.0,
    )


def _make_base(index: int, source_video: str = "abc12345") -> SegmentBase:
    return SegmentBase(
        segment_id=make_segment_id(source_video, index),
        video_file="test.mp4",
        source_video=source_video,
        start=float(index),
        end=float(index + 5),
        camera_movements=[_make_movement(0)],
    )


def _make_desc(segment_id: str) -> SegmentDescription:
    return SegmentDescription(
        segment_id=segment_id,
        description="Wide shot of landscape",
        technical_specs=TechnicalSpecs(
            framing="Wide Shot",
            movement="Tracking Shot",
            angle="High Angle",
            reasoning=TechnicalSpecsReasoning(
                framing="Captures the scale of the environment.",
                movement="Camera follows the vehicle.",
                angle="Elevated view shows road ahead.",
            ),
        ),
        color_profile=ColorProfile(
            dominant_colors=["#6B7B5A", "#9A8C82"],
            lighting_type="Overcast",
            temperature="cool",
        ),
        highlights=[
            Highlight(
                description="Vehicle crosses stream",
                keywords=["stream", "crossing", "off-road"],
                start="00:00:08.000",
                end="00:00:12.750",
            )
        ],
        quality_score=QualityScore(rating="excellent", reasoning="Smooth drone footage."),
        segment_tags=["aerial", "drone", "mountains"],
    )


# ── make_segment_id ───────────────────────────────────────────────────────────

def test_make_segment_id_returns_8_chars():
    sid = make_segment_id("abc12345", 0)
    assert isinstance(sid, str)
    assert len(sid) == 8


def test_make_segment_id_deterministic():
    assert make_segment_id("abc12345", 0) == make_segment_id("abc12345", 0)


def test_make_segment_id_differs_by_index():
    assert make_segment_id("abc12345", 0) != make_segment_id("abc12345", 1)


def test_make_segment_id_differs_by_source():
    assert make_segment_id("aaa", 0) != make_segment_id("bbb", 0)


# ── CameraMovement ────────────────────────────────────────────────────────────

def test_camera_movement_fields():
    m = _make_movement()
    assert m.movement_id == 0
    assert m.pan_entry_vel == 0.1
    assert m.pan_exit_vel == 0.2


def test_camera_movement_defaults():
    m = CameraMovement(movement_id=1, start_time=0.0, end_time=1.0)
    assert m.pan_entry_vel == 0.0
    assert m.zoom_std_deriv == 0.0


def test_camera_movement_roundtrip():
    m = _make_movement(2)
    loaded = CameraMovement.model_validate(m.model_dump(mode="json"))
    assert loaded.movement_id == 2
    assert loaded.pan_entry_vel == m.pan_entry_vel


# ── SegmentBase ───────────────────────────────────────────────────────────────

def test_segment_base_fields():
    seg = _make_base(0)
    assert len(seg.segment_id) == 8
    assert seg.video_file == "test.mp4"
    assert seg.source_video == "abc12345"
    assert seg.start == 0.0
    assert seg.end == 5.0
    assert len(seg.camera_movements) == 1


def test_segment_base_serializes():
    seg = _make_base(1)
    d = seg.model_dump(mode="json")
    assert d["video_file"] == "test.mp4"
    assert isinstance(d["camera_movements"], list)
    assert d["camera_movements"][0]["movement_id"] == 0


def test_segment_base_roundtrip():
    seg = _make_base(2)
    loaded = SegmentBase.model_validate(seg.model_dump(mode="json"))
    assert loaded.segment_id == seg.segment_id
    assert loaded.camera_movements[0].pan_entry_vel == 0.1


# ── SegmentDescription ────────────────────────────────────────────────────────

def test_segment_description_defaults():
    desc = SegmentDescription(segment_id="aabbccdd")
    assert desc.description == ""
    assert desc.technical_specs is None
    assert desc.color_profile is None
    assert desc.highlights == []
    assert desc.quality_score is None
    assert desc.segment_tags == []


def test_segment_description_full():
    seg_id = make_segment_id("abc12345", 0)
    desc = _make_desc(seg_id)
    assert desc.technical_specs.framing == "Wide Shot"
    assert desc.color_profile.temperature == "cool"
    assert desc.highlights[0].keywords == ["stream", "crossing", "off-road"]
    assert desc.quality_score.rating == "excellent"
    assert "aerial" in desc.segment_tags


def test_segment_description_roundtrip():
    seg_id = make_segment_id("abc12345", 0)
    desc = _make_desc(seg_id)
    loaded = SegmentDescription.model_validate(desc.model_dump(mode="json"))
    assert loaded.segment_id == desc.segment_id
    assert loaded.technical_specs.movement == "Tracking Shot"
    assert loaded.color_profile.dominant_colors == ["#6B7B5A", "#9A8C82"]


# ── Segment (merged view) ─────────────────────────────────────────────────────

def test_segment_vlm_defaults_empty():
    seg = Segment(**_make_base(0).model_dump())
    assert seg.vlm == []


def test_segment_inherits_base_fields():
    base = _make_base(0)
    seg = Segment(**base.model_dump())
    assert seg.segment_id == base.segment_id
    assert seg.camera_movements == base.camera_movements


# ── build_combined_view ───────────────────────────────────────────────────────

def test_build_combined_view_empty_inputs():
    assert build_combined_view([], []) == []


def test_build_combined_view_joins_on_segment_id():
    segments = [_make_base(0), _make_base(1)]
    descriptions = [_make_desc(segments[0].segment_id), _make_desc(segments[1].segment_id)]
    result = build_combined_view(segments, descriptions)
    assert len(result) == 2
    assert len(result[0].vlm) == 1
    assert result[0].vlm[0].description == "Wide shot of landscape"
    assert len(result[1].vlm) == 1


def test_build_combined_view_missing_description_gives_empty_vlm():
    segments = [_make_base(0), _make_base(1)]
    descriptions = [_make_desc(segments[0].segment_id)]
    result = build_combined_view(segments, descriptions)
    assert len(result[0].vlm) == 1
    assert result[1].vlm == []


def test_build_combined_view_no_descriptions():
    segments = [_make_base(i) for i in range(3)]
    result = build_combined_view(segments, [])
    assert all(r.vlm == [] for r in result)
    assert len(result) == 3


def test_build_combined_view_mismatched_ids_no_crash():
    """Descriptions for non-existent segment IDs are silently ignored."""
    segments = [_make_base(0)]
    descriptions = [_make_desc("deadbeef")]   # doesn't match any segment
    result = build_combined_view(segments, descriptions)
    assert len(result) == 1
    assert result[0].vlm == []


def test_build_combined_view_multiple_descriptions_per_segment():
    """Multiple VLM runs for the same segment are all included."""
    seg = _make_base(0)
    desc1 = _make_desc(seg.segment_id)
    desc2 = SegmentDescription(segment_id=seg.segment_id, description="Second run")
    result = build_combined_view([seg], [desc1, desc2])
    assert len(result[0].vlm) == 2


def test_build_combined_view_preserves_base_fields():
    seg = _make_base(0, source_video="deadbeef1234")
    result = build_combined_view([seg], [_make_desc(seg.segment_id)])
    assert result[0].source_video == "deadbeef1234"
    assert result[0].camera_movements[0].movement_id == 0


def test_build_combined_view_returns_segment_instances():
    result = build_combined_view([_make_base(0)], [])
    assert isinstance(result[0], Segment)


# ── VideoDescription ──────────────────────────────────────────────────────────

def test_video_description_schema():
    from core.schemas.video_description import VideoDescription, VideoVlm
    vd = VideoDescription(
        video_id="abc12345",
        video_file="DJI_0135.MP4",
        vlm=VideoVlm(
            description="Drone footage over mountains.",
            key_subjects=[["SUV", "Dark grey vehicle on dirt road."]],
            tone=["cinematic", "adventurous"],
            genre_or_type="aerial_videography",
            tags=["drone", "mountains"],
        ),
    )
    assert vd.video_id == "abc12345"
    assert vd.vlm.genre_or_type == "aerial_videography"
    assert vd.vlm.key_subjects[0][0] == "SUV"


def test_video_description_roundtrip():
    from core.schemas.video_description import VideoDescription, VideoVlm
    vd = VideoDescription(
        video_id="abc12345",
        video_file="DJI_0135.MP4",
        vlm=VideoVlm(description="Test", tags=["a", "b"]),
    )
    loaded = VideoDescription.model_validate(vd.model_dump(mode="json"))
    assert loaded.vlm.tags == ["a", "b"]


def test_video_description_defaults():
    from core.schemas.video_description import VideoDescription
    vd = VideoDescription(video_id="abc", video_file="test.mp4")
    assert vd.vlm.description == ""
    assert vd.vlm.tags == []
