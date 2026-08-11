"""Extraction for the structured response block convention (see
system_prompts.py's RESPONSE FORMATTING guidance): the model may embed
fenced ```primnox-card / ```primnox-buttons JSON blocks in an otherwise
plain-text/markdown reply. Pulled out of core.py as a pure function so it's
testable without spinning up PrimnoxCore's full pipeline.
"""
import json
import re

from logger import get_logger

log = get_logger("response_blocks")

_BLOCK_PATTERN = re.compile(r"```primnox-(card|buttons)\n(.*?)\n```", re.DOTALL)


def extract_blocks(text: str) -> tuple[str, list[dict]]:
    """Returns (cleaned_text, blocks). Malformed JSON inside a recognized
    fence is logged and dropped (the surrounding fence is still stripped
    from the visible text — a broken block shouldn't leak raw JSON/fence
    syntax into the chat)."""
    if not text or "```primnox-" not in text:
        return text, []

    blocks: list[dict] = []

    def _extract(match: re.Match) -> str:
        block_type = match.group(1)
        raw_json = match.group(2)
        try:
            parsed = json.loads(raw_json)
            parsed["type"] = block_type
            blocks.append(parsed)
        except Exception as e:
            log.warning(f"Failed to parse primnox-{block_type} block: {e}")
        return ""

    cleaned = _BLOCK_PATTERN.sub(_extract, text).strip()
    return cleaned, blocks
