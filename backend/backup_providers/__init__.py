# backend/backup_providers/__init__.py
"""
CloudProvider protocol — every adapter must implement this interface.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class CloudProvider(Protocol):
    def upload(self, filename: str, data: bytes) -> None:
        """Upload data as filename to the remote storage."""
        ...

    def download(self, filename: str) -> bytes:
        """Download and return the raw bytes for a remote file."""
        ...

    def list_backups(self) -> list[dict]:
        """Return [{name, size, timestamp}] for all .prx files in the remote."""
        ...

    def delete(self, filename: str) -> None:
        """Delete a remote backup file."""
        ...

    def test_connection(self) -> bool:
        """Return True if credentials are valid and the bucket/folder is reachable."""
        ...
