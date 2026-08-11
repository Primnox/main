"""Tests for response_blocks.py's fenced ```primnox-card / ```primnox-buttons
extraction — pulled out of core.py so it's testable without spinning up
PrimnoxCore's full pipeline."""
from response_blocks import extract_blocks


class TestExtractBlocks:
    def test_plain_text_with_no_blocks_is_unchanged(self):
        text = "just a normal reply, nothing special here."
        cleaned, blocks = extract_blocks(text)
        assert cleaned == text
        assert blocks == []

    def test_empty_string(self):
        assert extract_blocks("") == ("", [])

    def test_extracts_a_buttons_block(self):
        text = (
            "sure, want me to delete it?\n"
            "```primnox-buttons\n"
            '{"buttons": [{"label": "Yes", "action": "confirm"}, {"label": "No", "action": "cancel"}]}\n'
            "```"
        )
        cleaned, blocks = extract_blocks(text)
        assert "```primnox-buttons" not in cleaned
        assert "sure, want me to delete it?" in cleaned
        assert len(blocks) == 1
        assert blocks[0]["type"] == "buttons"
        assert blocks[0]["buttons"][0]["label"] == "Yes"

    def test_extracts_a_card_block(self):
        text = (
            "```primnox-card\n"
            '{"title": "14 duplicate files", "content": "2.4 GB can be recovered.", "actions": [{"label": "Review", "action": "review_duplicates"}]}\n'
            "```"
        )
        cleaned, blocks = extract_blocks(text)
        assert cleaned == ""
        assert blocks[0]["type"] == "card"
        assert blocks[0]["title"] == "14 duplicate files"
        assert blocks[0]["actions"][0]["action"] == "review_duplicates"

    def test_extracts_multiple_blocks_in_order(self):
        text = (
            "```primnox-card\n{\"title\": \"first\"}\n```\n"
            "some text between\n"
            "```primnox-buttons\n{\"buttons\": []}\n```"
        )
        cleaned, blocks = extract_blocks(text)
        assert "some text between" in cleaned
        assert [b["type"] for b in blocks] == ["card", "buttons"]

    def test_malformed_json_is_dropped_not_raised(self):
        text = "before\n```primnox-card\n{not valid json at all\n```\nafter"
        cleaned, blocks = extract_blocks(text)
        assert blocks == []
        assert "before" in cleaned and "after" in cleaned
        assert "```primnox-card" not in cleaned  # fence still stripped, no raw JSON leak

    def test_unrecognized_fence_language_is_left_alone(self):
        text = "```python\nprint('hi')\n```"
        cleaned, blocks = extract_blocks(text)
        assert cleaned == text
        assert blocks == []
