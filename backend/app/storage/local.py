import os

from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):

    def __init__(self, base_path: str):
        self._base_path = os.path.abspath(base_path)
        os.makedirs(self._base_path, exist_ok=True)

    def _full_path(self, key: str) -> str:
        # Defend against a key that tries to escape base_path via ".." —
        # storage keys are always server-generated (see
        # document_service._build_storage_key), never taken from user
        # input directly, but this is a cheap, worthwhile guard.
        full = os.path.abspath(os.path.join(self._base_path, key))
        if not full.startswith(self._base_path + os.sep) and full != self._base_path:
            raise ValueError(f"storage key escapes base path: {key!r}")
        return full

    def save(self, key: str, data: bytes, content_type: str) -> None:
        full = self._full_path(key)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)

    def read(self, key: str) -> bytes:
        with open(self._full_path(key), "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        full = self._full_path(key)
        if os.path.exists(full):
            os.remove(full)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._full_path(key))
