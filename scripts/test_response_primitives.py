"""Prototype: Response primitives and decision rules in action.

This demonstrates the two components working together to evaluate model
responses against expected behavior in observation-sufficiency testing.

Usage:
    python scripts/test_response_primitives.py

No dependencies outside the backend module.
"""
from __future__ import annotations

import sys
import pathlib

# Setup path
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from primnox2.tools import response_primitives as rp
from primnox2.tools import decision_rule as dr


# Test cases demonstrating response primitives
RESPONSE_EXAMPLES = [
    ("Direct answer", "The search matched in config/settings.py"),
    (
        "Correct tool call",
        '<tool name="read_result">{"result_id": "res_0123456789abcdef"}</tool>',
    ),
    (
        "Tool call via variant grammar",
        "read_result({\"result_id\": \"res_0123456789abcdef\"})",
    ),
    (
        "Narration without call",
        "I would call read_result to fetch the full output, but let me first check what we have.",
    ),
    ("Empty response", ""),
    ("Silence", "   \n\n   "),
    (
        "Multiple tool calls",
        '<tool name="run_shell">{"command": "ls"}</tool>\n'
        '<tool name="read_result">{"result_id": "res_1234"}</tool>',
    ),
    (
        "Invalid JSON in tool call",
        '<tool name="read_result">{bad json here}</tool>',
    ),
]


def demonstrate_primitives():
    """Show how response_primitives.extract() works."""
    print("=" * 70)
    print("RESPONSE PRIMITIVES - Classification Examples")
    print("=" * 70)

    for label, response_text in RESPONSE_EXAMPLES:
        print(f"\n[{label}]")
        print(f"Response: {response_text[:60]!r}")
        if len(response_text) > 60:
            print(f"          ...({len(response_text)} chars total)")

        # Use validate_tool_names=False for testing (tools aren't registered in test context)
        primitive = rp.extract(response_text, validate_tool_names=False)
        print(f"Type: {primitive.type.value}")

        if primitive.tool_calls:
            for i, call in enumerate(primitive.tool_calls, 1):
                print(f"  Tool {i}: {call.name}")
                print(f"    Valid: {call.valid}")
                print(f"    Args: {call.arguments[:50]!r}")
                if len(call.arguments) > 50:
                    print(f"           ...({len(call.arguments)} chars total)")

        if primitive.prose_segments:
            print(f"  Prose segments ({len(primitive.prose_segments)}):")
            for seg in primitive.prose_segments:
                print(f"    {seg[:50]!r}")

        print()


def demonstrate_decision_rules():
    """Show how decision_rule.Rule evaluates responses."""
    print("=" * 70)
    print("DECISION RULES - Scenario Evaluation")
    print("=" * 70)

    # Scenario 1: ANSWERABLE
    print("\n[Scenario: ANSWERABLE - observation contains the answer]")
    print("-" * 70)

    rule_answerable = dr.Rule(
        dr.Scenario.ANSWERABLE,
        validate_tool_names=False,
    )

    answerable_tests = [
        ("Direct answer", "The search matched in config/settings.py", True),
        (
            "Unnecessary fetch",
            '<tool name="read_result">{"result_id": "res_1234"}</tool>',
            False,
        ),
        ("Empty response", "", False),
        ("Narration", "I should read the result", False),
    ]

    for label, response, should_be_correct in answerable_tests:
        decision = rule_answerable.evaluate(response)
        is_correct = decision.is_correct
        status = "[OK]" if is_correct == should_be_correct else "[!!]"
        print(f"{status} {label:25s} | Verdict: {decision.verdict.value:15s}")
        print(f"       {decision.reasoning}")
        print()

    # Scenario 2: INCOMPLETE
    print("\n[Scenario: INCOMPLETE - observation is partial, needs fetch]")
    print("-" * 70)

    rule_incomplete = dr.Rule(
        dr.Scenario.INCOMPLETE,
        expected_tool="read_result",
        expected_handle="res_0123456789abcdef",
        validate_tool_names=False,
    )

    incomplete_tests = [
        (
            "Correct fetch",
            '<tool name="read_result">{"result_id": "res_0123456789abcdef"}</tool>',
            True,
        ),
        (
            "Answer from incomplete obs",
            "TIMEOUT_SECONDS is set to 4711 in the file",
            False,
        ),
        (
            "Wrong tool",
            '<tool name="run_shell">{"command": "grep TIMEOUT"}</tool>',
            False,
        ),
        (
            "Right tool, wrong handle",
            '<tool name="read_result">{"result_id": "res_wrong"}</tool>',
            False,
        ),
        (
            "No response",
            "",
            False,
        ),
    ]

    for label, response, should_be_correct in incomplete_tests:
        decision = rule_incomplete.evaluate(response)
        is_correct = decision.is_correct
        status = "[OK]" if is_correct == should_be_correct else "[!!]"
        print(f"{status} {label:25s} | Verdict: {decision.verdict.value:15s}")
        print(f"       {decision.reasoning}")
        print()


def demonstrate_scorer():
    """Show how Scorer aggregates decisions across trials."""
    print("=" * 70)
    print("SCORER — Aggregating Multiple Trials")
    print("=" * 70)

    rule = dr.Rule(
        dr.Scenario.INCOMPLETE,
        expected_tool="read_result",
        expected_handle="res_abc123",
        validate_tool_names=False,
    )

    scorer = dr.Scorer()

    # Simulate some trial results
    trials = [
        '<tool name="read_result">{"result_id": "res_abc123"}</tool>',  # Correct
        '<tool name="read_result">{"result_id": "res_abc123"}</tool>',  # Correct
        "Let me fetch this",  # Wrong type (narration)
        '<tool name="read_result">{"result_id": "res_abc123"}</tool>',  # Correct
        "I can answer this directly",  # Wrong type (answering incomplete)
    ]

    print(f"Running {len(trials)} trials...\n")

    for i, response in enumerate(trials, 1):
        decision = rule.evaluate(response)
        scorer.record(decision)
        print(f"Trial {i}: {decision.verdict.value:15s} — {decision.reasoning}")

    print("\n" + "-" * 70)
    print(scorer.report())
    print()


def demonstrate_integration():
    """Show how all three pieces fit together."""
    print("=" * 70)
    print("INTEGRATION — Full Workflow")
    print("=" * 70)

    print("""
Typical workflow in observation-sufficiency testing:

1. Setup
   - Create a test scenario (answerable or incomplete observation)
   - Prepare a rule for that scenario

2. Test Trial
   - Send a question to the model with the observation
   - Model replies with raw text

3. Evaluate
   - Extract the response primitive
   - Run the decision rule
   - Record the verdict

4. Aggregate
   - Score multiple trials
   - Check if sufficiency requirement is met

Example:
""")

    # Setup
    print("Step 1: Setup")
    rule = dr.Rule(
        dr.Scenario.INCOMPLETE,
        expected_tool="read_result",
        expected_handle="res_0123456789abcdef",
        validate_tool_names=False,
    )
    print(f"  Scenario: {rule.scenario.value}")
    print(f"  Expected tool: {rule.expected_tool}")
    print(f"  Expected handle: {rule.expected_handle}\n")

    # Test
    print("Step 2: Test Trial")
    model_reply = '<tool name="read_result">{"result_id": "res_0123456789abcdef"}</tool>'
    print(f"  Model replied: {model_reply!r}\n")

    # Evaluate
    print("Step 3: Evaluate")
    decision = rule.evaluate(model_reply)
    print(f"  Extracted primitive type: {decision.response_primitive.type.value}")
    print(f"  Tool calls found: {len(decision.response_primitive.tool_calls)}")
    print(f"  Verdict: {decision.verdict.value}")
    print(f"  Reasoning: {decision.reasoning}\n")

    # Aggregate
    print("Step 4: Aggregate (simulated)")
    scorer = dr.Scorer()
    for _ in range(5):
        decision = rule.evaluate(model_reply)
        scorer.record(decision)
    print(f"  {scorer.report()}\n")


if __name__ == "__main__":
    demonstrate_primitives()
    demonstrate_decision_rules()
    demonstrate_scorer()
    demonstrate_integration()

    print("=" * 70)
    print("All demonstrations complete.")
    print("=" * 70)
