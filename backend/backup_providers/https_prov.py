# backend/backup_providers/https_prov.py
"""
Custom HTTPS provider — for self-hosted servers.

The server must implement:
  PUT  <url>/upload/<filename>      body = raw .prx bytes
  GET  <url>/download/<filename>    returns raw .prx bytes
  GET  <url>/list                   returns JSON: [{name, size, timestamp}]
  DELETE <url>/delete/<filename>
  GET  <url>/ping                   returns 200 for health check

cfg keys:
  url          — base URL, e.g. "https://myserver.com/primnox-backup"
  auth_header  — value for Authorization header (e.g. "Bearer xyz"), optional
"""
import requests
from logger import get_logger

log = get_logger("backup.https")


class HTTPSProvider:
    def __init__(self, cfg: dict):
        self._base = cfg.get("url", "").rstrip("/")
        self._headers: dict = {}
        if auth := cfg.get("auth_header", ""):
            self._headers["Authorization"] = auth

    def upload(self, filename: str, data: bytes) -> None:
        url = f"{self._base}/upload/{filename}"
        resp = requests.put(url, data=data, headers=self._headers, timeout=60)
        resp.raise_for_status()
        log.info(f"HTTPS uploaded: {filename}")

    def download(self, filename: str) -> bytes:
        url = f"{self._base}/download/{filename}"
        resp = requests.get(url, headers=self._headers, timeout=60)
        resp.raise_for_status()
        return resp.content

    def list_backups(self) -> list[dict]:
        url = f"{self._base}/list"
        resp = requests.get(url, headers=self._headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def delete(self, filename: str) -> None:
        url = f"{self._base}/delete/{filename}"
        resp = requests.delete(url, headers=self._headers, timeout=15)
        resp.raise_for_status()
        log.info(f"HTTPS deleted: {filename}")

    def test_connection(self) -> bool:
        try:
            resp = requests.get(f"{self._base}/ping", headers=self._headers, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            log.warning(f"HTTPS connection test failed: {e}")
            return False
