"""
Composable step-based video segmentation pipeline.

Each PipelineStep is self-contained:
  - check_inputs(ctx) raises PipelineStepError if required context fields are absent.
  - run(ctx) performs the computation and writes its outputs into ctx.

Pipeline itself has no validation logic — every step owns its own contract.
Pipeline.resume(ctx) runs steps against an already-populated context, enabling
cross-pipeline state reuse without re-running expensive earlier steps.

Usage examples
--------------
# Default pipeline (flow → preprocess → segment → persist)
ctx = default_pipeline(proc_config, seg_config, storage).run(video_path)

# Stop after optical flow, inspect raw signal
ctx = Pipeline([OpticalFlowStep(proc_config)]).run(video_path)

# Resume with different segmentation penalties, reusing existing flow
ctx2 = Pipeline([
    PreprocessSignalStep(SegmentationConfig(fd_penalty=5.0)),
    SegmentScenesStep(SegmentationConfig(fd_penalty=5.0)),
]).resume(ctx)

# Segment on raw signal, no preprocessing
ctx = Pipeline([
    OpticalFlowStep(proc_config),
    SegmentScenesStep(seg_config, signal_source="raw"),
]).run(video_path)

# With downsampling
ctx = Pipeline([
    DownsampleStep(proc_config, output_dir=tmp_dir),
    OpticalFlowStep(proc_config),
    PreprocessSignalStep(seg_config),
    SegmentScenesStep(seg_config),
]).run(video_path)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import cv2
import numpy as np
from tqdm import tqdm

from core.schemas.segment import SegmentBase
from core.schemas.video import FrameMetrics, ProcessingConfig, SegmentationConfig
from video.analysis import build_segments, save_segments
from video.downsample import downsample_video
from video.homography import decompose_flow
from video.metrics import compute_frame_metrics, save_frame_metrics, signal_row
from video.optical_flow import compute_flow, flow_statistics, resize_for_flow
from video.segmentation import preprocess_signal, SIGNAL_COLS

if TYPE_CHECKING:
    from core.config import Settings

log = logging.getLogger(__name__)


# ── Errors ────────────────────────────────────────────────────────────────────

class PipelineStepError(RuntimeError):
    """Raised by check_inputs when a required context field is missing."""


# ── Context ───────────────────────────────────────────────────────────────────

@dataclass
class PipelineContext:
    """
    Shared state passed through every pipeline step.

    All fields except video_path default to empty/None so that a context can be
    constructed from any partial state and handed to Pipeline.resume().
    """
    video_path: Path
    project_name: str | None = None

    # Set by DownsampleStep
    downsampled_path: Path | None = None

    # Set by OpticalFlowStep
    raw_rows: list[dict] = field(default_factory=list)
    frame_metrics: list[FrameMetrics] = field(default_factory=list)
    raw_signal: np.ndarray | None = None        # shape (T, 4)
    timestamps: np.ndarray | None = None        # shape (T,)

    # Set by PreprocessSignalStep
    preprocessed_signal: np.ndarray | None = None

    # Set by SegmentScenesStep
    segments: list[SegmentBase] = field(default_factory=list)

    # Set by PersistStep
    project_id: str | None = None   # project name used as storage key
    video_hash: str | None = None   # content-hash of video_path


# ── Abstract base ─────────────────────────────────────────────────────────────

class PipelineStep(ABC):
    @abstractmethod
    def check_inputs(self, ctx: PipelineContext) -> None:
        """Raise PipelineStepError if required context fields are missing or invalid."""

    @abstractmethod
    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute the step, write outputs into ctx, and return ctx."""


# ── Steps ─────────────────────────────────────────────────────────────────────

class DownsampleStep(PipelineStep):
    """Downsample the source video and persist it to disk. Sets ctx.downsampled_path.

    When *storage* and *config* are provided the step is manifest-aware:
    - The downsampled file is saved to ``videos/{hash}/{stem}_downsampled.{fmt}``
      inside the project directory.
    - ``ctx.video_hash`` is populated early (before PersistStep) as a side effect.
    - If the manifest records a current "downsampled" completion and the file
      already exists on disk the step is skipped entirely.

    When *storage* is None the file is written to *output_dir*.  If *output_dir*
    is also None a temporary directory is created automatically (useful for
    in-memory pipelines and tests).
    """

    def __init__(
        self,
        proc_config: ProcessingConfig,
        output_dir: Path | None = None,
        storage=None,
        config=None,
    ):
        self.proc_config = proc_config
        self.output_dir = Path(output_dir) if output_dir else None
        self.storage = storage
        self.config = config
        self._tmpdir = None  # holds TemporaryDirectory when auto-created

    def check_inputs(self, ctx: PipelineContext) -> None:
        if not ctx.video_path.exists():
            raise PipelineStepError(f"video_path does not exist: {ctx.video_path}")

    def run(self, ctx: PipelineContext) -> PipelineContext:
        import tempfile

        from core.storage import hash_video_file

        stem = ctx.video_path.stem
        fmt = self.proc_config.output_format

        if self.storage is not None:
            # ── Storage-backed: manifest-aware, persistent output ─────────────
            video_hash = hash_video_file(ctx.video_path)
            ctx.video_hash = video_hash

            name = ctx.project_id or ctx.project_name or stem
            # Ensure the video is registered (idempotent — creates manifest entry
            # and videos/{hash}/ folder if absent).
            self.storage.add_video(name, ctx.video_path)

            out = (
                self.storage.get_project_path(name)
                / "videos" / video_hash
                / f"{stem}_downsampled.{fmt}"
            )

            if (
                self.config is not None
                and out.exists()
                and self.storage.is_step_current(name, video_hash, "downsampled", self.config)
            ):
                ctx.downsampled_path = out
                log.info("DownsampleStep: skipping (already current) → %s", out)
                return ctx

            ctx.downsampled_path = downsample_video(ctx.video_path, out, self.proc_config)

            if self.config is not None:
                self.storage.mark_step_complete(name, video_hash, "downsampled", self.config)

        else:
            # ── Memory-only: write to output_dir or a managed temp dir ────────
            if self.output_dir is None:
                import tempfile as _tf
                self._tmpdir = _tf.TemporaryDirectory()
                out_dir = Path(self._tmpdir.name)
            else:
                out_dir = self.output_dir
                out_dir.mkdir(parents=True, exist_ok=True)

            out = out_dir / f"{stem}_downsampled.{fmt}"
            ctx.downsampled_path = downsample_video(ctx.video_path, out, self.proc_config)

        log.info("DownsampleStep → %s", ctx.downsampled_path)
        return ctx


class OpticalFlowStep(PipelineStep):
    """
    Stream frames from ctx.downsampled_path (if set) or ctx.video_path,
    compute Farneback optical flow + RANSAC homography per frame pair.

    Writes: ctx.raw_rows, ctx.frame_metrics, ctx.raw_signal, ctx.timestamps.
    """

    def __init__(self, proc_config: ProcessingConfig, flow_fps: float | None = None):
        self.proc_config = proc_config
        self.flow_fps = flow_fps

    def check_inputs(self, ctx: PipelineContext) -> None:
        source = ctx.downsampled_path or ctx.video_path
        if not source.exists():
            raise PipelineStepError(f"Source video not found: {source}")

    def run(self, ctx: PipelineContext) -> PipelineContext:
        import ffmpeg

        source = ctx.downsampled_path or ctx.video_path
        width = self.proc_config.target_width
        hwaccel = self.proc_config.hwaccel

        probe = ffmpeg.probe(str(source))
        vs = next(s for s in probe["streams"] if s["codec_type"] == "video")
        orig_w, orig_h = int(vs["width"]), int(vs["height"])

        # Resolve fps: flow_fps takes priority, then proc_config, then native.
        if self.flow_fps is not None:
            fps = self.flow_fps
        elif self.proc_config.target_fps is not None:
            fps = self.proc_config.target_fps
        else:
            num, den = (int(x) for x in vs["r_frame_rate"].split("/"))
            fps = num / den

        target_h = int(width * orig_h / orig_w)
        if target_h % 2:
            target_h += 1
        frame_bytes = width * target_h * 3
        total_frames = int(float(probe["format"]["duration"]) * fps)

        input_kwargs = {"hwaccel": hwaccel} if hwaccel else {}
        proc = (
            ffmpeg.input(str(source), **input_kwargs)
            .filter("fps", fps=fps)
            .filter("scale", width, target_h)
            .output("pipe:", format="rawvideo", pix_fmt="rgb24")
            .run_async(pipe_stdout=True, quiet=True)
        )

        raw_rows: list[dict] = []
        frame_metrics: list[FrameMetrics] = []
        prev_gray: np.ndarray | None = None
        frame_idx = 0

        try:
            with tqdm(total=total_frames, desc=source.name, unit="fr") as pbar:
                while True:
                    raw = proc.stdout.read(frame_bytes)
                    if len(raw) != frame_bytes:
                        break
                    frame_idx += 1
                    pbar.update(1)
                    timestamp = frame_idx / fps
                    rgb = np.frombuffer(raw, dtype="uint8").reshape((target_h, width, 3)).copy()
                    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                    gray = resize_for_flow(bgr)

                    if prev_gray is not None:
                        flow = compute_flow(prev_gray, gray)
                        mag, _, coherence = flow_statistics(flow)
                        decomp = decompose_flow(flow)
                        frame_metrics.append(
                            compute_frame_metrics(frame_idx, timestamp, mag, coherence, decomp)
                        )
                        if decomp is not None:
                            raw_rows.append(signal_row(timestamp, frame_idx, decomp))

                    prev_gray = gray
        finally:
            proc.stdout.close()
            proc.wait()

        if not raw_rows:
            raise PipelineStepError(
                f"No RANSAC decompositions succeeded for {source}. "
                "Video may be too short or entirely static."
            )

        ctx.raw_rows = raw_rows
        ctx.frame_metrics = frame_metrics
        ctx.timestamps = np.array([r["timestamp"] for r in raw_rows])
        ctx.raw_signal = np.array(
            [[r[c] for c in SIGNAL_COLS] for r in raw_rows], dtype=np.float64
        )
        log.info(
            f"OpticalFlowStep → {len(raw_rows)} flow samples, "
            f"{len(frame_metrics)} frame metrics"
        )
        return ctx


class PreprocessSignalStep(PipelineStep):
    """
    Apply Savitzky-Golay smoothing + min-max normalisation to ctx.raw_signal.

    Writes: ctx.preprocessed_signal.
    """

    def __init__(self, seg_config: SegmentationConfig):
        self.seg_config = seg_config

    def check_inputs(self, ctx: PipelineContext) -> None:
        if ctx.raw_signal is None:
            raise PipelineStepError(
                "raw_signal is required — add OpticalFlowStep before PreprocessSignalStep."
            )
        if len(ctx.raw_signal) < 2:
            raise PipelineStepError(
                f"raw_signal has only {len(ctx.raw_signal)} row(s); need ≥ 2 to preprocess."
            )

    def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.preprocessed_signal = preprocess_signal(
            ctx.raw_signal,
            window=self.seg_config.savgol_window,
            poly=self.seg_config.savgol_poly,
        )
        log.info("PreprocessSignalStep → signal smoothed and normalised")
        return ctx


class SegmentScenesStep(PipelineStep):
    """
    Detect coarse scene boundaries (Pelt l2) and per-scene camera movements (Pelt l1).

    Parameters
    ----------
    seg_config    : segmentation penalties and smoothing parameters.
    signal_source : "preprocessed" (default) or "raw".
                    Each value enforces a distinct check_inputs contract:
                    - "preprocessed" requires ctx.preprocessed_signal to be set.
                    - "raw" requires ctx.raw_signal to be set.
                    This allows skipping PreprocessSignalStep entirely.

    Writes: ctx.segments.
    """

    def __init__(
        self,
        seg_config: SegmentationConfig,
        signal_source: Literal["preprocessed", "raw"] = "preprocessed",
    ):
        self.seg_config = seg_config
        self.signal_source = signal_source

    def check_inputs(self, ctx: PipelineContext) -> None:
        if self.signal_source == "preprocessed":
            if ctx.preprocessed_signal is None:
                raise PipelineStepError(
                    "preprocessed_signal is required — add PreprocessSignalStep before "
                    "SegmentScenesStep, or use signal_source='raw'."
                )
        elif self.signal_source == "raw":
            if ctx.raw_signal is None:
                raise PipelineStepError(
                    "raw_signal is required — add OpticalFlowStep before SegmentScenesStep."
                )
        else:
            raise PipelineStepError(
                f"Unknown signal_source={self.signal_source!r}. "
                "Use 'preprocessed' or 'raw'."
            )
        if ctx.timestamps is None:
            raise PipelineStepError(
                "timestamps is required — add OpticalFlowStep before SegmentScenesStep."
            )

    def run(self, ctx: PipelineContext) -> PipelineContext:
        signal = (
            ctx.preprocessed_signal
            if self.signal_source == "preprocessed"
            else ctx.raw_signal
        )
        ctx.segments = build_segments(
            signal,
            ctx.timestamps,
            fd_penalty=self.seg_config.fd_penalty,
            subseg_penalty=self.seg_config.subseg_penalty,
            source_video=ctx.video_hash or "",
            video_file=ctx.video_path.name,
        )
        log.info(f"SegmentScenesStep ({self.signal_source}) → {len(ctx.segments)} segments")
        return ctx


class PersistStep(PipelineStep):
    """
    Save frame_metrics and segments to project storage.

    Creates the project if ctx.project_id is None.
    Writes: ctx.project_id, ctx.video_hash.
    """

    def __init__(
        self,
        storage,
        project_name: str | None = None,
        config: Settings | None = None,
    ):
        self.storage = storage
        self.project_name = project_name
        self.config = config

    def check_inputs(self, ctx: PipelineContext) -> None:
        if not ctx.frame_metrics and not ctx.segments:
            raise PipelineStepError(
                "Nothing to persist: both frame_metrics and segments are empty."
            )

    def run(self, ctx: PipelineContext) -> PipelineContext:
        from core.project import ProjectStatus
        from core.storage import hash_video_file

        name = self.project_name or ctx.project_name or ctx.video_path.stem

        if ctx.project_id is None:
            project_dir = self.storage.get_project_path(name)
            if (project_dir / "project.json").exists():
                # Existing project — load it and add the video to the manifest.
                project = self.storage.get_project(name)
            else:
                # Brand-new project — create folder structure.
                project = self.storage.create_project(name, [ctx.video_path])
            ctx.project_id = name
        else:
            project = self.storage.get_project(ctx.project_id)

        # Hash the video and register it in the manifest (idempotent).
        # DownsampleStep may have already computed and set both of these.
        video_hash = ctx.video_hash or hash_video_file(ctx.video_path)
        ctx.video_hash = video_hash
        self.storage.add_video(name, ctx.video_path)

        if ctx.frame_metrics:
            save_frame_metrics(self.storage, name, ctx.frame_metrics)

        if ctx.segments:
            save_segments(self.storage, name, video_hash, ctx.segments)

        if self.config is not None:
            for step in ("optical_flow", "segmented"):
                self.storage.mark_step_complete(name, video_hash, step, self.config)

        project.status = ProjectStatus.ready
        self.storage.save_project(project)
        log.info(f"PersistStep → project {name} (video {video_hash})")
        return ctx


# ── Pipeline ──────────────────────────────────────────────────────────────────

class Pipeline:
    """
    Runs a sequence of PipelineStep objects against a PipelineContext.

    Validation is fully delegated to each step — Pipeline has no central checks.
    """

    def __init__(self, steps: list[PipelineStep]):
        self.steps = steps

    def run(self, video_path: Path | str, project_name: str | None = None) -> PipelineContext:
        """Build a fresh context from video_path and run all steps."""
        ctx = PipelineContext(video_path=Path(video_path), project_name=project_name)
        return self._execute(ctx)

    def resume(self, ctx: PipelineContext) -> PipelineContext:
        """
        Run all steps against an existing context.

        Enables cross-pipeline reuse: pass the context output of one pipeline
        into another without re-running expensive steps whose outputs are already
        populated (each step still validates its specific inputs).
        """
        return self._execute(ctx)

    def _execute(self, ctx: PipelineContext) -> PipelineContext:
        for step in self.steps:
            step.check_inputs(ctx)
            ctx = step.run(ctx)
        return ctx


# ── Default pipeline factory ──────────────────────────────────────────────────

def default_pipeline(
    proc_config: ProcessingConfig | None = None,
    seg_config: SegmentationConfig | None = None,
    storage=None,
    config: Settings | None = None,
    include_vlm: bool = False,
    flow_fps: float | None = None,
) -> Pipeline:
    """
    Standard pipeline: downsample → optical flow → preprocess → segment → (persist) → (vlm).

    DownsampleStep always runs first so that:
    - OpticalFlowStep reads the smaller downsampled file.
    - VLMStep and clip extraction have a persistent downsampled file to upload.

    When *storage* is provided DownsampleStep is manifest-aware and skips the
    ffmpeg call if the "downsampled" step is already current.  Without storage
    a temporary directory is used (suitable for tests and in-memory pipelines).

    ``config`` is forwarded to DownsampleStep, PersistStep, and VLMStep for
    manifest step-tracking.

    ``flow_fps`` overrides the optical flow streaming fps. When None, falls back
    to ``config.video.optical_flow.target_fps`` if config is provided.
    """
    pc = proc_config or ProcessingConfig()
    sc = seg_config or SegmentationConfig()

    resolved_flow_fps = flow_fps
    if resolved_flow_fps is None and config is not None:
        resolved_flow_fps = config.video.optical_flow.target_fps

    steps: list[PipelineStep] = [
        DownsampleStep(pc, storage=storage, config=config),
        OpticalFlowStep(pc, flow_fps=resolved_flow_fps),
        PreprocessSignalStep(sc),
        SegmentScenesStep(sc),
    ]
    if storage is not None:
        steps.append(PersistStep(storage, config=config))

    if include_vlm:
        if storage is None or config is None:
            raise ValueError("include_vlm=True requires both storage and config")
        from video.vlm import VLMStep
        steps.append(VLMStep(storage, config))

    return Pipeline(steps)
