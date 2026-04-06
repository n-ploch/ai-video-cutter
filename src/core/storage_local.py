from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator

from core.storage import StorageBackend


class LocalBackend(StorageBackend):
    """Filesystem-backed storage backend.

    All keys are resolved relative to ``root``.  ``local_path()`` yields the
    real on-disk path directly — no copies, no temp files.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _abs(self, key: str) -> Path:
        return self.root / key

    # ── StorageBackend interface ──────────────────────────────────────────────

    def read_bytes(self, key: str) -> bytes:
        return self._abs(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        p = self._abs(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def exists(self, key: str) -> bool:
        return self._abs(key).exists()

    def list_keys(self, prefix: str) -> list[str]:
        base = self._abs(prefix)
        if not base.exists():
            return []
        return [
            str(p.relative_to(self.root))
            for p in base.rglob("*")
            if p.is_file()
        ]

    def delete(self, key: str) -> None:
        self._abs(key).unlink(missing_ok=True)

    @contextlib.contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        """Yield the real on-disk path.  No copy needed for local storage."""
        yield self._abs(key)

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a FastAPI-served path.  The API mounts /files → storage root."""
        return f"/files/{key}"
