"""Tests for ppt_skill.py's markdown stripping — python-pptx text runs are
plain strings with no markup interpretation, so unlike pdf_skill.py's
conversion to real bold, this just removes the ** markers rather than
losing the ability to format at all (showing "pc wins" instead of the
literal "**pc wins**" a slide would otherwise contain verbatim)."""
from skills.ppt_skill import _strip_markdown


class TestStripMarkdown:
    def test_removes_bold_markers_keeping_the_text(self):
        assert _strip_markdown("**pc wins here, hard**") == "pc wins here, hard"

    def test_inline_bold_within_a_sentence(self):
        assert _strip_markdown("this is **really** important") == "this is really important"

    def test_multiple_bold_spans(self):
        assert _strip_markdown("**pc** vs **phone**") == "pc vs phone"

    def test_plain_text_is_unchanged(self):
        assert _strip_markdown("just a normal bullet point") == "just a normal bullet point"

    def test_empty_string(self):
        assert _strip_markdown("") == ""
