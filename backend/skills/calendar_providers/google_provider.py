# calendar_providers/google_provider.py
"""
Google Calendar API provider (OAuth2).

Setup:
  1. Go to console.cloud.google.com → New project → Enable Google Calendar API
  2. Create OAuth2 credentials (Desktop app) → Download client_secret.json
  3. On first run Primnox opens a browser for consent — token saved to APPDATA

Config keys:
  client_secret_path  (str)  — path to client_secret.json           [required]
  calendar_id         (str)  — "primary" or specific calendar ID     [default: primary]
  name                (str)  — display label                         [optional]
  color               (str)  — hex accent                            [optional]

REQUIRES_PIP: google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from logger import get_logger
from .base_provider import BaseCalendarProvider, CalendarEvent

log = get_logger("calendar.google")

_TOKEN_PATH = None  # set lazily from settings_manager APPDATA dir


def _get_token_path() -> Path:
    global _TOKEN_PATH
    if _TOKEN_PATH is None:
        try:
            from settings_manager import get_appdata_dir
            _TOKEN_PATH = get_appdata_dir() / "google_calendar_token.json"
        except Exception:
            _TOKEN_PATH = Path.home() / ".primnox_google_token.json"
    return _TOKEN_PATH


_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class GoogleCalendarProvider(BaseCalendarProvider):
    def __init__(self, config: dict):
        self.client_secret_path = config.get("client_secret_path", "")
        self.calendar_id        = config.get("calendar_id", "primary")
        self.name               = config.get("name", "Google Calendar")
        self.color              = config.get("color", "#4285f4")
        self._service           = None

    def is_configured(self) -> bool:
        return bool(self.client_secret_path) and Path(self.client_secret_path).exists()

    def _get_service(self):
        if self._service:
            return self._service
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = None
            token_path = _get_token_path()
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.client_secret_path, _SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                token_path.write_text(creds.to_json())

            self._service = build("calendar", "v3", credentials=creds)
            return self._service
        except Exception as e:
            log.warning(f"Google Calendar auth failed: {e}")
            return None

    def get_events(self, hours_ahead: int = 24) -> list[CalendarEvent]:
        service = self._get_service()
        if not service:
            return []
        try:
            now = datetime.now(timezone.utc)
            end = now + timedelta(hours=hours_ahead)
            result = service.events().list(
                calendarId=self.calendar_id,
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=20,
            ).execute()

            events = []
            for item in result.get("items", []):
                try:
                    title    = item.get("summary", "Untitled")
                    location = item.get("location", "")
                    desc     = item.get("description", "")
                    start_s  = item["start"].get("dateTime", item["start"].get("date", ""))
                    end_s    = item["end"].get("dateTime", item["end"].get("date", ""))

                    start = datetime.fromisoformat(start_s.replace("Z", "+00:00"))
                    end_  = datetime.fromisoformat(end_s.replace("Z", "+00:00"))

                    events.append(CalendarEvent(
                        title=title, start=start, end=end_,
                        location=location, description=desc,
                        calendar=self.name, color=self.color,
                    ))
                except Exception as e:
                    log.debug(f"Skipping Google event: {e}")
            return events
        except Exception as e:
            log.warning(f"Google Calendar fetch failed: {e}")
            return []
