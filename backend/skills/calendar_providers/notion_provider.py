# calendar_providers/notion_provider.py
"""
Notion Calendar provider via Notion API.

Setup:
  1. Go to notion.so/my-integrations → New integration → Copy Internal Integration Token
  2. Share the database/calendar page with the integration (3-dot menu → Add connections)

Config keys:
  token        (str)  — Notion integration token (secret_xxx...)    [required]
  database_id  (str)  — Notion database ID (from URL)               [required]
  date_prop    (str)  — Property name that holds the date            [default: Date]
  title_prop   (str)  — Property name that holds the title           [default: Name]
  name         (str)  — display label                               [optional]
  color        (str)  — hex accent                                  [optional]

REQUIRES_PIP: requests
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from logger import get_logger
from .base_provider import BaseCalendarProvider, CalendarEvent

log = get_logger("calendar.notion")

_NOTION_API = "https://api.notion.com/v1"
_VERSION     = "2022-06-28"


class NotionCalendarProvider(BaseCalendarProvider):
    def __init__(self, config: dict):
        self.token       = config.get("token", "")
        self.database_id = config.get("database_id", "")
        self.date_prop   = config.get("date_prop", "Date")
        self.title_prop  = config.get("title_prop", "Name")
        self.name        = config.get("name", "Notion")
        self.color       = config.get("color", "#000000")

    def is_configured(self) -> bool:
        return bool(self.token) and bool(self.database_id)

    def _headers(self) -> dict:
        return {
            "Authorization":    f"Bearer {self.token}",
            "Notion-Version":   _VERSION,
            "Content-Type":     "application/json",
        }

    def get_events(self, hours_ahead: int = 24) -> list[CalendarEvent]:
        try:
            import requests
        except ImportError:
            log.warning("NotionCalendarProvider requires: pip install requests")
            return []

        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=hours_ahead)

        body = {
            "filter": {
                "and": [
                    {
                        "property": self.date_prop,
                        "date": {"on_or_after": now.date().isoformat()}
                    },
                    {
                        "property": self.date_prop,
                        "date": {"before": end.isoformat()}
                    }
                ]
            },
            "sorts": [{"property": self.date_prop, "direction": "ascending"}],
            "page_size": 20,
        }

        try:
            resp = requests.post(
                f"{_NOTION_API}/databases/{self.database_id}/query",
                headers=self._headers(),
                json=body,
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            log.warning(f"Notion Calendar fetch failed: {e}")
            return []

        events = []
        for page in resp.json().get("results", []):
            try:
                props = page.get("properties", {})

                # Title
                title_prop = props.get(self.title_prop, {})
                title_parts = title_prop.get("title", [])
                title = "".join(p.get("plain_text", "") for p in title_parts) or "Untitled"

                # Date
                date_prop = props.get(self.date_prop, {}).get("date", {})
                start_s = date_prop.get("start", "")
                end_s   = date_prop.get("end", "")
                if not start_s:
                    continue

                start = datetime.fromisoformat(start_s)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)

                if end_s:
                    end_ = datetime.fromisoformat(end_s)
                    if end_.tzinfo is None:
                        end_ = end_.replace(tzinfo=timezone.utc)
                else:
                    end_ = start + timedelta(hours=1)

                # Location from a "Location" text property if it exists
                loc_prop = props.get("Location", {})
                location = ""
                if loc_prop.get("rich_text"):
                    location = "".join(p.get("plain_text", "")
                                       for p in loc_prop["rich_text"])

                events.append(CalendarEvent(
                    title=title, start=start, end=end_,
                    location=location, calendar=self.name, color=self.color,
                    url=page.get("url", ""),
                ))
            except Exception as e:
                log.debug(f"Skipping Notion page: {e}")
        return events
