"""Tests for google_provider.py's all-day event handling — the API returns
"date" (no time) instead of "dateTime" for all-day events, which previously
produced a naive datetime and crashed CalendarEvent.is_now/minutes_until
(compared against an aware "now") the moment the event was touched."""
from skills.calendar_providers.google_provider import GoogleCalendarProvider


class _FakeEventsList:
    def __init__(self, items):
        self._items = items

    def execute(self):
        return {"items": self._items}


class _FakeEventsResource:
    def __init__(self, items):
        self._items = items

    def list(self, **kwargs):
        return _FakeEventsList(self._items)


class _FakeService:
    def __init__(self, items):
        self._items = items

    def events(self):
        return _FakeEventsResource(self._items)


def _provider_with_fake_service(items) -> GoogleCalendarProvider:
    provider = GoogleCalendarProvider({"calendar_id": "primary"})
    provider._service = _FakeService(items)
    return provider


class TestGoogleProviderAllDayEvents:
    def test_all_day_event_produces_timezone_aware_datetimes(self):
        items = [{
            "summary": "Company Holiday",
            "start": {"date": "2024-01-15"},
            "end": {"date": "2024-01-16"},
        }]
        events = _provider_with_fake_service(items).get_events(hours_ahead=24)

        assert len(events) == 1
        assert events[0].start.tzinfo is not None
        assert events[0].end.tzinfo is not None

    def test_all_day_event_does_not_crash_is_now_or_minutes_until(self):
        items = [{
            "summary": "Company Holiday",
            "start": {"date": "2024-01-15"},
            "end": {"date": "2024-01-16"},
        }]
        events = _provider_with_fake_service(items).get_events(hours_ahead=24)

        # Previously raised: TypeError: can't compare offset-naive and
        # offset-aware datetimes.
        events[0].is_now
        events[0].minutes_until

    def test_all_day_and_timed_events_sort_together_without_crashing(self):
        items = [
            {"summary": "All Day Thing", "start": {"date": "2024-01-15"}, "end": {"date": "2024-01-16"}},
            {
                "summary": "Standup",
                "start": {"dateTime": "2024-01-15T09:00:00Z"},
                "end": {"dateTime": "2024-01-15T09:30:00Z"},
            },
        ]
        events = _provider_with_fake_service(items).get_events(hours_ahead=24)

        assert len(events) == 2
        # This is exactly what calendar_skill.py's _fetch_events does across
        # every configured provider's combined event list.
        sorted(events, key=lambda e: e.start)

    def test_timed_event_still_parses_correctly(self):
        items = [{
            "summary": "Standup",
            "start": {"dateTime": "2024-01-15T09:00:00Z"},
            "end": {"dateTime": "2024-01-15T09:30:00Z"},
        }]
        events = _provider_with_fake_service(items).get_events(hours_ahead=24)

        assert len(events) == 1
        assert events[0].start.hour == 9
        assert events[0].start.tzinfo is not None
