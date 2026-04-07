"""VLM pipeline step — sends segments to a VLM for scene descriptions.

Uses VLMBackend exclusively; no direct provider imports here.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.prompts import GLOBAL_ANALYSIS_PROMPT, SEGMENT_ANALYSIS_PROMPT
from core.schemas.segment import SegmentBase, SegmentDescription
from core.schemas.video_description import VideoDescription, VideoVlm
from video.clip import extract_clip
from video.pipeline import PipelineContext, PipelineStep, PipelineStepError
from video.vlm_backend import create_vlm_backend

if TYPE_CHECKING:
    from core.config import Settings
    from core.storage import ProjectStorage

log = logging.getLogger(__name__)


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove surrounding ```json ... ``` or ``` ... ``` fences if present."""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.DOTALL)


def _parse_json(text: str):
    """Strip markdown fences and parse JSON. Raises ValueError on failure."""
    return json.loads(_strip_fences(text))


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _analyze_global(backend, video_path: Path) -> VideoVlm:
    """Run GLOBAL_ANALYSIS_PROMPT against the full video and parse into VideoVlm."""
    raw = backend.analyze_video(video_path, GLOBAL_ANALYSIS_PROMPT)
    data = _parse_json(raw)
    return VideoVlm.model_validate(data)


def _segment_context(segments: list[SegmentBase]) -> str:
    """Compact JSON summary of all segments for prompt context."""
    return json.dumps(
        [{"segment_id": s.segment_id, "start": s.start, "end": s.end} for s in segments],
        indent=None,
    )


def _analyze_segment(
    backend,
    clip_path: Path,
    segment: SegmentBase,
    global_summary: str,
    all_segments: list[SegmentBase],
) -> SegmentDescription | None:
    """Run SEGMENT_ANALYSIS_PROMPT for one clip. Returns None on any failure."""
    prompt = SEGMENT_ANALYSIS_PROMPT.format(
        global_summary=global_summary,
        segments=_segment_context(all_segments),
        segment_id=segment.segment_id,
        start=f"{segment.start:.3f}",
        end=f"{segment.end:.3f}",
    )
    try:
        raw = backend.analyze_video(clip_path, prompt)
        data = _parse_json(raw)
        if isinstance(data, list):
            data = data[0]
        return SegmentDescription.model_validate(data)
    except Exception as exc:
        log.warning(
            "VLM segment analysis failed for segment %s (%s): %s",
            segment.segment_id,
            clip_path.name,
            exc,
        )
        return None


# ── VLMStep ───────────────────────────────────────────────────────────────────

class VLMStep(PipelineStep):
    """Pipeline step that sends segments to a VLM for scene descriptions.

    1. Runs a global analysis on the full (downsampled) video.
    2. Extracts a clip per segment (reuses existing clips).
    3. Runs per-segment analysis with global context injected.
    4. Saves VideoDescription and list[SegmentDescription] to storage.
    5. Marks the "described" step complete in the manifest.

    Clips are kept at ``videos/{hash}/segments/clips/seg_{id}.mp4``.
    """

    def __init__(self, storage: ProjectStorage, config: Settings) -> None:
        self.storage = storage
        self.config = config

    def check_inputs(self, ctx: PipelineContext) -> None:
        if not ctx.segments:
            raise PipelineStepError(
                "segments is empty — add SegmentScenesStep (and PersistStep) "
                "before VLMStep."
            )
        if ctx.video_hash is None:
            raise PipelineStepError(
                "video_hash is required — add PersistStep before VLMStep."
            )
        if ctx.project_name is None and ctx.project_id is None:
            raise PipelineStepError(
                "project_name/project_id is required — add PersistStep before VLMStep."
            )

    def run(self, ctx: PipelineContext) -> PipelineContext:
        project_name = ctx.project_id or ctx.project_name
        video_hash = ctx.video_hash
        video_path = ctx.downsampled_path or ctx.video_path
        vlm_cfg = self.config.vlm

        backend = create_vlm_backend(vlm_cfg)
        try:
            # ── Global analysis ───────────────────────────────────────────────
            log.info("VLMStep: running global analysis on %s", video_path.name)
            video_vlm = _analyze_global(backend, video_path)
            video_desc = VideoDescription(
                video_id=video_hash,
                video_file=ctx.video_path.name,
                vlm=video_vlm,
            )
            self.storage.save_json(
                project_name,
                f"videos/{video_hash}/descriptions/vlm.json",
                video_desc,
            )
            log.info("VLMStep: global description saved")

            # ── Segment analysis ──────────────────────────────────────────────
            clips_dir = (
                self.storage.get_project_path(project_name)
                / "videos" / video_hash / "segments" / "clips"
            )
            clips_dir.mkdir(parents=True, exist_ok=True)

            global_summary = video_vlm.description
            descriptions: list[SegmentDescription] = []

            for i, segment in enumerate(ctx.segments):
                clip_path = clips_dir / f"seg_{segment.segment_id}.mp4"

                if not clip_path.exists():
                    log.info(
                        "VLMStep: extracting clip %d/%d (segment %s)",
                        i + 1, len(ctx.segments), segment.segment_id,
                    )
                    extract_clip(video_path, segment.start, segment.end, clip_path)
                else:
                    log.info(
                        "VLMStep: clip already exists for segment %s, reusing",
                        segment.segment_id,
                    )

                log.info(
                    "VLMStep: analysing segment %d/%d (%s)",
                    i + 1, len(ctx.segments), segment.segment_id,
                )
                desc = _analyze_segment(
                    backend, clip_path, segment, global_summary, ctx.segments
                )
                if desc is not None:
                    descriptions.append(desc)

                if i < len(ctx.segments) - 1:
                    time.sleep(vlm_cfg.request_delay_s)

            # ── Persist results ───────────────────────────────────────────────
            self.storage.save_json(
                project_name,
                f"videos/{video_hash}/segments/descriptions.json",
                descriptions,
            )
            log.info(
                "VLMStep: saved %d/%d segment descriptions",
                len(descriptions), len(ctx.segments),
            )

            self.storage.mark_step_complete(
                project_name, video_hash, "described", self.config
            )

        finally:
            backend.close()

        return ctx
