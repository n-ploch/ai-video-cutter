from __future__ import annotations

import os
from pathlib import Path

from core.storage import ProjectStorage, StorageBackend


def make_storage(
    storage_backend: str | None = None,
    storage_root: str | Path | None = None,
    default_config: Path = Path("config/default.yaml"),
) -> ProjectStorage:
    """Construct a ``ProjectStorage`` wired to the appropriate backend.

    Falls back to environment variables ``STORAGE_BACKEND`` and
    ``STORAGE_ROOT`` when arguments are not provided.  Defaults to local
    filesystem storage rooted at ``local/data/projects``.

    Supported backends:
    - ``"local"`` — ``LocalBackend`` (default)
    - ``"s3"``    — ``S3Backend`` (not yet implemented)
    """
    backend_type = storage_backend or os.environ.get("STORAGE_BACKEND", "local")
    root = Path(storage_root or os.environ.get("STORAGE_ROOT", "local/data/projects"))

    backend: StorageBackend
    if backend_type == "local":
        from core.storage_local import LocalBackend
        backend = LocalBackend(root=root)
    elif backend_type == "s3":
        raise NotImplementedError("S3 backend is not yet implemented")
    else:
        raise ValueError(f"Unknown storage backend: {backend_type!r}")

    return ProjectStorage(root=root, default_config=default_config, backend=backend)
