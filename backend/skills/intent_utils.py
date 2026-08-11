"""Tolerant creation-intent detection — a fallback for skill routing and for
skills that need to tell "make me one" apart from "read/explain this one".

Exact trigger-phrase matching (skill_router.py's TRIGGER_MAP) is brittle:
"craete me a pdf where..." doesn't match "create pdf"/"create a pdf"/"make a
pdf" because of a typo and an inserted word, even though the intent is
completely unambiguous to a human. This checks for an artifact word (e.g.
"pdf") plus a creation verb ANYWHERE in the message, using fuzzy per-word
comparison (difflib, the same tool memory.py already uses for dedup) so a
misspelled verb like "craete" still matches "create".
"""
from difflib import SequenceMatcher

# Exact forms first (covers common inflections precisely, zero false-positive
# risk) — fuzzy matching against the base forms below only has to catch
# genuine typos ("craete"), not conjugation, which keeps the similarity
# threshold tight without missing "creating"/"created"/etc.
_CREATION_VERB_FORMS = (
    "create", "creates", "created", "creating",
    "generate", "generates", "generated", "generating",
    "make", "makes", "made", "making",
    "build", "builds", "built", "building",
    "write", "writes", "wrote", "written", "writing",
    "draft", "drafts", "drafted", "drafting",
    "produce", "produces", "produced", "producing",
)
_CREATION_VERB_BASE_FORMS = ("create", "generate", "make", "build", "write", "draft", "produce")

_VERB_SIMILARITY_THRESHOLD = 0.82


def _words(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text.lower()).split()


def _fuzzy_contains_verb(words: list[str]) -> bool:
    if any(w in _CREATION_VERB_FORMS for w in words):
        return True
    for word in words:
        for verb in _CREATION_VERB_BASE_FORMS:
            if SequenceMatcher(None, word, verb).ratio() >= _VERB_SIMILARITY_THRESHOLD:
                return True
    return False


def expresses_creation_intent(text: str, artifact_words: tuple[str, ...]) -> bool:
    """True if `text` mentions one of `artifact_words` (e.g. "pdf") together
    with a creation-intent verb anywhere in the message — order-independent
    and tolerant of a misspelled verb, unlike an exact trigger-phrase match."""
    if not text or not artifact_words:
        return False
    lowered = text.lower()
    if not any(a in lowered for a in artifact_words):
        return False
    return _fuzzy_contains_verb(_words(text))
