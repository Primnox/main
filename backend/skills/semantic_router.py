"""Model-based skill routing — picks a skill by what the user *meant*.

Why this exists: routing used to be `get_skill_for_trigger()`, a substring
match against hardcoded phrases ("create ppt", "make a presentation") plus a
fuzzy artifact+verb fallback. That fails in both directions and neither
failure is fixable by adding more phrases:

  - misses: "whip up a deck for tomorrow's standup" matches no phrase, so
    the request silently fell through to plain chat
  - false hits: any message containing "calendar" hijacked the turn for the
    calendar skill, however incidental the word was

The real signal is intent, which needs a model. This asks one — with a
deliberately tiny prompt (one line per skill) that demands a single bare
token back, so it stays reliable on small local models (Ollama/llama.cpp),
not just cloud ones.

Every answer is validated against the live catalog before it's trusted: a
model that invents a skill name, explains itself, or returns prose gets
treated as "no match" rather than routed somewhere wrong.
"""
from logger import get_logger

log = get_logger("skills.semantic")

# Anthropic's SKILL.md descriptions run several hundred characters and are
# written as prose ("Use this skill whenever... Do NOT use for..."). The
# leading sentence carries the routing signal; the rest is guidance for the
# skill's own execution and only bloats the classification prompt.
_DESCRIPTION_CAP = 220

_NO_MATCH = "NONE"

_SYSTEM = (
    "You are a request router. You are given a list of available skills and one user message. "
    f"Reply with EXACTLY ONE skill name copied verbatim from the list, or the single word {_NO_MATCH} "
    "if no skill fits. Output only that one token — no explanation, no punctuation, no formatting. "
    "Prefer " + _NO_MATCH + " for ordinary conversation, greetings, or questions you could just answer directly."
)


def _catalog() -> list[dict]:
    """Routable skills as [{name, description}]. Built from list_skills(), so
    it stays metadata-only — no skill module is imported just to route."""
    from skills.skill_router import list_skills
    out = []
    for entry in list_skills():
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        desc = (entry.get("description") or "").strip().replace("\n", " ")
        if len(desc) > _DESCRIPTION_CAP:
            desc = desc[:_DESCRIPTION_CAP].rsplit(" ", 1)[0] + "…"
        out.append({"name": name, "description": desc})
    return out


def _build_prompt(message: str, catalog: list[dict]) -> str:
    lines = [f"- {c['name']}: {c['description']}" for c in catalog]
    return (
        "Available skills:\n"
        + "\n".join(lines)
        + f"\n\nUser message:\n{message}\n\n"
        f"Which single skill should handle this? Reply with one name from the list above, or {_NO_MATCH}."
    )


def _match_name(reply: str, catalog: list[dict]) -> str | None:
    """Resolve a model reply to a catalog name, or None.

    Tolerates a model that wraps the answer ("Skill: pdf", "`pptx`") while
    still refusing anything ambiguous — if the reply mentions two different
    skills, or a name that isn't in the catalog, that's not a routing
    decision we should act on.
    """
    if not reply:
        return None
    normalized = "".join(c if c.isalnum() or c in "-_" else " " for c in reply.lower()).split()
    if not normalized:
        return None
    if _NO_MATCH.lower() in normalized:
        return None

    names = {c["name"].lower(): c["name"] for c in catalog}

    # Exact single-token reply is the expected, unambiguous case.
    if len(normalized) == 1 and normalized[0] in names:
        return names[normalized[0]]

    hits = {names[tok] for tok in normalized if tok in names}
    if len(hits) == 1:
        return next(iter(hits))
    return None


def classify(message: str) -> str | None:
    """The skill name that should handle `message`, or None for no match.

    Never raises and never blocks routing: any provider failure, malformed
    reply, or hallucinated name returns None so the caller can fall back to
    the keyword path instead of losing the turn entirely.
    """
    if not message or not message.strip():
        return None

    catalog = _catalog()
    if not catalog:
        return None

    try:
        from brain import think, resolve_think_text
        # resolve_think_text (not raw choices[]) because think() reports a
        # provider/key failure as a 200 whose content is a human-readable
        # apology — routing on that text would match nothing at best and
        # match a skill name mentioned inside the apology at worst.
        response = think(_build_prompt(message, catalog), system_override=_SYSTEM)
        reply = resolve_think_text(response, "")
    except Exception as e:
        log.warning(f"Semantic routing unavailable, falling back to trigger words: {e}")
        return None

    matched = _match_name(reply, catalog)
    log.info(f"Semantic route: {message[:40]!r} → {matched or _NO_MATCH}")
    return matched
