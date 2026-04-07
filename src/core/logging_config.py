from __future__ import annotations

import logging
import os

_NOISY_LIBS = [
    "httpx",
    "httpcore",
    "anthropic",
    "openai",
    "langchain",
    "langchain_core",
    "google",
    "celery.app.trace",
]


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger for the application.

    Level is resolved from (in order):
    1. The ``level`` argument
    2. The ``LOG_LEVEL`` environment variable
    3. ``INFO`` as a fallback

    Third-party libraries that produce excessive output at INFO are clamped to
    WARNING so application logs remain readable.
    """
    resolved = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    numeric = getattr(logging, resolved, logging.INFO)

    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    for lib in _NOISY_LIBS:
        logging.getLogger(lib).setLevel(logging.WARNING)
