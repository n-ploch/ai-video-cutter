from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel

# Default config path, relative to repo root. Callers that need an absolute
# path should resolve it themselves (e.g. Path(__file__).parents[2] / "config/default.yaml").
DEFAULT_CONFIG_PATH = Path("config/default.yaml")


# ── Sub-models ────────────────────────────────────────────────────────────────

class DownsampleConfig(BaseModel):
    target_fps: float | None = None  # None → preserve native fps
    target_width: int = 640
    output_format: str = "mp4"


class OpticalFlowConfig(BaseModel):
    target_fps: float = 4.0          # fps at which frames are streamed for flow computation
    pyr_scale: float = 0.5
    levels: int = 3
    winsize: int = 15
    iterations: int = 3
    poly_n: int = 5
    poly_sigma: float = 1.2


class VideoSegmentationConfig(BaseModel):
    fd_penalty: float = 3.0
    subseg_penalty: float = 2.0
    savgol_window: int = 11
    savgol_poly: int = 2


class VideoConfig(BaseModel):
    hwaccel: str | None = None
    downsample: DownsampleConfig = DownsampleConfig()
    optical_flow: OpticalFlowConfig = OpticalFlowConfig()
    segmentation: VideoSegmentationConfig = VideoSegmentationConfig()


class VlmConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-2.0-flash"
    temperature: float = 0.3
    gemini_api_key: str | None = None  # falls back to GEMINI_API_KEY env var
    request_delay_s: float = 2.0       # rate-limit pause between segment API calls


class AgentLLMConfig(BaseModel):
    provider: str = "mistral"
    model: str = "mistral-large-latest"
    temperature: float = 0.5
    base_url: str | None = None         # required for mistral/vllm
    api_key: str | None = None          # falls back to env var (MISTRAL_API_KEY, OPENAI_API_KEY, etc.)
    extra_headers: dict[str, str] = {}  # for additional auth headers


class StoryboardConfig(BaseModel):
    max_revisions: int = 2
    review_threshold: float = 0.7
    human_in_the_loop: bool = False
    story_writer: AgentLLMConfig = AgentLLMConfig(temperature=0.7)
    narrator: AgentLLMConfig = AgentLLMConfig(temperature=0.3)
    director: AgentLLMConfig = AgentLLMConfig(temperature=0.5)
    judge: AgentLLMConfig = AgentLLMConfig(temperature=0.1)


class EditorConfig(BaseModel):
    model: str = "claude-opus-4-6"
    similarity_threshold: float = 0.8


# ── Top-level Settings ────────────────────────────────────────────────────────

class Settings(BaseModel):
    project_name: str | None = None  # None in default.yaml; set in per-project config.yaml
    video: VideoConfig = VideoConfig()
    vlm: VlmConfig = VlmConfig()
    storyboard: StoryboardConfig = StoryboardConfig()
    editor: EditorConfig = EditorConfig()

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Settings":
        """Load settings from a YAML file. Missing keys fall back to defaults."""
        raw = yaml.safe_load(Path(path).read_text()) or {}
        return cls.model_validate(raw)

    @property
    def config_hash(self) -> str:
        """SHA-256 of the video config section.

        Used to detect when reprocessing is needed: if config_hash differs
        from what was recorded at processing time, the step is stale.
        Only the video section is hashed — VLM/storyboard/editor changes
        do not invalidate optical-flow or segmentation results.
        """
        serialized = json.dumps(
            self.video.model_dump(mode="json"), sort_keys=True
        )
        return hashlib.sha256(serialized.encode()).hexdigest()
