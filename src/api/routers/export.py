"""OTIO export endpoint (runs inline — fast enough not to need a Celery task)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_storage
from api.schemas.requests import ExportRequest
from api.schemas.responses import ExportResponse
from core.storage import ProjectStorage

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{project_name}/export", response_model=ExportResponse)
def export_timeline(
    project_name: str,
    body: ExportRequest = ExportRequest(),
    storage: ProjectStorage = Depends(get_storage),
):
    """Export the project timeline to OpenTimelineIO (.otio).

    Returns a URL to the generated ``.otio`` file served via ``/files/``.
    """
    try:
        storage.get_project(project_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    try:
        import opentimelineio as otio
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="opentimelineio is not installed. Install it to use export.",
        )

    from core.schemas.editor import TimelineOutput
    from editor.tools.otio_export import timeline_to_otio

    project_dir = storage.get_project_path(project_name)
    timeline_dir = project_dir / "timeline"
    export_dir = project_dir / "export_timeline"
    export_dir.mkdir(parents=True, exist_ok=True)

    # Resolve version.
    version = body.version
    if version == "latest":
        latest = timeline_dir / "latest.json"
        if not latest.exists():
            raise HTTPException(status_code=404, detail="No timeline found. Run the editor agent first.")
        json_path = latest.resolve()
        otio_stem = json_path.stem
    else:
        tag = version.lstrip("v")
        json_path = timeline_dir / f"v{tag}.json"
        otio_stem = f"v{tag}"

    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"Timeline version '{version}' not found")

    # Build source_video hash → path map from manifest.
    manifest = storage._load_manifest(project_name)
    video_paths: dict[str, str] = {
        h: entry.get("storage_key") or entry.get("original_path", "")
        for h, entry in manifest.get("videos", {}).items()
    }

    timeline: TimelineOutput = storage.load_json(
        project_name,
        f"timeline/{json_path.name}",
        schema=TimelineOutput,
    )

    otio_path = export_dir / f"{otio_stem}.otio"
    otio_timeline = timeline_to_otio(timeline, video_paths, rate=body.rate)
    otio.adapters.write_to_file(otio_timeline, str(otio_path))

    # Update latest.otio symlink.
    latest_json = timeline_dir / "latest.json"
    if latest_json.exists():
        latest_stem = latest_json.resolve().stem
        latest_target = export_dir / f"{latest_stem}.otio"
        if latest_target.exists():
            latest_otio = export_dir / "latest.otio"
            if latest_otio.is_symlink() or latest_otio.exists():
                latest_otio.unlink()
            latest_otio.symlink_to(latest_target.name)

    otio_key = str(otio_path.relative_to(storage.root))
    otio_url = storage.backend.get_url(otio_key)

    log.info("export_timeline: project=%s → %s", project_name, otio_path)
    return ExportResponse(
        version=otio_stem,
        otio_url=otio_url,
        total_segments=timeline.total_segments,
        total_duration=timeline.total_duration,
    )
