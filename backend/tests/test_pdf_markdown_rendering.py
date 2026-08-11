"""Tests for pdf_skill.py's markdown-to-reportlab conversion — reportlab's
Paragraph interprets text as restricted XML/HTML-like markup, not markdown.
Confirmed via a real generated PDF: "**pc wins here, hard**" appeared with
literal asterisks instead of actual bold text. Also tests XML-escaping,
since unescaped <, >, & in ordinary prose would otherwise be misread as
XML tags/entities by reportlab."""
from skills.pdf_skill import _markdown_line_to_reportlab


class TestMarkdownLineToReportlab:
    def test_bold_markdown_converts_to_reportlab_bold_tag(self):
        assert _markdown_line_to_reportlab("**pc wins here, hard**") == "<b>pc wins here, hard</b>"

    def test_inline_bold_within_a_sentence(self):
        result = _markdown_line_to_reportlab("phones though - they're **optimized** for what they do.")
        assert result == "phones though - they're <b>optimized</b> for what they do."

    def test_multiple_bold_spans_in_one_line(self):
        result = _markdown_line_to_reportlab("**pc** vs **phone**: it depends")
        assert result == "<b>pc</b> vs <b>phone</b>: it depends"

    def test_plain_text_is_unchanged(self):
        assert _markdown_line_to_reportlab("just a normal sentence") == "just a normal sentence"

    def test_bullet_marker_converts_to_bullet_character(self):
        result = _markdown_line_to_reportlab("- coding, 3d work: **pc**")
        assert result == "• coding, 3d work: <b>pc</b>"

    def test_xml_special_characters_are_escaped(self):
        assert _markdown_line_to_reportlab("cost < $1000") == "cost &lt; $1000"
        assert _markdown_line_to_reportlab("AT&T plans") == "AT&amp;T plans"
        assert _markdown_line_to_reportlab("x > y") == "x &gt; y"

    def test_escaping_happens_before_bold_conversion_not_after(self):
        # If escaping ran after bold conversion, our own <b>/</b> tags would
        # get escaped into &lt;b&gt; and show up as literal text.
        result = _markdown_line_to_reportlab("**bold with < in it**")
        assert result == "<b>bold with &lt; in it</b>"
        assert "&lt;b&gt;" not in result

    def test_empty_string(self):
        assert _markdown_line_to_reportlab("") == ""
