"""Primnox Crucible — a certification suite, not a feature suite.

The verification layer under `tests/` asks "does this work". Crucible asks "what
does it take to break this", which is a different question and finds different
things. A feature test written by the person who wrote the feature tends to
exercise the path they had in mind; a torture test starts from the failure and
works backwards.

Three rules the whole design follows.

DETERMINISTIC. Every artifact is generated from a seed, so a 500-turn
conversation or a 50,000-node graph is byte-identical on the next machine and on
the next build. A benchmark that produces different inputs each run cannot tell
a regression from noise.

HONEST ABOUT ABSENCE. A module whose subsystem does not exist scores
NOT_APPLICABLE and says why. Scoring an absent subsystem — awarding zero, or
worse, awarding full marks because nothing failed — is how a certification
becomes theatre.

FAILURES ARE THE OUTPUT. The report is the deliverable. A green run that found
nothing is a weaker result than a red one that found something real, and the
suite is written to make the second outcome likely.
"""
from . import manifest, report, scoring  # noqa: F401

VERSION = "1.0.0"
