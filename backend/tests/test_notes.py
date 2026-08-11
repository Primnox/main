"""Tests for the notes search/action-item fixes: FTS5 replacing an
unindexable LIKE scan, the broken ".\\n" action-item splitter, and the
targeted title-existence check meeting_recorder relies on.
"""
import pytest

import notes_manager as notes


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(notes, "DB_PATH", tmp_path / "test_notes.db")
    notes.init_db()
    return notes


class TestSearchNotes:
    def test_finds_note_by_body_text(self, db):
        db.add_note("Discussed the Q3 roadmap and budget planning.", title="Planning Meeting")
        results = db.search_notes("roadmap")
        assert any(r["title"] == "Planning Meeting" for r in results)

    def test_finds_note_by_title(self, db):
        db.add_note("some body text", title="Nothing ROM Port Notes")
        results = db.search_notes("nothing rom")
        assert len(results) == 1

    def test_no_match_returns_empty(self, db):
        db.add_note("unrelated content", title="Untitled Note")
        assert db.search_notes("xyzxyz-nomatch") == []

    def test_empty_query_returns_empty(self, db):
        db.add_note("some text", title="A Note")
        assert db.search_notes("") == []

    def test_pinned_notes_rank_first(self, db):
        n1 = db.add_note("budget review budget review", title="Old Budget Note")
        n2 = db.add_note("budget review", title="New Budget Note")
        db.toggle_pin_note(n1["id"], True)
        results = db.search_notes("budget")
        assert results[0]["id"] == n1["id"]

    def test_existing_notes_are_backfilled_into_fts(self, tmp_path, monkeypatch):
        # Simulate a note written before FTS existed by inserting directly,
        # then re-running init_db() (which runs the 'rebuild' backfill).
        monkeypatch.setattr(notes, "DB_PATH", tmp_path / "legacy.db")
        notes.init_db()
        conn = notes.get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO notes (title, text, timestamp) VALUES (?, ?, ?)",
            ("Legacy Note", "some legacy content about servers", "2020-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        notes.init_db()  # re-run migration/backfill

        results = notes.search_notes("servers")
        assert any(r["title"] == "Legacy Note" for r in results)


class TestExtractActionItems:
    def test_extracts_todo_style_line(self, db):
        text = "Meeting recap.\nTODO: send the follow-up email tomorrow."
        items = db.extract_action_items(text)
        assert any("follow-up email" in i for i in items)

    def test_extracts_sentence_without_literal_period_newline(self, db):
        # The old splitter required ".\n" (period immediately followed by
        # newline) — real prose almost never has that. This is plain prose.
        text = "We need to finish the report by Friday. Everyone agreed the plan looks good."
        items = db.extract_action_items(text)
        assert any("finish the report" in i for i in items)

    def test_does_not_false_positive_on_do_substring(self, db):
        # "document" and "adopt" contain "do" as a substring but aren't
        # action items — word-boundary matching should not flag this.
        text = "The document describes the new adoption process in detail."
        assert db.extract_action_items(text) == []

    def test_empty_text_returns_empty(self, db):
        assert db.extract_action_items("") == []


class TestNoteTitleExists:
    def test_true_when_present(self, db):
        db.add_note("body", title="Meeting: Standup")
        assert db.note_title_exists("Meeting: Standup") is True

    def test_false_when_absent(self, db):
        assert db.note_title_exists("Meeting: Nonexistent") is False


class TestWikiLinks:
    def test_add_note_resolves_wikilink_to_existing_note(self, db):
        target = db.add_note("the actual roadmap content", title="Project Roadmap")
        source = db.add_note("see [[Project Roadmap]] for details", title="Kickoff Notes")

        links = db.get_note_links(source["id"])
        assert links == [{"id": target["id"], "title": "Project Roadmap"}]

    def test_wikilink_match_is_case_insensitive(self, db):
        target = db.add_note("x", title="Project Roadmap")
        source = db.add_note("see [[project roadmap]]", title="Kickoff")
        assert [l["id"] for l in db.get_note_links(source["id"])] == [target["id"]]

    def test_unresolved_wikilink_is_silently_skipped(self, db):
        source = db.add_note("see [[Nonexistent Note]] for details", title="Kickoff")
        assert db.get_note_links(source["id"]) == []

    def test_backlinks_are_the_reverse_of_links(self, db):
        target = db.add_note("x", title="Project Roadmap")
        source = db.add_note("see [[Project Roadmap]]", title="Kickoff")

        assert [b["id"] for b in db.get_backlinks(target["id"])] == [source["id"]]
        assert db.get_backlinks(source["id"]) == []

    def test_update_note_replaces_links_not_accumulates(self, db):
        a = db.add_note("x", title="Note A")
        b = db.add_note("x", title="Note B")
        source = db.add_note("see [[Note A]]", title="Source")
        assert [l["id"] for l in db.get_note_links(source["id"])] == [a["id"]]

        db.update_note(source["id"], "Source", "see [[Note B]] now", project=None, parent_id=None)
        assert [l["id"] for l in db.get_note_links(source["id"])] == [b["id"]]

    def test_deleting_a_note_removes_its_links_both_directions(self, db):
        target = db.add_note("x", title="Project Roadmap")
        source = db.add_note("see [[Project Roadmap]]", title="Kickoff")

        db.delete_note(target["id"])
        assert db.get_note_links(source["id"]) == []

    def test_search_note_titles_matches_substring(self, db):
        db.add_note("x", title="Project Roadmap")
        db.add_note("x", title="Unrelated Note")
        results = db.search_note_titles("roadmap")
        assert [r["title"] for r in results] == ["Project Roadmap"]

    def test_search_note_titles_empty_query_returns_recent(self, db):
        db.add_note("x", title="First")
        db.add_note("x", title="Second")
        results = db.search_note_titles("")
        assert {r["title"] for r in results} == {"First", "Second"}


class TestParseNoteJsonResponse:
    """Backs the AI note builder (/api/notes/generate) — turns a prompt into
    a full note the way Notion AI's "ask AI to write" does. This is the
    fragile bit: parsing whatever JSON-ish text the model actually returns,
    including the ```json fence it adds despite being told not to."""

    def test_parses_clean_json(self):
        result = notes.parse_note_json_response('{"title": "Meeting Notes", "body": "# Agenda\\n- item one"}')
        assert result == {"title": "Meeting Notes", "body": "# Agenda\n- item one"}

    def test_strips_json_code_fence(self):
        raw = '```json\n{"title": "Brief", "body": "content here"}\n```'
        result = notes.parse_note_json_response(raw)
        assert result == {"title": "Brief", "body": "content here"}

    def test_strips_bare_code_fence(self):
        raw = '```\n{"title": "Brief", "body": "content here"}\n```'
        result = notes.parse_note_json_response(raw)
        assert result == {"title": "Brief", "body": "content here"}

    def test_missing_title_defaults_to_untitled(self):
        result = notes.parse_note_json_response('{"body": "just content"}')
        assert result["title"] == "Untitled"

    def test_blank_title_defaults_to_untitled(self):
        result = notes.parse_note_json_response('{"title": "   ", "body": "just content"}')
        assert result["title"] == "Untitled"

    def test_raises_on_invalid_json(self):
        import pytest as _pytest
        with _pytest.raises(ValueError, match="not valid JSON"):
            notes.parse_note_json_response("this is not json at all")

    def test_raises_on_empty_body(self):
        import pytest as _pytest
        with _pytest.raises(ValueError, match="no note body"):
            notes.parse_note_json_response('{"title": "Empty", "body": ""}')

    def test_raises_on_missing_body_key(self):
        import pytest as _pytest
        with _pytest.raises(ValueError, match="no note body"):
            notes.parse_note_json_response('{"title": "Empty"}')


class TestGetNoteById:
    """Backs the AI note builder's "edit this note" path — it needs the
    existing title/content/project/parent_id to give the model context and
    to preserve fields the user didn't ask to change."""

    def test_returns_the_note(self, db):
        created = db.add_note("original content", title="My Note", project="Work")
        fetched = db.get_note_by_id(created["id"])
        assert fetched == {
            "id": created["id"], "title": "My Note", "text": "original content",
            "project": "Work", "parent_id": None,
        }

    def test_returns_none_for_missing_id(self, db):
        assert db.get_note_by_id(999999) is None
