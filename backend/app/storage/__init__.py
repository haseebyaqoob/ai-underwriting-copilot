from functools import lru_cache

from app.config import settings
from app.storage.base import StorageBackend


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    if settings.STORAGE_BACKEND == "local":
        from app.storage.local import LocalStorageBackend

        return LocalStorageBackend(settings.LOCAL_STORAGE_PATH)

    if settings.STORAGE_BACKEND == "s3":
        # Not implemented in this session — the interface (StorageBackend)
        # is designed so this is the only place a real S3 backend needs to
        # be wired in: `from app.storage.s3 import S3StorageBackend`,
        # constructed from settings (bucket name, region, etc.), returned
        # here. No caller-side code changes needed.
        raise NotImplementedError(
            "STORAGE_BACKEND=s3 is not implemented yet. The StorageBackend "
            "interface is ready for it (see app/storage/base.py) but no "
            "S3StorageBackend exists in this codebase yet."
        )

    raise ValueError(f"Unknown STORAGE_BACKEND: {settings.STORAGE_BACKEND!r}")
