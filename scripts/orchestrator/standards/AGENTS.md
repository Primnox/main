# Engineering standards

You are implementing a single, self-contained work order. The specification is
in `TASK.md`. It is complete on its own — there is no wider system for you to
ask about, and no repository beyond this directory.

## Deliverable

- Produce the files named in the specification's **Deliverables** section, at
  exactly those paths, relative to this directory.
- Write complete implementations. No `TODO`, no `...`, no placeholder bodies,
  no "implementation left as an exercise".
- If the specification is ambiguous, choose the simpler reading, implement it,
  and record the choice in `NOTES.md` under `## Assumptions`.

## Constraints

- **No hardcoded values.** Anything a caller might reasonably want to change —
  URLs, ports, paths, limits, timeouts, thresholds, model names, feature flags,
  colours, copy — is a parameter, a constructor argument, or a field read from
  an injected config object. Defaults live in one named constant block at the
  top of the module, never inline at the point of use.
- **No network calls at import time**, and no reads of ambient global state.
  Dependencies arrive through parameters.
- **No new third-party dependencies** unless the specification names them.
- Match the language, style, and module format the specification asks for.
- Public functions and exported types get a one-line doc comment stating what
  they do and what they assume. Skip commentary on obvious lines.

## Verification

- Include the tests the specification asks for. If it asks for none, still make
  the code runnable and state in `NOTES.md` how you checked it.
- Do not claim something passes unless you ran it.

## Output contract

When you finish, write `NOTES.md` in this directory with exactly these sections:

```
## What I built
## Assumptions
## Public interface
## How to verify
## Not done
```

`## Not done` is required. If everything in the specification is complete,
write `Nothing outstanding.` under it. Never silently drop scope.
