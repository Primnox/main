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
import ipaddress
import socket
from urllib.parse import urlparse

import requests
from logger import get_logger

log = get_logger("backup.https")


def _validate_url(url: str) -> None:
    """
    Basic SSRF guard: only allow https:// URLs that don't resolve to
    loopback, link-local, or private network ranges (e.g. 127.0.0.1,
    169.254.169.254 cloud metadata, 10.x/192.168.x internal services).
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Backup URL must use https://")
    host = parsed.hostname
    if not host:
        raise ValueError("Backup URL is missing a host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve backup host '{host}': {e}")
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast:
            raise ValueError(
                f"Backup URL resolves to a non-public address ({addr}) — refusing for safety"
            )


class HTTPSProvider:
    def __init__(self, cfg: dict):
        self._base = cfg.get("url", "").rstrip("/")
        if self._base:
            _validate_url(self._base)
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
