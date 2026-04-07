"""Celery application and queue configuration."""
from __future__ import annotations

import os

from celery import Celery

app = Celery("vc_worker")

app.conf.update(
    broker_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    result_backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_routes={
        "video.*": {"queue": "video"},
        "vlm.*":   {"queue": "vlm"},
        "agents.*": {"queue": "agents"},
    },
    # Critical for long-running tasks: don't ack until the task is done so a
    # worker crash results in automatic re-delivery.
    task_acks_late=True,
    # Prevent prefetching multiple long tasks on a single worker process.
    worker_prefetch_multiplier=1,
    # Allows GET /api/v1/status/{task_id} to return "STARTED" mid-execution.
    task_track_started=True,
)

# Auto-discover tasks in all worker modules.
app.autodiscover_tasks(["worker.video_tasks", "worker.vlm_tasks", "worker.agent_tasks"])

# Configure logging for the worker process.
from core.logging_config import setup_logging  # noqa: E402
setup_logging()

# Instrument google-genai SDK for Langfuse tracing (no-op if unconfigured).
from core.tracing import setup_langfuse_instrumentation  # noqa: E402
setup_langfuse_instrumentation()
