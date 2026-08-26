"""Decision rules for response adequacy (ARCH §5.7–§5.8).

Given an observation and what the model did with it, is that response
correct? The decision is not subjective. It has two cases:

  SHOULD_ANSWER_FROM_OBSERVATION: The observation contains the answer.
  The model's job is to extract and articulate it, not to fetch. If the
  model calls a tool instead, that is a failure — it paid the cost of a
  round trip when the cost had already been paid to compact.

  MUST_FETCH_WHEN_ANSWER_ABSENT: The observation is partial. The answer
  is definitely not in the observation. The model's job is to notice that
  gap and call the tool to fill it. If the model generates an answer from
  an incomplete observation, that is a failure — it is confident prose
  about something it cannot possibly know.

These are the two measurements that compaction must satisfy. Both have to
hold, or the saving is fake.

A decision rule takes:
  - The scenario (what is the model being asked, and is the answer in the observation?)
  - The response (what did the model actually do?)

And returns whether the response is appropriate.
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Optional

from . import response_primitives as rp


class Scenario(enum.Enum):
    """What the model is being tested on."""

    ANSWERABLE = "answerable"
    """The observation contains everything needed to answer the question."""

    INCOMPLETE = "incomplete"
    """The observation is partial; the answer requires fetching."""


class Verdict(enum.Enum):
    """The correctness judgment."""

    CORRECT = "correct"
    """The response is appropriate for this scenario."""

    WRONG_TYPE = "wrong_type"
    """The response shape is wrong for the scenario."""

    WRONG_TOOL = "wrong_tool"
    """Correct to fetch, but called the wrong tool."""

    WRONG_HANDLE = "wrong_handle"
    """Fetched correctly but with the wrong reference/handle."""

    MALFORMED = "malformed"
    """Tool call had unparseable arguments."""

    SILENT = "silent"
    """No response or empty response."""


@dataclasses.dataclass(frozen=True)
class Decision:
    """A rule's judgment of whether a response is correct."""

    verdict: Verdict
    """The correctness verdict."""

    reasoning: str
    """Why the verdict was rendered."""

    response_primitive: rp.ResponsePrimitive
    """The extracted response for reference."""

    @property
    def is_correct(self) -> bool:
        """Whether the response satisfies its scenario."""
        return self.verdict == Verdict.CORRECT


class Rule:
    """Decision logic for observation-sufficiency scenarios."""

    def __init__(
        self,
        scenario: Scenario,
        expected_tool: Optional[str] = None,
        expected_handle: Optional[str] = None,
        validate_tool_names: bool = True,
    ):
        """Set up a rule for a given scenario.

        Args:
            scenario: What is the model being tested on?
            expected_tool: If fetching is required, what tool should be called?
            expected_handle: If fetching, what handle should be passed?
            validate_tool_names: If False, extract tool patterns without requiring
                               them to be in the registered tool set. Useful for
                               testing when the tool registry is empty.
        """
        self.scenario = scenario
        self.expected_tool = expected_tool
        self.expected_handle = expected_handle
        self.validate_tool_names = validate_tool_names

    def evaluate(self, response: str) -> Decision:
        """Judge whether a response is appropriate for this scenario.

        Args:
            response: The model's raw text reply.

        Returns:
            A Decision with the verdict and reasoning.
        """
        primitive = rp.extract(response, validate_tool_names=self.validate_tool_names)

        if self.scenario == Scenario.ANSWERABLE:
            return self._evaluate_answerable(primitive)
        elif self.scenario == Scenario.INCOMPLETE:
            return self._evaluate_incomplete(primitive)

        return Decision(
            verdict=Verdict.SILENT,
            reasoning="Unknown scenario",
            response_primitive=primitive,
        )

    def _evaluate_answerable(self, primitive: rp.ResponsePrimitive) -> Decision:
        """When the observation is complete, the model should answer directly.

        Correct: DIRECT_ANSWER with relevant content.
        Wrong: Tool calls, silence, or prose that only theorizes.
        """
        if primitive.type == rp.ResponseType.EMPTY_OR_SILENCE:
            return Decision(
                verdict=Verdict.SILENT,
                reasoning="No response provided",
                response_primitive=primitive,
            )

        if primitive.type == rp.ResponseType.DIRECT_ANSWER:
            return Decision(
                verdict=Verdict.CORRECT,
                reasoning="Model answered directly from available information",
                response_primitive=primitive,
            )

        if primitive.has_tool_call:
            return Decision(
                verdict=Verdict.WRONG_TYPE,
                reasoning=(
                    f"Model called a tool ({primitive.first_call.name if primitive.first_call else 'unknown'}) "
                    f"when the answer was in the observation. This costs a round trip."
                ),
                response_primitive=primitive,
            )

        if primitive.type == rp.ResponseType.PROSE_WITH_TOOL_MENTION:
            return Decision(
                verdict=Verdict.WRONG_TYPE,
                reasoning="Model narrated calling a tool without actually calling it",
                response_primitive=primitive,
            )

        return Decision(
            verdict=Verdict.WRONG_TYPE,
            reasoning=f"Unexpected response type: {primitive.type.value}",
            response_primitive=primitive,
        )

    def _evaluate_incomplete(self, primitive: rp.ResponsePrimitive) -> Decision:
        """When the observation is partial, the model must fetch.

        Correct: Calls expected_tool with expected_handle.
        Wrong: No fetch, wrong tool, wrong handle, or invalid arguments.
        """
        if primitive.type == rp.ResponseType.EMPTY_OR_SILENCE:
            return Decision(
                verdict=Verdict.SILENT,
                reasoning="Model gave no response when a fetch was required",
                response_primitive=primitive,
            )

        if primitive.type == rp.ResponseType.DIRECT_ANSWER:
            return Decision(
                verdict=Verdict.WRONG_TYPE,
                reasoning=(
                    "Model answered from an incomplete observation. "
                    "The missing detail was not available, so this is confident prose about unknown information."
                ),
                response_primitive=primitive,
            )

        if not primitive.has_tool_call:
            return Decision(
                verdict=Verdict.WRONG_TYPE,
                reasoning="Model did not call a tool when the observation was incomplete",
                response_primitive=primitive,
            )

        # The model did call a tool. Check if it is the right one.
        if not primitive.first_call:
            return Decision(
                verdict=Verdict.SILENT,
                reasoning="Tool call extracted but no first call found",
                response_primitive=primitive,
            )

        if primitive.first_call.name != self.expected_tool:
            return Decision(
                verdict=Verdict.WRONG_TOOL,
                reasoning=(
                    f"Model called {primitive.first_call.name}, "
                    f"but should have called {self.expected_tool}"
                ),
                response_primitive=primitive,
            )

        # Right tool. Check the arguments.
        if not primitive.first_call.valid:
            return Decision(
                verdict=Verdict.MALFORMED,
                reasoning=(
                    f"Tool {primitive.first_call.name} was called with invalid JSON: "
                    f"{primitive.first_call.arguments[:100]}"
                ),
                response_primitive=primitive,
            )

        # Check if the handle/reference is correct
        if self.expected_handle and not primitive.first_call.mentions(self.expected_handle):
            return Decision(
                verdict=Verdict.WRONG_HANDLE,
                reasoning=(
                    f"Tool {primitive.first_call.name} was called, "
                    f"but did not reference the expected handle {self.expected_handle}"
                ),
                response_primitive=primitive,
            )

        return Decision(
            verdict=Verdict.CORRECT,
            reasoning=(
                f"Model correctly called {self.expected_tool} "
                f"to fetch the missing information"
            ),
            response_primitive=primitive,
        )


class Scorer:
    """Aggregate scoring across multiple trials."""

    def __init__(self):
        self.verdicts: list[Verdict] = []
        self.decisions: list[Decision] = []

    def record(self, decision: Decision) -> None:
        """Add a decision to the score."""
        self.verdicts.append(decision.verdict)
        self.decisions.append(decision)

    @property
    def count_correct(self) -> int:
        """How many trials were correct."""
        return sum(1 for v in self.verdicts if v == Verdict.CORRECT)

    @property
    def count_total(self) -> int:
        """Total trials recorded."""
        return len(self.verdicts)

    @property
    def accuracy(self) -> float:
        """Fraction correct (0.0 to 1.0)."""
        return self.count_correct / self.count_total if self.count_total > 0 else 0.0

    def breakdown(self) -> dict[Verdict, int]:
        """Count of each verdict type."""
        counts = {v: 0 for v in Verdict}
        for verdict in self.verdicts:
            counts[verdict] += 1
        return counts

    def report(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Scored {self.count_total} trials",
            f"  Correct: {self.count_correct}/{self.count_total} ({self.accuracy:.0%})",
        ]
        bd = self.breakdown()
        # Sort by count descending, then by verdict name for stability
        for verdict, count in sorted(bd.items(), key=lambda x: (-x[1], x[0].value)):
            if count > 0 and verdict != Verdict.CORRECT:
                lines.append(f"  {verdict.value}: {count}")
        return "\n".join(lines)


__all__ = [
    "Scenario",
    "Verdict",
    "Decision",
    "Rule",
    "Scorer",
]
