"""Tests for the Privacy Mirror PII scrubber.

This is the highest-stakes pure logic in the backend: anything it fails to
redact is shipped verbatim to a third-party model provider and cannot be
recalled. Nothing here loads the DeBERTa model — it is not loaded at import
time, so `_pipeline is None` and `_detect_spans` exercises the regex backstop,
which is the path that runs during startup and whenever the model fails.
"""

import pytest

from privacy_mirror import (
    ScrubSession,
    StreamRehydrator,
    _detect_spans,
    _regex_redact,
)


# ── Regex redaction ──────────────────────────────────────────────────────────


class TestRegexRedact:
    def test_redacts_email(self):
        out = _regex_redact("mail me at john.smith@example.com please")
        assert "john.smith@example.com" not in out
        assert "[EMAIL]" in out

    def test_redacts_ipv4(self):
        out = _regex_redact("server at 192.168.1.100 is down")
        assert "192.168.1.100" not in out
        assert "[IPV4]" in out

    def test_redacts_credit_card_in_both_spacings(self):
        for card in ("4111-1111-1111-1111", "4111 1111 1111 1111", "4111111111111111"):
            out = _regex_redact(f"card {card} exp 09/26")
            assert card not in out, f"{card} leaked"

    def test_redacts_api_key_value_but_keeps_the_label(self):
        # Only the secret is replaced; the surrounding assignment stays readable
        # so the model still knows a token was present.
        out = _regex_redact("token=sk_live_abc123def456ghi789jkl")
        assert "sk_live_abc123def456ghi789jkl" not in out
        assert "token=" in out
        assert "[REDACTED]" in out

    def test_redacts_long_opaque_strings(self):
        secret = "a" * 40
        assert secret not in _regex_redact(f"bearer {secret}")

    def test_leaves_ordinary_prose_alone(self):
        text = "Let us meet on Tuesday to review the roadmap."
        assert _regex_redact(text) == text

    def test_empty_input_round_trips(self):
        assert _regex_redact("") == ""


class TestCityGazetteer:
    """The DeBERTa model produces no span at all for most non-US cities, so the
    gazetteer is the only thing standing between them and a verbatim leak."""

    @pytest.mark.parametrize(
        "city", ["Mumbai", "Chennai", "Tokyo", "Bengaluru", "Dubai", "Kyiv"]
    )
    def test_redacts_cities_the_model_misses(self, city):
        out = _regex_redact(f"I live in {city} these days")
        assert city not in out
        assert "[CITY]" in out

    def test_prefers_the_longer_city_name(self):
        # "New Delhi" must win over the "Delhi" substring, or the word "New"
        # is left dangling in front of the placeholder.
        out = _regex_redact("flying to New Delhi tomorrow")
        assert "Delhi" not in out
        assert "New [CITY]" not in out

    @pytest.mark.parametrize("word", ["Reading", "Nice", "Mobile", "Bath", "Cork"])
    def test_does_not_redact_city_names_that_are_ordinary_words(self, word):
        # These are deliberately excluded from the gazetteer; redacting them
        # would mangle normal prose.
        text = f"{word} is something I do daily"
        assert _regex_redact(text) == text

    def test_requires_a_word_boundary(self):
        # "Pune" inside "Puneet" is a name fragment, not a city.
        assert "Puneet" in _regex_redact("Puneet sent the report")


# ── Span detection ───────────────────────────────────────────────────────────


class TestDetectSpans:
    def test_returns_nothing_for_clean_text(self):
        assert _detect_spans("nothing sensitive here") == []

    def test_spans_point_at_the_real_substring(self):
        text = "reach me at a@b.co ok"
        spans = _detect_spans(text)
        assert spans
        for sp in spans:
            assert text[sp["start"] : sp["end"]] == sp["text"]

    def test_spans_never_overlap(self):
        text = "mail a@b.co from 10.0.0.1 with token=abcdefghijklmnopqrstuvwx"
        spans = sorted(_detect_spans(text), key=lambda s: s["start"])
        for prev, nxt in zip(spans, spans[1:]):
            assert prev["end"] <= nxt["start"], f"{prev} overlaps {nxt}"

    def test_spans_carry_no_surrounding_whitespace(self):
        for sp in _detect_spans("  a@b.co  and  10.0.0.1  "):
            assert sp["text"] == sp["text"].strip()

    def test_empty_text_is_safe(self):
        assert _detect_spans("") == []


# ── ScrubSession ─────────────────────────────────────────────────────────────


class TestScrubSession:
    def test_scrub_removes_the_original_and_rehydrate_restores_it(self):
        s = ScrubSession()
        text = "email bob@corp.com about the invoice"
        scrubbed = s.scrub(text)

        assert "bob@corp.com" not in scrubbed
        assert s.rehydrate(scrubbed) == text

    def test_round_trips_multiple_distinct_entities(self):
        s = ScrubSession()
        text = "bob@corp.com and eve@corp.com from 10.0.0.1"
        assert s.rehydrate(s.scrub(text)) == text

    def test_the_same_value_reuses_one_placeholder(self):
        s = ScrubSession()
        scrubbed = s.scrub("bob@corp.com wrote, then bob@corp.com wrote again")
        placeholders = {e["placeholder"] for e in s.mapping}
        assert len(placeholders) == 1
        assert scrubbed.count(placeholders.pop()) == 2

    def test_placeholders_are_numbered_in_reading_order(self):
        s = ScrubSession()
        s.scrub("first a@x.com then b@x.com")
        emails = [e for e in s.mapping if e["label"] == "EMAIL"]
        assert [e["original"] for e in emails] == ["a@x.com", "b@x.com"]
        assert emails[0]["placeholder"].endswith("_1§")
        assert emails[1]["placeholder"].endswith("_2§")

    def test_mapping_stays_on_device_and_is_ordered_and_unique(self):
        s = ScrubSession()
        s.scrub("a@x.com, a@x.com, b@x.com")
        originals = [e["original"] for e in s.mapping]
        assert originals == ["a@x.com", "b@x.com"]

    def test_double_digit_placeholders_are_not_clobbered_by_single_digit_ones(self):
        # §EMAIL_1§ is a prefix-ish match risk for §EMAIL_10§; rehydrate sorts
        # by length to avoid corrupting the longer one.
        s = ScrubSession()
        text = " ".join(f"user{i}@corp.com" for i in range(12))
        assert s.rehydrate(s.scrub(text)) == text

    def test_scrub_of_clean_text_is_a_no_op(self):
        s = ScrubSession()
        text = "no secrets in this sentence"
        assert s.scrub(text) == text
        assert s.mapping == []

    def test_empty_string_round_trips(self):
        s = ScrubSession()
        assert s.scrub("") == ""
        assert s.rehydrate("") == ""

    def test_unmapped_placeholder_never_reaches_the_user(self):
        # If the model echoes or invents a placeholder we have no mapping for,
        # a raw §...§ token must not be shown.
        s = ScrubSession()
        out = s.rehydrate("as §EMAIL_7§ mentioned")
        assert "§" not in out
        assert "[redacted]" in out

    def test_sessions_do_not_share_mappings(self):
        a, b = ScrubSession(), ScrubSession()
        scrubbed = a.scrub("ping bob@corp.com")
        # b has never seen this value, so it must not be able to restore it.
        assert "bob@corp.com" not in b.rehydrate(scrubbed)


# ── StreamRehydrator ─────────────────────────────────────────────────────────


class TestStreamRehydrator:
    def _session_with(self, text):
        s = ScrubSession()
        return s, s.scrub(text)

    def test_passes_through_text_with_no_placeholders(self):
        s = ScrubSession()
        r = StreamRehydrator(s)
        assert r.feed("hello ") + r.feed("world") + r.flush() == "hello world"

    def test_restores_a_placeholder_split_across_chunks(self):
        # This is the whole reason the buffer exists: a token boundary can land
        # in the middle of §EMAIL_1§, and neither half is restorable alone.
        s, scrubbed = self._session_with("mail bob@corp.com now")
        r = StreamRehydrator(s)

        out = "".join(r.feed(ch) for ch in scrubbed) + r.flush()
        assert out == "mail bob@corp.com now"

    def test_restores_when_split_at_every_possible_offset(self):
        s, scrubbed = self._session_with("mail bob@corp.com now")
        expected = "mail bob@corp.com now"

        for cut in range(len(scrubbed) + 1):
            r = StreamRehydrator(s)
            out = r.feed(scrubbed[:cut]) + r.feed(scrubbed[cut:]) + r.flush()
            assert out == expected, f"split at {cut} produced {out!r}"

    def test_never_emits_a_partial_placeholder(self):
        s, scrubbed = self._session_with("mail bob@corp.com now")
        r = StreamRehydrator(s)

        emitted = []
        for ch in scrubbed:
            emitted.append(r.feed(ch))
        # Before flush, nothing emitted may contain a stray marker.
        assert "§" not in "".join(emitted)

    def test_flush_drops_a_dangling_partial_at_end_of_stream(self):
        s = ScrubSession()
        r = StreamRehydrator(s)
        r.feed("done §EMA")
        assert "§" not in r.flush()

    def test_flush_is_idempotent(self):
        s = ScrubSession()
        r = StreamRehydrator(s)
        r.feed("hello")
        r.flush()
        assert r.flush() == ""

    def test_section_references_survive(self):
        # "§5" is a legitimate section marker, not a placeholder fragment.
        s = ScrubSession()
        r = StreamRehydrator(s)
        assert r.feed("see §5 of the contract") + r.flush() == "see §5 of the contract"
