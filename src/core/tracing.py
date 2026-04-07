from __future__ import annotations

import os


def get_langfuse_handler(session_id: str, tags: list[str] | None = None):
    """Return a Langfuse CallbackHandler if credentials are configured, else None.

    The handler is passed via ``config["callbacks"]`` to LangGraph's
    ``compiled.invoke()`` and propagates automatically to every node and nested
    LLM call inside the graph.

    Returns None (and never raises) when LANGFUSE_PUBLIC_KEY or
    LANGFUSE_SECRET_KEY are not set, so tracing is fully opt-in.
    """
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return None
    from langfuse.langchain import CallbackHandler  # type: ignore[import]
    return CallbackHandler(session_id=session_id, tags=tags or [])


def flush_langfuse() -> None:
    """Flush pending Langfuse spans to the backend.

    Call at the end of short-lived processes (CLI runs, Celery tasks) to ensure
    buffered telemetry is exported before the process exits or the worker
    recycles.  Safe to call even when Langfuse is not configured.
    """
    try:
        from langfuse import get_client  # type: ignore[import]
        get_client().flush()
    except Exception:
        pass
