"""
Drone Video Analysis Pipeline — Stage 1
========================================
Extracts frames, computes embeddings, optical flow stats,
quality metrics, and segments video into scenes via change point detection.

Dependencies:
    pip install opencv-contrib-python numpy torch transformers ruptures scipy pillow tqdm ffmpeg-python

Note on BRISQUE: requires opencv-contrib-python (not just opencv-python).
    If unavailable, the pipeline falls back to sharpness + exposure only.
"""

import cv2
import numpy as np
import json
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Generator

import ffmpeg
import torch
from transformers import AutoModel, AutoProcessor
from scipy.spatial.distance import cosine as cosine_dist
from scipy.signal import find_peaks
import ruptures as rpt
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class FrameMetrics:
    timestamp: float  # seconds
    frame_idx: int
    sharpness: float  # laplacian variance
    mean_brightness: float
    highlight_clip_pct: float  # % pixels > 250
    shadow_clip_pct: float  # % pixels < 5
    brisque_score: Optional[float] = None

@dataclass
class FlowStats:
    timestamp: float
    mean_magnitude: float
    dominant_direction: float  # radians
    coherence: float  # 0-1, how uniform the flow field is

@dataclass
class Scene:
    scene_id: int
    start_time: float
    end_time: float
    duration: float
    avg_sharpness: float
    avg_brightness: float
    avg_brisque: Optional[float]
    avg_flow_magnitude: float
    avg_flow_coherence: float
    quality_score: float  # composite 0-1
    keyframe_timestamps: list = field(default_factory=list)
    # Embedding index range: rows [emb_start, emb_end) in the .npy file
    emb_start: int = 0
    emb_end: int = 0


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------
def stream_frames(
    video_path: str, fps: float = 1.0, width: int = 448
) -> Generator[tuple[np.ndarray, float, float], None, None]:
    """
    Stream frames from a video using FFmpeg with hardware acceleration (VideoToolbox on Mac).
    Yields (frame_rgb, timestamp_seconds, read_time_seconds) one frame at a time —
    only a single frame is held in memory at any point.
    """
    try:
        probe = ffmpeg.probe(video_path)
    except ffmpeg.Error as e:
        raise RuntimeError(
            f"ffprobe failed on {video_path!r}:\n{e.stderr.decode(errors='replace')}"
        ) from e
    video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    if video_stream is None:
        raise ValueError(f"No video stream found in {video_path}")

    orig_w = int(video_stream["width"])
    orig_h = int(video_stream["height"])
    duration = float(probe["format"]["duration"])

    aspect_ratio = orig_h / orig_w
    target_height = int(width * aspect_ratio)
    if target_height % 2 != 0:
        target_height += 1

    frame_bytes = width * target_height * 3

    log.info(
        f"Streaming {video_path}: {orig_w}x{orig_h} → {width}x{target_height} "
        f"@ {fps}fps, duration={duration:.1f}s, ~{int(duration * fps)} frames"
    )

    process = (
        ffmpeg
        .input(video_path, hwaccel="videotoolbox")
        .filter("fps", fps=fps)
        .filter("scale", width, target_height)
        .output("pipe:", format="rawvideo", pix_fmt="rgb24")
        .run_async(pipe_stdout=True, quiet=True)
    )

    frame_idx = 1
    try:
        while True:
            start_read = time.time()
            raw_data = process.stdout.read(frame_bytes)
            read_time = time.time() - start_read

            if len(raw_data) != frame_bytes:
                break

            timestamp = frame_idx / fps
            yield (
                np.frombuffer(raw_data, dtype="uint8").reshape((target_height, width, 3)).copy(),
                timestamp,
                read_time,
            )
            frame_idx += 1
    finally:
        process.stdout.close()
        process.wait()


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------
class QualityAnalyzer:
    """Computes per-frame technical quality metrics."""

    def __init__(self):
        self.has_brisque = False
        try:
            # Test if BRISQUE is available (needs opencv-contrib)
            cv2.quality.QualityBRISQUE_create(
                cv2.samples.findFile("brisque_model_live.yml"),
                cv2.samples.findFile("brisque_range_live.yml"),
            )
            self.has_brisque = True
        except Exception:
            log.warning(
                "BRISQUE unavailable (need opencv-contrib-python + model files). "
                "Falling back to sharpness/exposure only."
            )

    def compute(self, timestamp: float, frame_idx: int, frame_bgr: np.ndarray) -> FrameMetrics:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # Sharpness: variance of Laplacian
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Exposure stats
        mean_brightness = float(gray.mean())
        total_pixels = gray.size
        highlight_clip = float((gray > 250).sum() / total_pixels * 100)
        shadow_clip = float((gray < 5).sum() / total_pixels * 100)

        # BRISQUE (if available)
        brisque = None
        if self.has_brisque:
            try:
                score = cv2.quality.QualityBRISQUE_compute(
                    frame_bgr,
                    cv2.samples.findFile("brisque_model_live.yml"),
                    cv2.samples.findFile("brisque_range_live.yml"),
                )
                brisque = float(score[0])
            except Exception:
                pass

        return FrameMetrics(
            timestamp=timestamp,
            frame_idx=frame_idx,
            sharpness=sharpness,
            mean_brightness=mean_brightness,
            highlight_clip_pct=highlight_clip,
            shadow_clip_pct=shadow_clip,
            brisque_score=brisque,
        )


# ---------------------------------------------------------------------------
# Optical flow
# ---------------------------------------------------------------------------
class OpticalFlowAnalyzer:
    """Computes Farnebäck optical flow statistics between consecutive frames."""

    def __init__(self, resize_width: int = 640):
        self.resize_width = resize_width

    def _resize(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        scale = self.resize_width / w
        new_h = int(h * scale)
        resized = cv2.resize(frame_bgr, (self.resize_width, new_h))
        return cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    def compute_between(self, frame_a: np.ndarray, frame_b: np.ndarray, ts: float) -> FlowStats:
        gray_a = self._resize(frame_a)
        gray_b = self._resize(frame_b)

        flow = cv2.calcOpticalFlowFarneback(
            gray_a, gray_b, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
        )

        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])

        mean_mag = float(mag.mean())

        # Dominant direction: circular mean via vector averaging
        dx_mean = float(np.cos(ang).mean())
        dy_mean = float(np.sin(ang).mean())
        dominant_dir = float(np.arctan2(dy_mean, dx_mean))

        # Coherence: length of mean direction vector (1 = all flow in same dir)
        coherence = float(np.sqrt(dx_mean ** 2 + dy_mean ** 2))

        return FlowStats(
            timestamp=ts,
            mean_magnitude=mean_mag,
            dominant_direction=dominant_dir,
            coherence=coherence,
        )


# ---------------------------------------------------------------------------
# Embedding extraction
# ---------------------------------------------------------------------------
class VisionModelWrapper:
    """Unified interface for SigLIP and CLIP image/text encoding."""

    MODELS = {
        "siglip": "google/siglip-so400m-patch14-384",
        "clip":   "openai/clip-vit-base-patch32",
    }

    def __init__(self, model_type: str = "siglip", model_name: str = None):
        if model_type not in self.MODELS:
            raise ValueError(f"model_type must be one of {list(self.MODELS)}, got {model_type!r}")

        self.model_type = model_type
        self.device = (
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )
        name = model_name or self.MODELS[model_type]
        log.info(f"Loading {model_type.upper()} ({name}) on {self.device}")

        self.processor = AutoProcessor.from_pretrained(name, use_fast=True)
        self.model = AutoModel.from_pretrained(name).to(self.device).eval()

    @torch.no_grad()
    def encode_images(self, frames_rgb: list[np.ndarray]) -> np.ndarray:
        """Returns (N, D) array of L2-normalised image embeddings. Expects RGB frames."""
        from PIL import Image
        inputs = self.processor(
            images=[Image.fromarray(f) for f in frames_rgb],
            return_tensors="pt",
        ).to(self.device)
        output = self.model.get_image_features(**inputs)

        # Extract tensor from model output (handle both old and new API)
        if isinstance(output, torch.Tensor):
            features = output
        elif hasattr(output, 'pooler_output') and output.pooler_output is not None:
            features = output.pooler_output
        elif hasattr(output, 'last_hidden_state'):
            features = output.last_hidden_state[:, 0]  # Use [CLS] token
        else:
            # Fallback for any other structure
            features = output[0] if isinstance(output, (tuple, list)) else output

        features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features.cpu().numpy()

    @torch.no_grad()
    def encode_text(self, texts: list[str]) -> np.ndarray:
        """Returns (N, D) array of L2-normalised text embeddings."""
        inputs = self.processor(text=texts, return_tensors="pt", padding=True).to(self.device)
        features = self.model.get_text_features(**inputs)
        features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features.cpu().numpy()


# ---------------------------------------------------------------------------
# Scene segmentation
# ---------------------------------------------------------------------------
class SceneSegmenter:
    """Detects scene boundaries using change point detection on embeddings."""

    def __init__(self, method: str = "sliding_window", window_size: int = 10):
        """
        method: "sliding_window" or "ruptures"
        window_size: seconds (used as number of frames at 1fps)
        """
        self.method = method
        self.window_size = window_size

    def detect_boundaries(
        self,
        embeddings: np.ndarray,
        timestamps: np.ndarray,
        penalty: float = 1.0,
        peak_prominence: float = 0.05,
    ) -> list[float]:
        """Returns list of boundary timestamps."""

        if self.method == "ruptures":
            return self._ruptures_method(embeddings, timestamps, penalty)
        else:
            return self._sliding_window_method(embeddings, timestamps, peak_prominence)

    def _sliding_window_method(
        self, embeddings: np.ndarray, timestamps: np.ndarray, prominence: float
    ) -> list[float]:
        n = len(embeddings)
        w = self.window_size
        scores = np.zeros(n)

        for t in range(w, n - w):
            left_mean = embeddings[t - w : t].mean(axis=0)
            right_mean = embeddings[t : t + w].mean(axis=0)
            scores[t] = cosine_dist(left_mean, right_mean)

        # Find peaks in the score signal
        peaks, properties = find_peaks(scores, prominence=prominence, distance=w)
        boundaries = timestamps[peaks].tolist()

        log.info(
            f"Sliding window found {len(boundaries)} boundaries "
            f"(prominence={prominence}, window={w})"
        )
        return boundaries

    def _ruptures_method(
        self, embeddings: np.ndarray, timestamps: np.ndarray, penalty: float
    ) -> list[float]:
        # PCA down if high-dimensional for speed
        if False:#embeddings.shape[1] > 100:
            from sklearn.decomposition import PCA
            pca = PCA(n_components=50)
            reduced = pca.fit_transform(embeddings)
            explained = pca.explained_variance_ratio_.sum()
            log.info(f"PCA: {embeddings.shape[1]}d -> 50d ({explained:.1%} variance retained)")
        else:
            reduced = embeddings

        algo = rpt.KernelCPD(kernel="rbf", min_size=self.window_size).fit(reduced)
        breakpoints = algo.predict(pen=penalty)
        # ruptures returns indices (last index = len), drop the final one
        bp_indices = [b for b in breakpoints if b < len(timestamps)]
        boundaries = timestamps[bp_indices].tolist()

        log.info(f"Ruptures found {len(boundaries)} boundaries (penalty={penalty})")
        return boundaries


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
class DronePipeline:
    """Orchestrates the full Stage 1 analysis pipeline."""

    def __init__(
        self,
        embedding_fps: float = 1.0,
        flow_fps: float = 4.0,
        segmentation_method: str = "sliding_window",
        window_size: int = 10,
        model_type: str = "siglip",
        model_name: str = None,
        emb_width: int = 448,
        flow_width: int = 640,
        embed_batch_size: int = 16,
    ):
        self.embedding_fps = embedding_fps
        self.flow_fps = flow_fps
        self.emb_width = emb_width
        self.flow_width = flow_width
        self.embed_batch_size = embed_batch_size
        self.segmenter = SceneSegmenter(method=segmentation_method, window_size=window_size)
        self.quality = QualityAnalyzer()
        self.flow = OpticalFlowAnalyzer()
        self.embeddings_extractor = VisionModelWrapper(model_type=model_type, model_name=model_name)

    def analyze(self, video_path: str, output_path: str = None) -> dict:
        """Run full pipeline on a video file. Returns results dict."""

        # --- Pass 1: Embeddings + quality (stream at embedding_fps) ---
        # Frames are never all in memory at once: we buffer at most `embed_batch_size`
        # frames for the embedding model, then discard them.
        log.info("=== Pass 1: Embeddings + quality metrics ===")
        timestamps_list: list[float] = []
        quality_metrics: list[FrameMetrics] = []
        all_embeddings: list[np.ndarray] = []
        frame_buffer: list[np.ndarray] = []  # RGB frames awaiting embedding

        for frame_rgb, ts, _ in tqdm(
            stream_frames(video_path, fps=self.embedding_fps, width=self.emb_width),
            desc=f"Emb+Quality @{self.embedding_fps}fps",
        ):
            idx = len(timestamps_list)
            timestamps_list.append(ts)

            # Quality metrics operate on BGR
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            quality_metrics.append(self.quality.compute(ts, idx, frame_bgr))

            # Buffer for batch embedding
            frame_buffer.append(frame_rgb)
            if len(frame_buffer) >= self.embed_batch_size:
                all_embeddings.append(self.embeddings_extractor.encode_images(frame_buffer))
                frame_buffer.clear()

        # Flush remaining frames
        if frame_buffer:
            all_embeddings.append(self.embeddings_extractor.encode_images(frame_buffer))
            frame_buffer.clear()

        timestamps = np.array(timestamps_list)
        embeddings = np.concatenate(all_embeddings, axis=0) if all_embeddings else np.empty((0, 0))

        # --- Pass 2: Optical flow (stream at flow_fps) ---
        # Only two frames are ever in memory at the same time.
        log.info("=== Pass 2: Optical flow ===")
        flow_stats: list[FlowStats] = []
        prev_frame_bgr: Optional[np.ndarray] = None

        for frame_rgb, ts, _ in tqdm(
            stream_frames(video_path, fps=self.flow_fps, width=self.flow_width),
            desc=f"Optical flow @{self.flow_fps}fps",
        ):
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            if prev_frame_bgr is not None:
                flow_stats.append(self.flow.compute_between(prev_frame_bgr, frame_bgr, ts))
            prev_frame_bgr = frame_bgr

        # --- 3. Scene segmentation ---
        log.info("=== Detecting scene boundaries ===")
        boundaries = self.segmenter.detect_boundaries(embeddings, timestamps)

        all_boundaries = [0.0] + boundaries + [timestamps[-1]]

        # --- 4. Build scene objects ---
        scenes = self._build_scenes(all_boundaries, quality_metrics, flow_stats, embeddings, timestamps)

        # --- 5. Assemble output ---
        result = {
            "video_path": str(video_path),
            "duration": float(timestamps[-1]),
            "num_scenes": len(scenes),
            "scenes": [asdict(s) for s in scenes],
            "frame_metrics": [asdict(m) for m in quality_metrics],
            "flow_stats": [asdict(f) for f in flow_stats],
            "boundaries": all_boundaries,
        }

        # Optionally save
        if output_path is None:
            output_path = str(Path(video_path).with_suffix(".analysis.json"))
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        log.info(f"Results saved to {output_path}")

        # Save embeddings + timestamp index together
        emb_path = str(Path(video_path).with_suffix(".embeddings.npz"))
        np.savez(emb_path, embeddings=embeddings, timestamps=timestamps)
        log.info(f"Embeddings + timestamps saved to {emb_path}")

        return result

    def _build_scenes(
        self,
        boundaries: list[float],
        quality_metrics: list[FrameMetrics],
        flow_stats: list[FlowStats],
        embeddings: np.ndarray,
        timestamps: np.ndarray,
    ) -> list[Scene]:
        scenes = []

        for i in range(len(boundaries) - 1):
            start, end = boundaries[i], boundaries[i + 1]

            # Gather metrics within this scene
            scene_quality = [m for m in quality_metrics if start <= m.timestamp < end]
            scene_flow = [f for f in flow_stats if start <= f.timestamp < end]

            if not scene_quality:
                continue

            avg_sharp = np.mean([m.sharpness for m in scene_quality])
            avg_bright = np.mean([m.mean_brightness for m in scene_quality])

            brisque_scores = [m.brisque_score for m in scene_quality if m.brisque_score is not None]
            avg_brisque = float(np.mean(brisque_scores)) if brisque_scores else None

            avg_flow_mag = float(np.mean([f.mean_magnitude for f in scene_flow])) if scene_flow else 0.0
            avg_flow_coh = float(np.mean([f.coherence for f in scene_flow])) if scene_flow else 0.0

            # --- Composite quality score (0-1) ---
            quality_score = self._composite_quality(
                avg_sharp, avg_bright, avg_brisque, avg_flow_coh,
                scene_quality,
            )

            # --- Keyframe selection: most diverse frames via embedding spread ---
            scene_mask = (timestamps >= start) & (timestamps < end)
            scene_indices = np.where(scene_mask)[0]
            scene_embs = embeddings[scene_mask]
            scene_ts = timestamps[scene_mask]
            keyframe_ts = self._select_keyframes(scene_embs, scene_ts, max_keyframes=3)

            # Embedding row range for this scene
            emb_start = int(scene_indices[0]) if len(scene_indices) > 0 else 0
            emb_end = int(scene_indices[-1] + 1) if len(scene_indices) > 0 else 0

            scenes.append(Scene(
                scene_id=i,
                start_time=round(start, 2),
                end_time=round(end, 2),
                duration=round(end - start, 2),
                avg_sharpness=round(float(avg_sharp), 2),
                avg_brightness=round(float(avg_bright), 2),
                avg_brisque=round(avg_brisque, 2) if avg_brisque else None,
                avg_flow_magnitude=round(avg_flow_mag, 4),
                avg_flow_coherence=round(avg_flow_coh, 4),
                quality_score=round(quality_score, 3),
                keyframe_timestamps=[round(t, 2) for t in keyframe_ts],
                emb_start=emb_start,
                emb_end=emb_end,
            ))

        # Sort by quality score descending
        scenes.sort(key=lambda s: s.quality_score, reverse=True)
        log.info(f"Built {len(scenes)} scenes")
        return scenes

    def _composite_quality(
        self,
        sharpness: float,
        brightness: float,
        brisque: Optional[float],
        flow_coherence: float,
        frame_metrics: list[FrameMetrics],
    ) -> float:
        """
        Compute a 0-1 composite quality score.
        This is intentionally simple — tune weights for your footage.
        """
        scores = []

        # Sharpness: log-scale, higher is better.
        # Typical range for drone footage: 10 (blurry) to 2000+ (very sharp)
        sharp_score = min(np.log1p(sharpness) / np.log1p(1500), 1.0)
        scores.append(("sharpness", sharp_score, 0.3))

        # Exposure: penalize extreme brightness and clipping
        bright_score = 1.0 - abs(brightness - 127) / 127  # best at ~127
        avg_clip = np.mean(
            [m.highlight_clip_pct + m.shadow_clip_pct for m in frame_metrics]
        )
        clip_penalty = min(avg_clip / 10.0, 1.0)  # 10%+ clipping = 0
        exposure_score = max(bright_score - clip_penalty, 0.0)
        scores.append(("exposure", exposure_score, 0.2))

        # Flow coherence: higher = smoother camera motion
        scores.append(("stability", flow_coherence, 0.2))

        # BRISQUE: lower is better, typical range 0-100
        if brisque is not None:
            brisque_norm = max(1.0 - brisque / 80.0, 0.0)
            scores.append(("brisque", brisque_norm, 0.3))
        else:
            # Redistribute BRISQUE weight to sharpness if unavailable
            scores[0] = ("sharpness", sharp_score, 0.5)

        # Weighted sum
        total_weight = sum(w for _, _, w in scores)
        composite = sum(s * w for _, s, w in scores) / total_weight
        return float(np.clip(composite, 0, 1))

    def _select_keyframes(
        self, embeddings: np.ndarray, timestamps: np.ndarray, max_keyframes: int = 3
    ) -> list[float]:
        """Select diverse keyframes using greedy max-min distance."""
        if len(embeddings) <= max_keyframes:
            return timestamps.tolist()

        n = len(embeddings)
        selected = [n // 2]  # start with middle frame

        for _ in range(max_keyframes - 1):
            best_idx, best_min_dist = -1, -1
            for candidate in range(n):
                if candidate in selected:
                    continue
                min_dist = min(
                    1 - np.dot(embeddings[candidate], embeddings[s])
                    for s in selected
                )
                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_idx = candidate
            selected.append(best_idx)

        return sorted([float(timestamps[i]) for i in selected])


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def _print_summary(result: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"Video: {result['video_path']}")
    print(f"Duration: {result['duration']:.1f}s")
    print(f"Scenes found: {result['num_scenes']}")
    print(f"{'=' * 60}")
    for s in result["scenes"]:
        print(
            f"  Scene {s['scene_id']:2d} | "
            f"{s['start_time']:6.1f}s - {s['end_time']:6.1f}s | "
            f"duration: {s['duration']:5.1f}s | "
            f"quality: {s['quality_score']:.3f} | "
            f"keyframes: {s['keyframe_timestamps']}"
        )


def _is_already_analyzed(video_path: Path) -> bool:
    """Return True if both output files for this video already exist."""
    return (
        video_path.with_suffix(".analysis.json").exists()
        and video_path.with_suffix(".embeddings.npz").exists()
    )


def _collect_videos(target: str) -> list[Path]:
    """
    If target is a directory, return all .mp4 files inside it (non-recursive).
    If target is a file, return it as a single-element list.
    """
    p = Path(target)
    if p.is_dir():
        return sorted(f for f in p.iterdir() if f.suffix.lower() == ".mp4")
    return [p]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Drone Video Analysis — Stage 1")
    parser.add_argument(
        "video",
        help="Path to a single video file, or a directory to scan for .mp4 files",
    )
    parser.add_argument("--emb-fps", type=float, default=1.0, help="FPS for embedding extraction")
    parser.add_argument("--flow-fps", type=float, default=4.0, help="FPS for optical flow")
    parser.add_argument("--method", choices=["sliding_window", "ruptures"], default="sliding_window")
    parser.add_argument("--window", type=int, default=10, help="Window size for change detection (seconds)")
    parser.add_argument("--penalty", type=float, default=1.0, help="Penalty for ruptures method")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path (single-file mode only)")
    parser.add_argument("--model-type", choices=["siglip", "clip"], default="siglip")
    parser.add_argument("--model-name", type=str, default=None, help="Override default HuggingFace model name")
    parser.add_argument("--emb-width", type=int, default=448, help="Frame width for embedding pass")
    parser.add_argument("--flow-width", type=int, default=640, help="Frame width for optical flow pass")
    parser.add_argument("--batch-size", type=int, default=16, help="Embedding batch size")
    parser.add_argument("--reanalyze", action="store_true", help="Re-run even if output files already exist")
    args = parser.parse_args()

    videos = _collect_videos(args.video)
    if not videos:
        log.error(f"No .mp4 files found in {args.video!r}")
        raise SystemExit(1)

    # In batch mode, --output is ignored
    batch_mode = Path(args.video).is_dir()
    if batch_mode and args.output:
        log.warning("--output is ignored in directory mode; outputs are written next to each video.")

    # Filter out already-analyzed videos unless --reanalyze is set
    pending = [v for v in videos if args.reanalyze or not _is_already_analyzed(v)]
    skipped = len(videos) - len(pending)

    if batch_mode:
        log.info(f"Found {len(videos)} video(s) — {skipped} already analyzed, {len(pending)} to process.")

    if not pending:
        log.info("Nothing to do.")
        raise SystemExit(0)

    pipeline = DronePipeline(
        embedding_fps=args.emb_fps,
        flow_fps=args.flow_fps,
        segmentation_method=args.method,
        window_size=args.window,
        model_type=args.model_type,
        model_name=args.model_name,
        emb_width=args.emb_width,
        flow_width=args.flow_width,
        embed_batch_size=args.batch_size,
    )

    for i, video_path in enumerate(pending, 1):
        if batch_mode:
            log.info(f"[{i}/{len(pending)}] Processing {video_path.name}")
        output_path = None if batch_mode else args.output
        result = pipeline.analyze(str(video_path), output_path=output_path)
        _print_summary(result)