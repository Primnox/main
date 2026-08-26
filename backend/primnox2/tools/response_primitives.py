"""Response primitives — atomic classification of model responses (ARCH §5.7).

A model response in a tool-using context falls into one of a small set of
shapes. These are not judgment calls about quality or correctness; they are
measurements of *structure*: did the reply propose a tool, and if so, which
tool, and was the argument valid?

Each primitive is a fact that can be extracted from raw text. The primitives
then feed decision rules: when an observation is compacted, what shapes of
response are correct, and what shapes signal something went wrong?
"""
from __future__ import annotations

import dataclasses
import json
import re
from enum import Enum
from typing import Optional

from .registry import tool_names


class ResponseType(Enum):
    """Classification of model response structure."""

    DIRECT_ANSWER = "direct_answer"
    """Prose reply without a tool call — answer from available information."""

    TOOL_CALL = "tool_call"
    """A valid tool invocation within the grammar."""

    INVALID_TOOL_CALL = "invalid_tool_call"
    """Attempted tool invocation that fails parsing or references a nonexistent tool."""

    PROSE_WITH_TOOL_MENTION = "prose_with_tool_mention"
    """Narration that names a tool ("I would call read_result") without actually calling it."""

    EMPTY_OR_SILENCE = "empty_or_silence"
    """No response, or only whitespace."""

    MULTIPLE_CALLS = "multiple_calls"
    """More than one tool call in a single response."""


@dataclasses.dataclass(frozen=True)
class ToolCall:
    """A structured tool invocation extracted from response text."""

    name: str
    """The tool name, as named in the grammar."""

    arguments: str
    """The raw JSON argument block, unparsed."""

    arguments_parsed: Optional[dict] = None
    """Parsed JSON if valid; None otherwise."""

    start_pos: int = 0
    """Character offset where the call begins in the response."""

    end_pos: int = 0
    """Character offset where the call ends in the response."""

    @property
    def valid(self) -> bool:
        """Whether the arguments parse to valid JSON."""
        return self.arguments_parsed is not None

    def mentions(self, needle: str) -> bool:
        """Whether the argument block contains the given string.

        Used to check if a tool call references the right handle (e.g.,
        result_id in a read_result call).
        """
        return needle in self.arguments


@dataclasses.dataclass(frozen=True)
class ResponsePrimitive:
    """Atomic analysis of a model's response."""

    raw_text: str
    """The verbatim model output."""

    type: ResponseType
    """Classification of response structure."""

    tool_calls: tuple[ToolCall, ...] = ()
    """All extracted tool calls, in order of appearance."""

    prose_segments: tuple[str, ...] = ()
    """Text passages between/around tool calls (for PROSE_WITH_TOOL_MENTION)."""

    @property
    def has_tool_call(self) -> bool:
        """Whether any tool was invoked."""
        return self.type in (ResponseType.TOOL_CALL, ResponseType.MULTIPLE_CALLS)

    @property
    def first_call(self) -> Optional[ToolCall]:
        """The first tool call, if any."""
        return self.tool_calls[0] if self.tool_calls else None

    @property
    def all_calls_valid(self) -> bool:
        """Whether every tool call has valid JSON arguments."""
        return all(call.valid for call in self.tool_calls)


# Pattern for canonical tool blocks: <tool name="...">...</tool>
_TOOL_BLOCK = re.compile(r'<tool\s+name="([^"]+)"\s*>(.*?)</tool>', re.S)

# Variant: <tool_name>{...}</tool_name>
_VARIANT_TAG = re.compile(r'<(\w+)\s*>\s*(\{.*?\})\s*</\1\s*>', re.S)

# Variant: tool_name({...})
_FUNCTION_CALL = re.compile(r'\b(\w+)\s*\(\s*(\{.*?\})\s*\)', re.S)


def extract(response: str, validate_tool_names: bool = True) -> ResponsePrimitive:
    """Classify a model response and extract its structure.

    This is the universal analysis path: a response always produces a
    primitive, regardless of whether it is correct, well-formed, or helpful.

    Args:
        response: The model's raw text reply.
        validate_tool_names: If True, only extract calls to registered tools.
                           If False, extract anything tool-like. Useful for
                           testing when the tool registry is empty.
    """
    response = response or ""
    if not response or response.isspace():
        return ResponsePrimitive(
            raw_text=response,
            type=ResponseType.EMPTY_OR_SILENCE,
        )

    valid_names = set(tool_names()) if validate_tool_names else None
    calls: list[ToolCall] = []

    def _is_valid_tool_name(name: str) -> bool:
        """Check if a tool name should be extracted."""
        if valid_names is None:
            # No validation; extract anything that looks tool-like
            return True
        return name in valid_names

    # Extract from canonical grammar: <tool name="...">...</tool>
    for match in _TOOL_BLOCK.finditer(response):
        name, args = match.groups()
        if _is_valid_tool_name(name):
            parsed = _parse_json(args)
            calls.append(
                ToolCall(
                    name=name,
                    arguments=args,
                    arguments_parsed=parsed,
                    start_pos=match.start(),
                    end_pos=match.end(),
                )
            )

    # Extract from variant grammars only if no canonical matches (to avoid
    # double-counting if a response uses both). This keeps the "one true call"
    # case unambiguous.
    if not calls:
        for match in _VARIANT_TAG.finditer(response):
            name, args = match.groups()
            if _is_valid_tool_name(name):
                parsed = _parse_json(args)
                calls.append(
                    ToolCall(
                        name=name,
                        arguments=args,
                        arguments_parsed=parsed,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

    if not calls:
        for match in _FUNCTION_CALL.finditer(response):
            name, args = match.groups()
            if _is_valid_tool_name(name):
                parsed = _parse_json(args)
                calls.append(
                    ToolCall(
                        name=name,
                        arguments=args,
                        arguments_parsed=parsed,
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )

    # Classify based on what we found
    if calls:
        if len(calls) > 1:
            resp_type = ResponseType.MULTIPLE_CALLS
        elif any(call.valid for call in calls):
            resp_type = ResponseType.TOOL_CALL
        else:
            # Called a tool but arguments are malformed
            resp_type = ResponseType.INVALID_TOOL_CALL
    elif _mentions_tool(response, valid_names):
        # Prose that names a tool without calling it
        resp_type = ResponseType.PROSE_WITH_TOOL_MENTION
    else:
        # Plain answer
        resp_type = ResponseType.DIRECT_ANSWER

    # For prose-with-mention, extract segments
    prose_segments = ()
    if resp_type == ResponseType.PROSE_WITH_TOOL_MENTION:
        prose_segments = _extract_prose_segments(response)

    return ResponsePrimitive(
        raw_text=response,
        type=resp_type,
        tool_calls=tuple(calls),
        prose_segments=prose_segments,
    )


def _parse_json(text: str) -> Optional[dict]:
    """Try to parse a string as JSON, returning None if it fails."""
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _mentions_tool(text: str, valid_names: Optional[set[str]]) -> bool:
    """Check if prose mentions calling a tool without actually calling it.

    This looks for specific phrasings like "I would call" or "let me call"
    followed by a tool name, which indicate the model is narrating about a
    tool rather than actually invoking it.
    """
    text_lower = text.lower()

    # Phrases that indicate the model is talking about calling a tool
    # rather than actually invoking it. These are deliberately restrictive
    # to avoid false positives (e.g., prose that happens to mention "search").
    decision_phrases = [
        "i would call",
        "i should call",
        "let me call",
        "i'll call",
        "i could call",
        "need to call",
    ]

    # If no specific tool names are validated, just check for decision phrases
    if valid_names is None:
        valid_names = {"read_result", "run_shell", "run_python"}

    # Look for a decision phrase followed by a tool name
    for phrase in decision_phrases:
        if phrase in text_lower:
            # Check if any tool name follows the phrase
            for name in valid_names:
                # Tool name after the phrase, with word boundary
                pattern = f"{phrase} {name}"
                if pattern in text_lower:
                    return True
    return False


def _extract_prose_segments(text: str, max_segments: int = 3) -> tuple[str, ...]:
    """Extract narrative prose from a response that mentions but doesn't call tools.

    Returns up to max_segments pieces of the response that look like
    explanation or narrative, useful for understanding why the model thought
    it needed to (or was about to) call something.
    """
    # Remove tool block markers to get the prose
    text_without_calls = _TOOL_BLOCK.sub("", text)
    text_without_calls = _VARIANT_TAG.sub("", text_without_calls)
    text_without_calls = _FUNCTION_CALL.sub("", text_without_calls)

    # Split on multiple newlines and filter short pieces
    segments = [s.strip() for s in text_without_calls.split("\n\n")]
    segments = [s for s in segments if len(s) > 20]

    return tuple(segments[:max_segments])


__all__ = [
    "ResponseType",
    "ResponsePrimitive",
    "ToolCall",
    "extract",
]
