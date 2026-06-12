# backend/backup_providers/gdrive.py
"""
Google Drive provider.

cfg keys:
  token        — OAuth2 refresh token (obtained during setup flow)
  client_id    — OAuth2 client ID
  client_secret
  folder_id    — Drive folder ID to store backups in (optional; uses root if absent)
"""
import json
from logger import get_logger

log = get_logger("backup.gdrive")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
MIME = "application/octet-stream"


class GDriveProvider:
    def __init__(self, cfg: dict):
        self._cfg = cfg

    def _service(self):
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            raise RuntimeError(
                "Google Drive SDK not installed — run: "
                "pip install google-api-python-client google-auth-oauthlib"
            )
        creds = Credentials(
            token=None,
            refresh_token=self._cfg.get("token"),
            client_id=self._cfg.get("client_id"),
            client_secret=self._cfg.get("client_secret"),
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def _folder_id(self) -> str | None:
        return self._cfg.get("folder_id") or None

    def upload(self, filename: str, data: bytes) -> None:
        from googleapiclient.http import MediaInMemoryUpload
        svc = self._service()
        meta = {"name": filename}
        if self._folder_id():
            meta["parents"] = [self._folder_id()]
        media = MediaInMemoryUpload(data, mimetype=MIME, resumable=False)
        svc.files().create(body=meta, media_body=media, fields="id").execute()
        log.info(f"GDrive uploaded: {filename}")

    def download(self, filename: str) -> bytes:
        import io
        from googleapiclient.http import MediaIoBaseDownload
        svc = self._service()
        file_id = self._find_file_id(svc, filename)
        if not file_id:
            raise FileNotFoundError(f"Backup not found in Drive: {filename}")
        req = svc.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()

    def list_backups(self) -> list[dict]:
        svc = self._service()
        q = "name contains '.prx' and trashed=false"
        if self._folder_id():
            q += f" and '{self._folder_id()}' in parents"
        resp = svc.files().list(
            q=q,
            fields="files(id, name, size, modifiedTime)",
            orderBy="modifiedTime desc",
        ).execute()
        return [
            {
                "name":      f["name"],
                "size":      int(f.get("size", 0)),
                "timestamp": f.get("modifiedTime", ""),
            }
            for f in resp.get("files", [])
        ]

    def delete(self, filename: str) -> None:
        svc = self._service()
        file_id = self._find_file_id(svc, filename)
        if file_id:
            svc.files().delete(fileId=file_id).execute()
            log.info(f"GDrive deleted: {filename}")

    def test_connection(self) -> bool:
        try:
            self._service().files().list(pageSize=1, fields="files(id)").execute()
            return True
        except Exception as e:
            log.warning(f"GDrive connection test failed: {e}")
            return False

    def _find_file_id(self, svc, filename: str) -> str | None:
        q = f"name='{filename}' and trashed=false"
        if self._folder_id():
            q += f" and '{self._folder_id()}' in parents"
        resp = svc.files().list(q=q, fields="files(id)", pageSize=1).execute()
        files = resp.get("files", [])
        return files[0]["id"] if files else None
