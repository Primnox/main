# calendar_providers/outlook_provider.py
"""
Microsoft Outlook / Office 365 provider via Microsoft Graph API.

Setup:
  1. Go to portal.azure.com → App registrations → New registration (Personal/Work)
  2. Add permission: Calendars.Read (delegated) → Grant admin consent
  3. Under Authentication add a Mobile/Desktop redirect: http://localhost
  4. Copy the Application (client) ID

Config keys:
  client_id   (str)  — Azure app (client) ID                       [required]
  tenant_id   (str)  — "common" for personal accounts, org tenant  [default: common]
  name        (str)  — display label                               [optional]
  color       (str)  — hex accent                                  [optional]

REQUIRES_PIP: msal requests
"""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from logger import get_logger
from .base_provider import BaseCalendarProvider, CalendarEvent

log = get_logger("calendar.outlook")

_GRAPH_BASE  = "https://graph.microsoft.com/v1.0"
_SCOPES      = ["Calendars.Read", "offline_access"]


def _get_token_path() -> Path:
    try:
        from settings_manager import get_appdata_dir
        return get_appdata_dir() / "outlook_calendar_token.json"
    except Exception:
        return Path.home() / ".primnox_outlook_token.json"


class OutlookCalendarProvider(BaseCalendarProvider):
    def __init__(self, config: dict):
        self.client_id = config.get("client_id", "")
        self.tenant_id = config.get("tenant_id", "common")
        self.name      = config.get("name", "Outlook")
        self.color     = config.get("color", "#0078d4")
        self._token:   str   = ""
        self._token_exp: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.client_id)

    def _get_token(self) -> str | None:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        try:
            import msal
            token_path = _get_token_path()
            cache = msal.SerializableTokenCache()
            if token_path.exists():
                cache.deserialize(token_path.read_text())

            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            app = msal.PublicClientApplication(self.client_id, authority=authority,
                                               token_cache=cache)

            accounts = app.get_accounts()
            result = None
            if accounts:
                result = app.acquire_token_silent(_SCOPES, account=accounts[0])

            if not result:
                # Device code flow — works headlessly
                flow = app.initiate_device_flow(_SCOPES)
                log.info(f"Outlook auth: {flow.get('message', '')}")
                result = app.acquire_token_by_device_flow(flow)

            if result and "access_token" in result:
                token_path.write_text(cache.serialize())
                self._token     = result["access_token"]
                self._token_exp = time.time() + result.get("expires_in", 3600)
                return self._token
        except Exception as e:
            log.warning(f"Outlook auth failed: {e}")
        return None

    def get_events(self, hours_ahead: int = 24) -> list[CalendarEvent]:
        token = self._get_token()
        if not token:
            return []
        try:
            import requests
            now = datetime.now(timezone.utc)
            end = now + timedelta(hours=hours_ahead)
            url = (f"{_GRAPH_BASE}/me/calendarView"
                   f"?startDateTime={now.isoformat()}&endDateTime={end.isoformat()}"
                   f"&$select=subject,start,end,location,bodyPreview"
                   f"&$orderby=start/dateTime&$top=20")
            resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
            resp.raise_for_status()

            events = []
            for item in resp.json().get("value", []):
                try:
                    title    = item.get("subject", "Untitled")
                    location = item.get("location", {}).get("displayName", "")
                    desc     = item.get("bodyPreview", "")
                    start_s  = item["start"]["dateTime"]
                    end_s    = item["end"]["dateTime"]
                    tz_name  = item["start"].get("timeZone", "UTC")

                    # Graph returns naive times in the event's timezone. Without
                    # a `Prefer: outlook.timezone` header, Graph can return a
                    # legacy Windows timezone name (e.g. "Pacific Standard
                    # Time") instead of an IANA key — zoneinfo doesn't know
                    # those, so fall back to UTC rather than silently dropping
                    # the whole event (better to show it at a possibly-wrong
                    # hour than not show it at all).
                    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
                    try:
                        tz = ZoneInfo(tz_name)
                    except ZoneInfoNotFoundError:
                        log.warning(f"Outlook event has unrecognized timezone '{tz_name}' — falling back to UTC")
                        tz = timezone.utc
                    start = datetime.fromisoformat(start_s).replace(tzinfo=tz)
                    end_  = datetime.fromisoformat(end_s).replace(tzinfo=tz)

                    events.append(CalendarEvent(
                        title=title, start=start, end=end_,
                        location=location, description=desc,
                        calendar=self.name, color=self.color,
                    ))
                except Exception as e:
                    log.debug(f"Skipping Outlook event: {e}")
            return events
        except Exception as e:
            log.warning(f"Outlook Calendar fetch failed: {e}")
            return []
