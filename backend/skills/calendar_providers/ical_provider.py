# calendar_providers/ical_provider.py
"""
Universal iCal provider — works with ANY service that exports an .ics URL:
  • Google Calendar   → Settings → Calendar → Secret address in iCal format
  • Outlook / O365    → Calendar → Publish → ICS link
  • ProtonCalendar    → Settings → Calendar → Export link
  • Apple iCloud      → Calendar → Share → Copy Link (public .ics)
  • Notion Calendar   → Calendar Settings → Export → ICS
  • Any WebDAV server

REQUIRES_PIP: icalendar recurring-ical-events requests
"""

from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone
from logger import get_logger
from .base_provider import BaseCalendarProvider, CalendarEvent

log = get_logger("calendar.ical")

# Cache each URL for this many seconds to avoid hammering remote servers
_CACHE_TTL = 120


class ICalProvider(BaseCalendarProvider):
    """
    Config dict keys:
      url    (str)  — https:// or file:// iCal URL               [required]
      name   (str)  — human label shown in the island strip       [optional]
      color  (str)  — hex accent colour                           [optional]
    """

    def __init__(self, config: dict):
        self.url:   str = config.get("url", "").strip()
        self.name:  str = config.get("name", "Calendar")
        self.color: str = config.get("color", "#6366f1")
        self._cache_data: bytes | None = None
        self._cache_ts:   float       = 0.0

    def is_configured(self) -> bool:
        return bool(self.url)

    def _fetch_raw(self) -> bytes | None:
        """Fetch (or return cached) raw .ics bytes."""
        now = time.time()
        if self._cache_data and (now - self._cache_ts) < _CACHE_TTL:
            return self._cache_data

        try:
            import requests
            resp = requests.get(self.url, timeout=10, headers={"User-Agent": "Primnox/1.0"})
            resp.raise_for_status()
            self._cache_data = resp.content
            self._cache_ts   = now
            return self._cache_data
        except Exception as e:
            log.warning(f"ICalProvider fetch failed ({self.name}): {e}")
            return self._cache_data  # return stale cache rather than nothing

    def get_events(self, hours_ahead: int = 24) -> list[CalendarEvent]:
        try:
            import icalendar
            import recurring_ical_events
        except ImportError:
            log.warning("ICalProvider requires: pip install icalendar recurring-ical-events requests")
            return []

        raw = self._fetch_raw()
        if not raw:
            return []

        try:
            cal = icalendar.Calendar.from_ical(raw)
        except Exception as e:
            log.warning(f"ICalProvider parse failed ({self.name}): {e}")
            return []

        now   = datetime.now(timezone.utc)
        end   = now + timedelta(hours=hours_ahead)
        events: list[CalendarEvent] = []

        try:
            raw_events = recurring_ical_events.of(cal).between(now, end)
        except Exception as e:
            log.warning(f"ICalProvider recurring expansion failed: {e}")
            return []

        for component in raw_events:
            if component.get("TYPE", component.name) not in ("VEVENT",):
                continue
            try:
                title    = str(component.get("SUMMARY", "Untitled"))
                location = str(component.get("LOCATION", ""))
                desc     = str(component.get("DESCRIPTION", ""))

                dtstart = component.get("DTSTART")
                dtend   = component.get("DTEND")
                if not dtstart or not dtend:
                    continue

                start = dtstart.dt
                end_  = dtend.dt

                # Normalize to aware datetime (handle date-only all-day events)
                if not hasattr(start, "hour"):  # date object
                    start = datetime(start.year, start.month, start.day,
                                     tzinfo=timezone.utc)
                    end_  = datetime(end_.year, end_.month, end_.day,
                                     tzinfo=timezone.utc)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if end_.tzinfo is None:
                    end_ = end_.replace(tzinfo=timezone.utc)

                events.append(CalendarEvent(
                    title=title,
                    start=start,
                    end=end_,
                    location=location,
                    description=desc,
                    calendar=self.name,
                    color=self.color,
                ))
            except Exception as e:
                log.debug(f"Skipping event: {e}")
                continue

        events.sort(key=lambda e: e.start)
        return events
