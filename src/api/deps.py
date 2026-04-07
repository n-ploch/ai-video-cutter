"""FastAPI dependency injection."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Depends

from core.config import AppSettings
from core.storage import ProjectStorage
from core.storage_factory import make_storage


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings.from_env()


def get_storage(
    app_settings: AppSettings = Depends(get_app_settings),
) -> ProjectStorage:
    return make_storage(
        storage_backend=app_settings.storage_backend,
        storage_root=app_settings.storage_root,
        default_config=app_settings.default_config_path,
    )
