"""
Object storage interface — Module 3. `local` is implemented for real now;
`s3` is meant to be a drop-in later with zero changes to callers (only
`app/storage/__init__.py`'s factory needs a new branch, and `.env`'s
STORAGE_BACKEND flipped to "s3").

Callers deal purely in `storage_key` strings, never filesystem paths or S3
bucket/key pairs directly — `DocumentVersion.storage_key` in the DB is
backend-agnostic on purpose.
"""
from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str) -> None:
        """Write `data` under `key`. Overwrites if the key already exists
        (callers are responsible for generating unique keys — see
        `document_service._build_storage_key`)."""
        ...

    @abstractmethod
    def read(self, key: str) -> bytes:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...
