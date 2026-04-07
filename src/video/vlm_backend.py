"""VLM backend abstraction layer.

Decouples the VLM call mechanics (upload, polling, API invocation) from the
pipeline step. Add a new backend by subclassing VLMBackend and registering it
in create_vlm_backend().
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.config import VlmConfig


# ── Abstract base ─────────────────────────────────────────────────────────────

class VLMBackend(ABC):
    """Minimal interface that every VLM backend must implement."""

    @abstractmethod
    def analyze_video(self, video_path: Path, prompt: str) -> str:
        """Upload *video_path*, call the model with *prompt*, return raw text.

        Implementations are responsible for uploading the file, waiting until
        it is ready, calling the model, and returning the raw response text.
        The caller owns cleanup of *video_path* itself (it is never deleted
        here).
        """

    @abstractmethod
    def close(self) -> None:
        """Release any held resources (connections, cached uploads, etc.)."""


# ── Gemini File API backend ───────────────────────────────────────────────────

class GeminiFileAPIBackend(VLMBackend):
    """Backend that uses Google Gemini via the File API for video understanding.

    Parameters
    ----------
    api_key:     Gemini API key. Falls back to ``GEMINI_API_KEY`` env var if None.
    model:       Gemini model ID, e.g. ``"gemini-2.0-flash"``.
    temperature: Sampling temperature (0–1).
    poll_interval_s: Seconds to wait between state-polling attempts.
    poll_max_attempts: Maximum polling attempts before raising RuntimeError.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.3,
        poll_interval_s: float = 2.0,
        poll_max_attempts: int = 30,
    ) -> None:
        try:
            import google.genai as genai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for GeminiFileAPIBackend. "
                "Install it with: pip install google-genai"
            ) from exc

        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Gemini API key not found. Set gemini_api_key in config or "
                "the GEMINI_API_KEY environment variable."
            )

        self._client = genai.Client(api_key=resolved_key)
        self._model = model
        self._temperature = temperature
        self._poll_interval = poll_interval_s
        self._poll_max = poll_max_attempts

    def analyze_video(self, video_path: Path, prompt: str) -> str:
        """Upload video, wait for ACTIVE state, call model, return response text."""
        import google.genai.types as types  # type: ignore[import-untyped]

        uploaded = self._upload_and_wait(video_path)
        try:
            log.info("GeminiBackend: calling %s on %s", self._model, video_path.name)
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part(file_data=types.FileData(file_uri=uploaded.uri)),
                            types.Part(text=prompt),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(temperature=self._temperature),
            )
            log.debug("GeminiBackend: response length=%d chars", len(response.text or ""))
            return response.text
        finally:
            # Best-effort delete; files auto-expire after 48h if this fails.
            try:
                self._client.files.delete(name=uploaded.name)
            except Exception:
                pass

    def close(self) -> None:
        pass  # google-genai client has no explicit teardown

    # ── internals ─────────────────────────────────────────────────────────────

    def _upload_and_wait(self, path: Path):
        """Upload *path* to the Gemini File API and poll until state == ACTIVE."""
        log.info("GeminiBackend: uploading %s", path.name)
        uploaded = self._client.files.upload(file=str(path))
        for attempt in range(self._poll_max):
            file_info = self._client.files.get(name=uploaded.name)
            state = str(file_info.state).upper()
            if "ACTIVE" in state:
                log.debug("GeminiBackend: %s ACTIVE after %d poll(s)", path.name, attempt + 1)
                return file_info
            if "FAILED" in state:
                raise RuntimeError(
                    f"Gemini File API processing failed for {path.name}: "
                    f"state={file_info.state}"
                )
            time.sleep(self._poll_interval)
        raise RuntimeError(
            f"Gemini file {path.name} never reached ACTIVE after "
            f"{self._poll_max * self._poll_interval:.0f}s"
        )


# ── Factory ───────────────────────────────────────────────────────────────────

def create_vlm_backend(config: VlmConfig) -> VLMBackend:
    """Instantiate and return the appropriate VLMBackend for *config.provider*.

    Extend this function when adding new backends (Vertex AI, Anthropic, etc.).
    """
    if config.provider == "gemini":
        return GeminiFileAPIBackend(
            api_key=config.gemini_api_key,
            model=config.model,
            temperature=config.temperature,
        )
    raise ValueError(
        f"Unknown VLM provider: {config.provider!r}. "
        "Supported providers: 'gemini'."
    )
