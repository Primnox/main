# calendar_providers/base_provider.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CalendarEvent:
    title:    str
    start:    datetime
    end:      datetime
    location: str = ""
    description: str = ""
    calendar: str = ""     # which calendar/account it came from
    color:    str = "#6366f1"
    url:      str = ""

    @property
    def duration_minutes(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() / 60))

    @property
    def minutes_until(self) -> int:
        delta = (self.start - datetime.now().astimezone()).total_seconds()
        return int(delta / 60)

    @property
    def is_now(self) -> bool:
        now = datetime.now().astimezone()
        return self.start <= now <= self.end

    @property
    def is_upcoming(self) -> bool:
        return self.minutes_until > 0

    def to_dict(self) -> dict:
        return {
            "title":       self.title,
            "start_iso":   self.start.isoformat(),
            "end_iso":     self.end.isoformat(),
            "location":    self.location,
            "description": self.description[:200],
            "calendar":    self.calendar,
            "color":       self.color,
            "minutes_until": self.minutes_until,
            "is_now":      self.is_now,
            "duration_minutes": self.duration_minutes,
        }


class BaseCalendarProvider(ABC):
    name:  str = ""
    color: str = "#6366f1"

    @abstractmethod
    def get_events(self, hours_ahead: int = 24) -> list[CalendarEvent]:
        """Return upcoming events within the next `hours_ahead` hours."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Return False if required credentials / URLs are missing."""
        return True
