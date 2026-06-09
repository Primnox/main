# skills/calendar_skill.py
"""
Calendar Island Skill — shows upcoming events as a strip in the Dynamic Island.

Pluggable providers (add as many as you like in Primnox settings):
  • iCal URL   — Google Calendar, Outlook, ProtonCalendar, Apple iCloud, Notion
  • Google API — richer Google Calendar integration (optional)
  • Outlook    — Microsoft Graph API (optional)
  • Notion API — Notion Calendar databases (optional)

Island strip behaviour:
  - Default:     "📅  Data Structures  ·  Room 204  ·  in 34m"
  - Imminent(<15m): urgent=True  "⚡  Data Structures starting in 8m"
  - In progress:   "◉  Data Structures  ·  ends 4:00 PM"
  - Nothing today: strip hidden

Triggered via chat by words like "next class", "my schedule", "calendar", etc.
"""

from __future__ import annotations
import threading
import time
from datetime import datetime, timezone
from logger import get_logger
from skills.base_island_skill import BaseIslandSkill
from skills.base_skill import SkillContext, SkillResult
from settings_manager import load_settings

log = get_logger("skill.calendar")

_CACHE_LOCK = threading.Lock()


def _build_provider(cfg: dict):
    """Instantiate the right provider class from a config dict."""
    ptype = cfg.get("type", "ical").lower()
    try:
        if ptype == "ical":
            from skills.calendar_providers.ical_provider import ICalProvider
            return ICalProvider(cfg)
        elif ptype == "google":
            from skills.calendar_providers.google_provider import GoogleCalendarProvider
            return GoogleCalendarProvider(cfg)
        elif ptype == "outlook":
            from skills.calendar_providers.outlook_provider import OutlookCalendarProvider
            return OutlookCalendarProvider(cfg)
        elif ptype == "notion":
            from skills.calendar_providers.notion_provider import NotionCalendarProvider
            return NotionCalendarProvider(cfg)
        else:
            log.warning(f"Unknown calendar provider type: {ptype!r}")
    except Exception as e:
        log.warning(f"Failed to build provider {ptype!r}: {e}")
    return None


def _fmt_time(dt: datetime) -> str:
    local = dt.astimezone()
    h = local.hour % 12 or 12
    m = local.minute
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{h}:{m:02d} {ampm}"


def _fmt_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if m else f"{h}h"


class CalendarIslandSkill(BaseIslandSkill):
    name        = "calendar"
    island_name = "calendar"
    description = (
        "Shows your upcoming events in the Dynamic Island. "
        "Supports Google Calendar, Outlook, ProtonCalendar, Notion, and any iCal URL. "
        "Triggers on: 'next class', 'my schedule', 'what class', 'calendar', 'timetable'."
    )
    trigger_words = (
        "next class", "my schedule", "what class", "timetable",
        "calendar", "next event", "when is my", "class today",
        "what do i have", "upcoming events", "my classes",
    )
    supported_extensions: tuple = ()
    refresh_seconds = 60
    REQUIRES_PIP    = ()   # providers declare their own deps

    def __init__(self):
        self._providers:   list = []
        self._last_reload: float = 0.0
        self._event_cache: list  = []
        self._cache_ts:    float = 0.0
        self._cache_ttl:   float = 55.0   # slightly less than refresh_seconds

    # ── Provider management ────────────────────────────────────────────────────

    def _reload_providers(self):
        """Re-read settings and rebuild providers if config changed."""
        try:
            settings = load_settings()
            configs  = settings.get("calendar_providers", [])
            if not configs:
                self._providers = []
                return
            self._providers = [
                p for cfg in configs
                if (p := _build_provider(cfg)) and p.is_configured()
            ]
            log.debug(f"Calendar: loaded {len(self._providers)} provider(s)")
        except Exception as e:
            log.warning(f"Calendar: failed to reload providers: {e}")

    def _get_providers(self):
        now = time.time()
        if now - self._last_reload > 120:   # re-check settings every 2 min
            self._reload_providers()
            self._last_reload = now
        return self._providers

    # ── Event fetching ─────────────────────────────────────────────────────────

    def _fetch_events(self) -> list:
        now = time.time()
        with _CACHE_LOCK:
            if self._event_cache and now - self._cache_ts < self._cache_ttl:
                return self._event_cache

        providers = self._get_providers()
        if not providers:
            return []

        all_events = []
        for provider in providers:
            try:
                all_events.extend(provider.get_events(hours_ahead=24))
            except Exception as e:
                log.warning(f"Calendar provider {provider.name} failed: {e}")

        # Sort by start time, deduplicate by (title, start)
        seen = set()
        deduped = []
        for ev in sorted(all_events, key=lambda e: e.start):
            key = (ev.title, ev.start.isoformat())
            if key not in seen:
                seen.add(key)
                deduped.append(ev)

        with _CACHE_LOCK:
            self._event_cache = deduped
            self._cache_ts    = now
        return deduped

    # ── Island data ────────────────────────────────────────────────────────────

    def get_island_data(self) -> dict | None:
        events = self._fetch_events()
        if not events:
            return None

        now = datetime.now(timezone.utc)

        # Find the current event (if any) and the next upcoming one
        current_event = next(
            (e for e in events if e.is_now), None
        )
        next_event = next(
            (e for e in events if e.is_upcoming and e.minutes_until >= 0), None
        )

        if not current_event and not next_event:
            return None

        # ── Currently in an event ──────────────────────────────────────────────
        if current_event:
            loc = f"  ·  {current_event.location}" if current_event.location else ""
            end_time = _fmt_time(current_event.end)
            return {
                "label":    "◉ Now",
                "title":    current_event.title,
                "subtitle": f"In progress{loc}  ·  ends {end_time}",
                "color":    current_event.color,
                "urgent":   False,
                "panel":    _build_panel(events),
            }

        # ── Next upcoming event ────────────────────────────────────────────────
        ev      = next_event
        mins    = ev.minutes_until
        urgent  = mins <= 15
        loc     = f"  ·  {ev.location}" if ev.location else ""
        time_s  = _fmt_minutes(mins)

        if urgent:
            label    = "⚡ Soon"
            subtitle = f"Starting in {time_s}{loc}"
        else:
            label    = "📅 Next"
            subtitle = f"{ev.calendar}{loc}  ·  in {time_s}"

        return {
            "label":    label,
            "title":    ev.title,
            "subtitle": subtitle,
            "badge":    time_s,
            "color":    ev.color,
            "urgent":   urgent,
            "panel":    _build_panel(events),
        }

    # ── Chat execution ─────────────────────────────────────────────────────────

    def execute(self, ctx: SkillContext) -> SkillResult:
        events = self._fetch_events()
        if not events:
            settings = load_settings()
            if not settings.get("calendar_providers"):
                return SkillResult(
                    success=True,
                    output_text=(
                        "No calendar connected yet. Go to **Configure → Calendar** "
                        "and add an iCal URL or connect Google / Outlook."
                    )
                )
            return SkillResult(success=True, output_text="No upcoming events in the next 24 hours.")

        now = datetime.now(timezone.utc)
        lines = ["## Upcoming Events\n"]
        for ev in events[:10]:
            start_fmt = ev.start.astimezone().strftime("%a %b %d, %I:%M %p")
            end_fmt   = ev.end.astimezone().strftime("%I:%M %p")
            loc       = f" · {ev.location}" if ev.location else ""
            status    = " *(now)*" if ev.is_now else f" *(in {_fmt_minutes(ev.minutes_until)})*"
            lines.append(f"- **{ev.title}**{status}  \n  {start_fmt} – {end_fmt}{loc}")

        return SkillResult(success=True, output_text="\n".join(lines))


def _build_panel(events: list) -> dict:
    """Build the expanded panel payload showing today's full agenda."""
    today_events = [
        e for e in events
        if e.start.astimezone().date() == datetime.now().date()
    ][:6]

    items = []
    for ev in today_events:
        start = ev.start.astimezone().strftime("%I:%M %p").lstrip("0")
        loc   = f" · {ev.location}" if ev.location else ""
        status = "◉" if ev.is_now else ("⚡" if ev.minutes_until <= 15 else "○")
        items.append({
            "label": f"{status} {start}",
            "value": f"{ev.title}{loc}",
            "color": ev.color,
        })
    return {"items": items}
