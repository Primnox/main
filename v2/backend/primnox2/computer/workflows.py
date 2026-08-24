"""Recorded desktop workflows — do this again, to a window that has moved.

A recording is a list of steps, and the whole design question is how a step
names the thing it acts on. Element refs cannot: `e12` means "the twelfth node
of that particular walk", so it is void the moment a dialog opens, a list
scrolls, or the application ships an update. Coordinates are worse — they
survive nothing, not even the window being resized.

So a step carries a selector (`tree.selector_for`): role, name, and ordinal,
which is how a person would say it. "The second button called Save" keeps
meaning the same thing across reads, window sizes, and most versions of the
application.

Replay is deliberately strict about two things:

  It re-reads the window between every step. A recording is not a macro
  played into the void — each step resolves against what is actually on
  screen at that moment, which is what lets it notice that the thing it
  wanted is gone instead of clicking where the thing used to be.

  It stops at the first step it cannot resolve. Skipping ahead would run the
  back half of a workflow against a state the front half never established,
  and the steps most worth recording are the ones with an order to them.

Recordings are stored as assets rather than in a table of their own: they are
small JSON documents the user should be able to read, export, and delete like
anything else Primnox produced, and inventing a table would mean inventing a
lifecycle for it too.
"""
from __future__ import annotations

import json
import time

from . import operations

SCHEMA = 1

# A recorded step is one of these. Anything not listed cannot be recorded,
# which is a deliberate whitelist rather than an oversight: `press_keys` with
# take_focus, for instance, interrupts the user, and a workflow that quietly
# steals focus on replay is not something to build by accident.
REPLAYABLE = frozenset({"click", "type", "scroll", "keys"})


def step_for(kind: str, selector: "dict | None", arguments: dict) -> dict:
    """One recorded step, checked against the operation table as it is made.

    The check belongs here rather than at replay because a recording is
    written once and run many times, often much later and often by somebody
    who did not record it. An undeclared verb caught now is a message to the
    person recording; caught at replay it is a workflow that stops halfway
    through, in front of somebody with no idea what it was meant to do.
    """
    operations.spec(kind)
    return {"kind": kind, "selector": selector, "arguments": arguments}


def operation_for(step: dict) -> operations.Operation:
    """A recorded step as the canonical operation it always was.

    The stored shape predates the operation table and is kept as it is,
    because recordings live in the user's assets and rewriting their format
    would strand every workflow anybody already made. The bridge is one
    function; the migration would be a lifecycle.
    """
    selector = step.get("selector")
    arguments = dict(step.get("arguments") or {})
    if selector:
        target = {"selector": selector}
    elif "x" in arguments and "y" in arguments:
        target = {"point": [arguments["x"], arguments["y"]]}
    else:
        target = None
    return operations.Operation(verb=step.get("kind", ""), target=target,
                                arguments=arguments)


def document(name: str, handle: str, label: str, steps: list[dict]) -> dict:
    return {
        "schema": SCHEMA,
        "name": name,
        "recorded_at": time.time(),
        # What it was recorded against, kept for the message shown when a
        # replay is pointed at something else. It is NOT a constraint: the
        # point of a selector-based recording is that it can run against a
        # second window of the same application.
        "recorded_on": {"handle": handle, "label": label},
        "steps": steps,
    }


def to_bytes(doc: dict) -> bytes:
    return json.dumps(doc, indent=2).encode("utf-8")


def parse(raw: bytes | str) -> dict:
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"that is not a readable workflow ({exc})")
    if not isinstance(doc, dict) or "steps" not in doc:
        raise ValueError("that file does not contain a workflow")
    if doc.get("schema") != SCHEMA:
        raise ValueError(
            f"that workflow was recorded by a different version "
            f"(schema {doc.get('schema')!r}, this build reads {SCHEMA})")
    return doc


def describe(doc: dict) -> str:
    lines = [f"{doc.get('name', 'workflow')} — {len(doc.get('steps', []))} steps, "
             f"recorded on {doc.get('recorded_on', {}).get('label', 'an unknown window')}"]
    consequences: list[str] = []
    for index, step in enumerate(doc.get("steps", []), 1):
        selector = step.get("selector") or {}
        who = (f"{selector.get('role', '')} {selector.get('name', '')!r}".strip()
               if selector else "the window")
        lines.append(f"  {index}. {step['kind']} {who}")
        try:
            klass = operations.spec(step["kind"]).side_effect
        except (operations.UnknownVerb, KeyError):
            continue
        if operations.SEVERITY[klass] >= operations.SEVERITY[operations.DESTRUCTIVE]:
            consequences.append(f"step {index} ({step['kind']}) is {klass}")
    # Said before the workflow runs, not after. A recording is the one place a
    # user can read what is about to happen while there is still time to
    # decline it, and "4 steps" tells them nothing about whether one of them
    # presses Send.
    if consequences:
        lines.append("  " + "; ".join(consequences)
                     + " — Primnox cannot undo these.")
    return "\n".join(lines)
