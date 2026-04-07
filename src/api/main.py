"""FastAPI application factory."""
from __future__ import annotations

import logging
from pathlib import Path

from core.logging_config import setup_logging

setup_logging()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.deps import get_app_settings
from api.routers import editor, export, projects, storyboard, status, videos

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Video Cutter API",
        version="0.1.0",
        description="REST API for the AI video cutter workflows.",
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
    app.include_router(videos.router,   prefix="/api/v1/projects", tags=["videos"])
    app.include_router(storyboard.router, prefix="/api/v1/projects", tags=["storyboard"])
    app.include_router(editor.router,   prefix="/api/v1/projects", tags=["editor"])
    app.include_router(export.router,   prefix="/api/v1/projects", tags=["export"])
    app.include_router(status.router,   prefix="/api/v1",          tags=["status"])

    # ── Serve project storage files (local backend only) ──────────────────────
    app_settings = get_app_settings()
    if app_settings.storage_backend == "local":
        storage_root = Path(app_settings.storage_root)
        storage_root.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/files",
            StaticFiles(directory=str(storage_root), check_dir=False),
            name="files",
        )
        log.info("Serving storage files from %s at /files", storage_root)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


# Allow running directly: uvicorn api.main:app
app = create_app()
