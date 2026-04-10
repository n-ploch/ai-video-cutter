from __future__ import annotations

import contextlib
import hashlib
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TypeVar

from pydantic import BaseModel

from core.project import Project
from core.schemas.video import VideoFile


# ── Storage backend ABC ───────────────────────────────────────────────────────

class StorageBackend(ABC):
    """Abstract blob-storage backend.

    Keys are forward-slash path strings relative to the storage root,
    e.g. ``"my-project/videos/abc123/downsampled.mp4"``.

    ``LocalBackend`` (``storage_local.py``) is the concrete implementation
    for single-machine use.  A future ``S3Backend`` can implement the same
    interface to enable cloud deployment without touching workflow code.
    """

    @abstractmethod
    def read_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def write_bytes(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @contextlib.contextmanager
    @abstractmethod
    def local_path(self, key: str) -> Iterator[Path]:
        """Yield a real local ``Path`` for the given key.

        ``LocalBackend``: yields the on-disk path directly (no copy).
        ``S3Backend``: downloads to a temp file, yields it, re-uploads on
        exit if the file was modified.

        Workers use this to hand paths to ffmpeg, OpenCV, etc.
        """
        ...  # pragma: no cover

    @abstractmethod
    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a URL usable by the UI.

        ``LocalBackend``: returns ``/files/<key>`` (served by FastAPI
        StaticFiles).  ``S3Backend``: returns a pre-signed URL.
        """
        ...

T = TypeVar("T", bound=BaseModel)

_SUBFOLDERS = ("videos", "analysis", "storyboard", "timeline")

# Processing steps tracked in the manifest.
PROCESSING_STEPS = ("downsampled", "optical_flow", "segmented", "described")


# ── Video hashing ─────────────────────────────────────────────────────────────

def hash_video_file(path: Path) -> str:
    """Fast content-hash using first 64 KB + file size.

    Avoids reading the full file for large videos while still being unique
    enough for practical deduplication. Returns a 16-char hex prefix.
    """
    chunk = 64 * 1024
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(chunk))
    h.update(str(Path(path).stat().st_size).encode())
    return h.hexdigest()[:16]


# ── Manifest helpers ──────────────────────────────────────────────────────────

def _empty_video_entry(path: Path, video_hash: str, storage_key: str | None = None) -> dict:
    return {
        "original_path": str(path.resolve()),
        "storage_key": storage_key,   # backend-relative key; None for CLI-added videos
        "filename": path.name,
        "hash": video_hash,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "processing": {step: None for step in PROCESSING_STEPS},
        "config_hash": None,
    }


# ── Storage ───────────────────────────────────────────────────────────────────

class ProjectStorage:
    """Local filesystem project storage.

    Projects are stored under ``root/{project_name}/``.  Video files are
    content-addressed by a fast hash of the first 64 KB + file size, enabling
    incremental processing and deduplication.

    The interface is deliberately abstract: a future ``GCSProjectStorage`` can
    implement the same public methods without consumers needing to change.
    """

    def __init__(
        self,
        root: Path = Path("data/projects"),
        default_config: Path = Path("config/default.yaml"),
        backend: StorageBackend | None = None,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._default_config = Path(default_config)
        if backend is None:
            from core.storage_local import LocalBackend
            self.backend: StorageBackend = LocalBackend(self.root)
        else:
            self.backend = backend

    # ── Project lifecycle ─────────────────────────────────────────────────────

    def create_project(self, name: str, video_paths: list[Path]) -> Project:
        """Create a project folder, hash videos, write manifest and project.json."""
        from video.ingest import probe_video

        project_dir = self._project_dir(name)
        for subfolder in _SUBFOLDERS:
            (project_dir / subfolder).mkdir(parents=True, exist_ok=True)

        # Copy default config into project folder and inject project_name.
        if self._default_config.exists():
            import yaml
            raw = yaml.safe_load(self._default_config.read_text()) or {}
            raw["project_name"] = name
            (project_dir / "config.yaml").write_text(
                yaml.dump(raw, default_flow_style=False, sort_keys=False)
            )

        # Probe videos and build initial manifest.
        video_files: list[VideoFile] = []
        manifest: dict[str, Any] = {"videos": {}}
        for vp in video_paths:
            vp = Path(vp)
            video_hash = hash_video_file(vp)
            video_files.append(probe_video(vp))
            manifest["videos"][video_hash] = _empty_video_entry(vp, video_hash)

        self._write_json(project_dir / "videos" / "manifest.json", manifest)

        project = Project(name=name, video_files=video_files)
        self._write_json(project_dir / "project.json", project.model_dump(mode="json"))
        return project

    def get_project(self, name: str) -> Project:
        """Load a project by name."""
        data = self._read_json(self._project_dir(name) / "project.json")
        return Project.model_validate(data)

    def save_project(self, project: Project) -> None:
        self._write_json(
            self._project_dir(project.name) / "project.json",
            project.model_dump(mode="json"),
        )

    def list_projects(self) -> list[Project]:
        projects: list[Project] = []
        for path in sorted(self.root.iterdir()):
            manifest = path / "project.json"
            if manifest.exists():
                try:
                    projects.append(Project.model_validate(self._read_json(manifest)))
                except Exception:
                    pass
        return projects

    # ── Video management ──────────────────────────────────────────────────────

    def add_video(self, project_name: str, video_path: Path) -> str:
        """Hash video_path, add to manifest if not already present.

        Returns the video hash. Safe to call repeatedly — duplicate hashes
        are silently skipped.
        """
        video_path = Path(video_path)
        video_hash = hash_video_file(video_path)
        manifest = self._load_manifest(project_name)
        if video_hash not in manifest["videos"]:
            manifest["videos"][video_hash] = _empty_video_entry(video_path, video_hash)
            (self._project_dir(project_name) / "videos" / video_hash).mkdir(
                parents=True, exist_ok=True
            )
            self._save_manifest(project_name, manifest)
        return video_hash

    def is_step_current(
        self,
        project_name: str,
        video_hash: str,
        step: str,
        config: Any,  # Settings — avoid circular import
    ) -> bool:
        """Return True if ``step`` has been completed with the current config_hash."""
        manifest = self._load_manifest(project_name)
        entry = manifest["videos"].get(video_hash)
        if entry is None:
            return False
        if entry["processing"].get(step) is None:
            return False
        return entry.get("config_hash") == config.config_hash

    def mark_step_complete(
        self,
        project_name: str,
        video_hash: str,
        step: str,
        config: Any,  # Settings
    ) -> None:
        """Record that ``step`` completed at the current time with the current config_hash."""
        manifest = self._load_manifest(project_name)
        entry = manifest["videos"].setdefault(video_hash, {})
        entry.setdefault("processing", {})
        entry["processing"][step] = datetime.now(timezone.utc).isoformat()
        entry["config_hash"] = config.config_hash
        self._save_manifest(project_name, manifest)

    # ── Data I/O ──────────────────────────────────────────────────────────────

    def save_json(
        self,
        project_name: str,
        path: str,
        data: BaseModel | list | dict,
    ) -> Path:
        """Persist data at ``root/{project_name}/{path}``.

        ``path`` is a forward-slash relative path within the project directory,
        e.g. ``"analysis/combined.json"`` or ``"videos/abc123/flow/metrics.json"``.
        """
        dest = self._project_dir(project_name) / path
        if isinstance(data, BaseModel):
            payload = data.model_dump(mode="json")
        elif isinstance(data, list):
            payload = [
                item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                for item in data
            ]
        else:
            payload = data
        self._write_json(dest, payload)
        return dest

    def load_json(
        self,
        project_name: str,
        path: str,
        schema: type[T] | None = None,
    ) -> Any:
        """Load data from ``root/{project_name}/{path}``.

        If ``schema`` is provided, validates against a Pydantic model (single
        object or list of objects).
        """
        raw = self._read_json(self._project_dir(project_name) / path)
        if schema is not None:
            if isinstance(raw, list):
                return [schema.model_validate(item) for item in raw]
            return schema.model_validate(raw)
        return raw

    # ── Versioned outputs ─────────────────────────────────────────────────────

    def list_versioned(self, project_name: str, category: str) -> list[dict]:
        """Return metadata for all versioned files under ``{category}/``.

        Each entry is a dict with ``version`` (int) and ``created_at`` (ISO
        timestamp derived from the file's mtime).  Results are sorted ascending
        by version number.  Returns an empty list if the directory doesn't exist
        or contains no versioned files.
        """
        category_dir = self._project_dir(project_name) / category
        if not category_dir.exists():
            return []
        entries = []
        for f in category_dir.iterdir():
            m = re.fullmatch(r"v(\d+)\.json", f.name)
            if m:
                mtime = f.stat().st_mtime
                entries.append({
                    "version": int(m.group(1)),
                    "created_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                })
        return sorted(entries, key=lambda x: x["version"])

    def save_versioned(
        self,
        project_name: str,
        category: str,
        data: BaseModel,
    ) -> int:
        """Save ``data`` as the next version under ``{category}/``.

        Files are named ``v1.json``, ``v2.json``, etc. A ``latest.json``
        symlink is updated to point to the new version.

        Returns the version number written.
        """
        category_dir = self._project_dir(project_name) / category
        category_dir.mkdir(parents=True, exist_ok=True)

        existing = [
            int(m.group(1))
            for f in category_dir.iterdir()
            if (m := re.fullmatch(r"v(\d+)\.json", f.name))
        ]
        version = max(existing, default=0) + 1

        target = category_dir / f"v{version}.json"
        self._write_json(target, data.model_dump(mode="json"))

        symlink = category_dir / "latest.json"
        if symlink.is_symlink() or symlink.exists():
            symlink.unlink()
        symlink.symlink_to(target.name)

        return version

    # ── Paths ─────────────────────────────────────────────────────────────────

    def get_project_path(self, project_name: str) -> Path:
        return self._project_dir(project_name)

    # ── Manifest internals ────────────────────────────────────────────────────

    def _load_manifest(self, project_name: str) -> dict:
        path = self._project_dir(project_name) / "videos" / "manifest.json"
        if not path.exists():
            return {"videos": {}}
        return self._read_json(path)

    def _save_manifest(self, project_name: str, manifest: dict) -> None:
        path = self._project_dir(project_name) / "videos" / "manifest.json"
        self._write_json(path, manifest)

    # ── Filesystem primitives ─────────────────────────────────────────────────

    def _project_dir(self, project_name: str) -> Path:
        return self.root / project_name

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))

    @staticmethod
    def _read_json(path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"No such file: {path}")
        return json.loads(path.read_text())
