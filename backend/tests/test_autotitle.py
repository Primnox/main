"""Conversations name themselves after their first message.

`rename_conversation` existed but only the manual-rename endpoint ever called
it, so every conversation kept the literal string "New Chat" for its whole life.
The sidebar became a column of identical rows: scrollable, not readable, and
search could not help because every title was the same word.
"""
from __future__ import annotations

import pytest

from primnox2.chat import ephemeral, turns


def title_of(conversation_id: str) -> str:
    """There is no single-conversation getter; the list is the read path."""
    for c in turns.list_conversations(limit=500):
        if c["id"] == conversation_id:
            return c["title"]
    raise AssertionError(f"conversation {conversation_id} not in the list")


@pytest.fixture(autouse=True)
def _clean():
    ephemeral.reset()
    yield
    ephemeral.reset()


# ── the derivation ───────────────────────────────────────────────────────────

def test_a_short_message_becomes_the_title_verbatim():
    assert turns.title_from("Convert this deck to HTML") == "Convert this deck to HTML"


def test_a_long_message_is_cut_at_a_word_boundary():
    """A mid-word cut reads as a truncation bug rather than as a title."""
    text = ("How do I convert a PowerPoint presentation into an animated "
            "HTML deck that runs offline in a browser")
    title = turns.title_from(text)
    assert len(title) <= 61                      # 60 plus the ellipsis
    assert title.endswith("…")
    assert not title[:-1].endswith(" ")
    # The character before the ellipsis must end a whole word.
    assert text.startswith(title[:-1])
    assert text[len(title) - 1] in " " or len(title) - 1 >= len(text)


def test_newlines_and_runs_of_space_collapse():
    """A pasted traceback must not put a newline in the sidebar."""
    assert turns.title_from("line one\n\n   line   two") == "line one line two"


def test_an_empty_message_keeps_the_default():
    assert turns.title_from("   ") == turns.DEFAULT_TITLE
    assert turns.title_from("") == turns.DEFAULT_TITLE


# ── the guard ────────────────────────────────────────────────────────────────

def test_the_first_message_names_the_conversation():
    conv = turns.create_conversation()
    assert conv["title"] == turns.DEFAULT_TITLE
    turns.create_turn(conv["id"], "Summarise the battery report")
    assert title_of(conv["id"]) == "Summarise the battery report"


def test_the_second_message_does_not_rename_it():
    """The name the first message earned has to survive the rest of the chat."""
    conv = turns.create_conversation()
    turns.create_turn(conv["id"], "First question about batteries")
    turns.create_turn(conv["id"], "Now something completely different")
    assert title_of(conv["id"]) == "First question about batteries"


def test_a_manual_rename_is_never_overwritten():
    """The strongest guarantee here: a title the user chose is theirs."""
    conv = turns.create_conversation()
    turns.rename_conversation(conv["id"], "Battery research")
    turns.create_turn(conv["id"], "Some entirely unrelated opening line")
    assert title_of(conv["id"]) == "Battery research"


def test_maybe_autotitle_reports_no_change_when_it_declines():
    conv = turns.create_conversation()
    assert turns.maybe_autotitle(conv["id"], "First") == "First"
    assert turns.maybe_autotitle(conv["id"], "Second") is None


def test_an_unknown_conversation_is_declined_not_created():
    assert turns.maybe_autotitle("conv_does_not_exist", "hello") is None


# ── incognito ────────────────────────────────────────────────────────────────

def test_an_incognito_conversation_is_titled_in_memory():
    """It has no row to update, and it still has to be findable in the list
    while it exists."""
    conv = turns.create_conversation(incognito=True)
    turns.create_turn(conv["id"], "Off the record question")
    assert ephemeral.conversation(conv["id"])["title"] == "Off the record question"


def test_incognito_also_respects_a_manual_rename():
    conv = turns.create_conversation(incognito=True)
    turns.rename_conversation(conv["id"], "Kept name")
    turns.create_turn(conv["id"], "Something else entirely")
    assert ephemeral.conversation(conv["id"])["title"] == "Kept name"
