# backend/backup_providers/dropbox_prov.py
"""
Dropbox provider.

cfg keys:
  token        — Dropbox OAuth2 access token (long-lived)
  folder       — remote folder path, e.g. "/PrimnoxBackups" (default)
"""
from logger import get_logger

log = get_logger("backup.dropbox")


class DropboxProvider:
    def __init__(self, cfg: dict):
        self._token  = cfg.get("token", "")
        self._folder = cfg.get("folder", "/PrimnoxBackups").rstrip("/")

    def _dbx(self):
        try:
            import dropbox
        except ImportError:
            raise RuntimeError("Dropbox SDK not installed — run: pip install dropbox")
        return dropbox.Dropbox(self._token)

    def _path(self, filename: str) -> str:
        return f"{self._folder}/{filename}"

    def upload(self, filename: str, data: bytes) -> None:
        import dropbox
        dbx = self._dbx()
        dbx.files_upload(
            data,
            self._path(filename),
            mode=dropbox.files.WriteMode.overwrite,
        )
        log.info(f"Dropbox uploaded: {filename}")

    def download(self, filename: str) -> bytes:
        _, resp = self._dbx().files_download(self._path(filename))
        return resp.content

    def list_backups(self) -> list[dict]:
        import dropbox
        dbx = self._dbx()
        try:
            result = dbx.files_list_folder(self._folder)
        except dropbox.exceptions.ApiError:
            return []
        entries = [
            e for e in result.entries
            if isinstance(e, dropbox.files.FileMetadata) and e.name.endswith(".prx")
        ]
        return sorted(
            [
                {
                    "name":      e.name,
                    "size":      e.size,
                    "timestamp": e.server_modified.isoformat(),
                }
                for e in entries
            ],
            key=lambda x: x["timestamp"],
            reverse=True,
        )

    def delete(self, filename: str) -> None:
        self._dbx().files_delete_v2(self._path(filename))
        log.info(f"Dropbox deleted: {filename}")

    def test_connection(self) -> bool:
        try:
            self._dbx().users_get_current_account()
            return True
        except Exception as e:
            log.warning(f"Dropbox connection test failed: {e}")
            return False
