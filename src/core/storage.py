from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar, overload

from pydantic import BaseModel

from core.project import Project
from core.schemas.video import VideoFile

T = TypeVar("T", bound=BaseModel)

_SUBFOLDERS = ("sources", "analysis", "storyboard", "timeline")


class ProjectStorage:
    def __init__(self, root: Path = Path("data/projects")):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Project lifecycle ────────────────────────────────────────────────────

    def create_project(self, name: str, video_paths: list[Path]) -> Project:
        from video.ingest import probe_video

        video_files = [probe_video(p) for p in video_paths]
        project = Project(name=name, video_files=video_files)
        project_dir = self._project_dir(project.id)
        for subfolder in _SUBFOLDERS:
            (project_dir / subfolder).mkdir(parents=True, exist_ok=True)

        # Copy source video references into sources/ (stores metadata, not the file)
        self._write_json(project_dir / "project.json", project.model_dump(mode="json"))
        return project

    def get_project(self, project_id: str) -> Project:
        data = self._read_json(self._project_dir(project_id) / "project.json")
        return Project.model_validate(data)

    def save_project(self, project: Project) -> None:
        self._write_json(
            self._project_dir(project.id) / "project.json",
            project.model_dump(mode="json"),
        )

    def list_projects(self) -> list[Project]:
        projects = []
        for path in sorted(self.root.iterdir()):
            manifest = path / "project.json"
            if manifest.exists():
                try:
                    projects.append(Project.model_validate(self._read_json(manifest)))
                except Exception:
                    pass
        return projects

    # ── Analysis data ────────────────────────────────────────────────────────

    def save_json(self, project_id: str, key: str, data: BaseModel | list | dict) -> Path:
        """
        Persist analysis data under {project_id}/analysis/{key}.json.

        Accepts a Pydantic model, a list of models/dicts, or a plain dict.
        Returns the path written.
        """
        dest = self._project_dir(project_id) / "analysis" / f"{key}.json"
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

    def load_json(self, project_id: str, key: str, schema: type[T] | None = None) -> Any:
        """
        Load analysis data from {project_id}/analysis/{key}.json.

        If schema is provided validates a single object via Pydantic.
        Returns raw dict/list otherwise.
        """
        raw = self._read_json(self._project_dir(project_id) / "analysis" / f"{key}.json")
        if schema is not None:
            if isinstance(raw, list):
                return [schema.model_validate(item) for item in raw]
            return schema.model_validate(raw)
        return raw

    # ── Paths ────────────────────────────────────────────────────────────────

    def get_project_path(self, project_id: str) -> Path:
        return self._project_dir(project_id)

    # ── Internals ────────────────────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        return self.root / project_id

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))

    @staticmethod
    def _read_json(path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"No such file: {path}")
        return json.loads(path.read_text())
