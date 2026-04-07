from __future__ import annotations

import os


def setup_langfuse_instrumentation() -> None:
    """Instrument the google-genai SDK with OpenTelemetry via Langfuse.

    Must be called once at worker/process startup (before any google.genai calls).
    No-ops when Langfuse credentials are not configured.
    """
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return
    try:
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor  # type: ignore[import]
        GoogleGenAIInstrumentor().instrument()
    except Exception:
        pass


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
    return CallbackHandler()


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
