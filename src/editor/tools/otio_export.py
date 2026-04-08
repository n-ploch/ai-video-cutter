"""Convert a TimelineOutput to an OpenTimelineIO timeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.schemas.editor import TimelineOutput

log = logging.getLogger(__name__)

# Default transition handle length in seconds for dissolves / dip_to_black.
_DEFAULT_TRANSITION_DURATION_S: float = 0.5


def timeline_to_otio(
    timeline: "TimelineOutput",
    video_paths: dict[str, str],   # source_video hash → absolute path string
    rate: float = 30.0,
) -> object:
    """Convert a TimelineOutput to an opentimelineio.schema.Timeline.

    Args:
        timeline:    Parsed TimelineOutput pydantic model.
        video_paths: Mapping from source_video hash to the absolute path of the
                     original video file.  Entries whose hash is missing will
                     fall back to the video_file filename (unresolved reference).
        rate:        Rational time rate (frames per second) used throughout the
                     OTIO timeline.  Float second timestamps from the JSON are
                     converted by multiplying by this rate.

    Returns:
        An ``opentimelineio.schema.Timeline`` ready to serialize.
    """
    import opentimelineio as otio

    def _rt(seconds: float) -> otio.opentime.RationalTime:
        return otio.opentime.RationalTime(round(seconds * rate), rate)

    def _make_clip(entry: dict) -> otio.schema.Clip:
        path = video_paths.get(entry["source_video"], entry.get("video_file", ""))
        ref = otio.schema.ExternalReference(
            target_url=path,
            available_range=None,  # let the editor determine full range
        )
        source_range = otio.opentime.TimeRange(
            start_time=_rt(entry["start"]),
            duration=_rt(entry["end"] - entry["start"]),
        )
        metadata = {
            "segment_id": entry["segment_id"],
            "scene_id": entry["scene_id"],
            "bucket_idx": entry["bucket_idx"],
            "quality_rating": entry["quality_rating"],
            "edge_cost": entry["edge_cost"],
        }
        return otio.schema.Clip(
            name=entry["segment_id"],
            media_reference=ref,
            source_range=source_range,
            metadata={"ai_video_cutter": metadata},
        )

    def _make_transition(stitch_action: str) -> otio.schema.Transition | None:
        if stitch_action in ("cut", "accept", ""):
            return None
        half = _rt(_DEFAULT_TRANSITION_DURATION_S / 2)
        transition_type = otio.schema.TransitionTypes.SMPTE_Dissolve
        return otio.schema.Transition(
            name=stitch_action,
            transition_type=transition_type,
            in_offset=half,
            out_offset=half,
            metadata={"ai_video_cutter": {"stitch_action": stitch_action}},
        )

    # Flatten all entries across scenes, sorted by position
    all_entries: list[dict] = sorted(
        (e.model_dump() if hasattr(e, "model_dump") else dict(e)
         for scene in timeline.scenes
         for e in scene.entries),
        key=lambda e: e["position"],
    )

    track = otio.schema.Track(
        name="Video",
        kind=otio.schema.TrackKind.Video,
    )

    for i, entry in enumerate(all_entries):
        clip = _make_clip(entry)
        stitch = entry.get("stitch_action", "cut")

        # A non-cut stitch_action on this entry means there's a transition
        # *into* this clip from the previous one.
        if i > 0 and stitch not in ("cut", "accept", ""):
            transition = _make_transition(stitch)
            if transition is not None:
                track.append(transition)
                log.debug(
                    "otio_export: added %s transition before segment %s",
                    stitch, entry["segment_id"],
                )

        track.append(clip)

    # Add scene markers at the first clip of each scene
    first_entry_by_scene: dict[int, dict] = {}
    for e in all_entries:
        sid = e["scene_id"]
        if sid not in first_entry_by_scene:
            first_entry_by_scene[sid] = e

    for scene in timeline.scenes:
        entry = first_entry_by_scene.get(scene.scene_id)
        if entry is None:
            continue
        # Compute global time offset for this clip in the track
        offset_s = sum(
            e["end"] - e["start"]
            for e in all_entries
            if e["position"] < entry["position"]
        )
        marker = otio.schema.Marker(
            name=f"Scene {scene.scene_id}",
            color=otio.schema.MarkerColor.GREEN,
            marked_range=otio.opentime.TimeRange(
                start_time=_rt(offset_s),
                duration=_rt(0),
            ),
            metadata={"ai_video_cutter": {"scene_description": scene.scene_description}},
        )
        track.markers.append(marker)

    otio_timeline = otio.schema.Timeline(
        name=f"{timeline.project_name} v{timeline.storyboard.version}",
        metadata={
            "ai_video_cutter": {
                "project_name": timeline.project_name,
                "storyboard_version": timeline.storyboard.version,
                "total_duration": timeline.total_duration,
                "total_segments": timeline.total_segments,
                "gate2_round": timeline.gate2_round,
            }
        },
    )
    otio_timeline.tracks.append(track)

    log.info(
        "otio_export: built timeline '%s' — %d clips, %.1fs @ %.0ffps",
        otio_timeline.name, len(all_entries), timeline.total_duration, rate,
    )
    return otio_timeline
