"""Tests for outlook_provider.py's timezone handling — Microsoft Graph can
return a legacy Windows timezone name (e.g. "Pacific Standard Time") instead
of an IANA key, which zoneinfo.ZoneInfo doesn't recognize. Previously this
silently dropped the whole event via the broad per-item except; now it falls
back to UTC instead of losing the event entirely."""
import requests

from skills.calendar_providers.outlook_provider import OutlookCalendarProvider


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _provider_with_token(monkeypatch, items) -> OutlookCalendarProvider:
    provider = OutlookCalendarProvider({"client_id": "fake-client-id"})
    monkeypatch.setattr(provider, "_get_token", lambda: "fake-token")
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _FakeResponse({"value": items}))
    return provider


class TestOutlookProviderTimezoneFallback:
    def test_unrecognized_windows_timezone_falls_back_to_utc_instead_of_dropping_event(self, monkeypatch):
        items = [{
            "subject": "Standup",
            "start": {"dateTime": "2024-01-15T09:00:00", "timeZone": "Pacific Standard Time"},
            "end": {"dateTime": "2024-01-15T09:30:00", "timeZone": "Pacific Standard Time"},
            "location": {"displayName": ""},
            "bodyPreview": "",
        }]
        events = _provider_with_token(monkeypatch, items).get_events(hours_ahead=24)

        assert len(events) == 1
        assert events[0].title == "Standup"
        assert events[0].start.tzinfo is not None

    def test_valid_iana_timezone_still_works_normally(self, monkeypatch):
        items = [{
            "subject": "Standup",
            "start": {"dateTime": "2024-01-15T09:00:00", "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": "2024-01-15T09:30:00", "timeZone": "America/Los_Angeles"},
            "location": {"displayName": ""},
            "bodyPreview": "",
        }]
        events = _provider_with_token(monkeypatch, items).get_events(hours_ahead=24)

        assert len(events) == 1
        assert str(events[0].start.tzinfo) == "America/Los_Angeles"

    def test_utc_timezone_still_works(self, monkeypatch):
        items = [{
            "subject": "Standup",
            "start": {"dateTime": "2024-01-15T09:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2024-01-15T09:30:00", "timeZone": "UTC"},
            "location": {"displayName": ""},
            "bodyPreview": "",
        }]
        events = _provider_with_token(monkeypatch, items).get_events(hours_ahead=24)

        assert len(events) == 1
        assert events[0].start.hour == 9
