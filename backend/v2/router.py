"""The retrieval router: which substrate answers this question.

Primnox does not dump everything it knows into the model. It decides what is
relevant, retrieves that, checks it, compresses it, and only then reasons.
This module is the deciding step.

    request → intent → M | S | G | R | T | H | C → retrieve → rank → context

The labels:

    M  memory        durable facts and the world model
    S  search        exact lexical lookup — strings, symbols, filenames
    G  graphify      structural relationships — callers, dependents, impact
    R  read          a specific file or artifact
    T  task state    what is being worked on right now
    H  history       episodic/temporal recall — what happened, and when
    C  combined      several of the above, named explicitly in `sources`

Two decisions are deliberate.

**The output is a discrete label, not JSON.** When the only thing being
decided is which retrieval path to take, a single letter is cheaper to
produce, impossible to malform, and trivial to benchmark. Verbose structured
output for a seven-way choice is paying reasoning tokens for formatting.

**The default classifier is deterministic.** Routing runs on every request,
so it must be fast, free and predictable. :func:`route` takes an optional
`classifier` hook for a tiny model, but a model is an override for hard
cases, not a dependency — and its answer is validated against the same label
set before it is trusted.

The hook this module removes is as important as what it adds: there is no
"Graphify before grep" step. Structural questions select G; lexical ones
never touch the graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

LABELS: dict[str, str] = {
    "M": "memory",
    "S": "search",
    "G": "graphify",
    "R": "read",
    "T": "task_state",
    "H": "history",
    "C": "combined",
}

# What the request wants done, which is separate from where the answer comes
# from: "remember that we use pnpm" and "what package manager do we use?"
# both concern memory, but only one of them writes.
INTENTS = {"retrieve", "remember", "forget", "act"}

# A second source is included when it scores at least this fraction of the
# winner. Set by hand against the worked examples in the architecture
# documents: high enough that a passing keyword does not drag an unrelated
# subsystem into every query, low enough that genuinely compound questions
# ("why did this break after I changed X?") come back combined.
COMBINED_MARGIN = 0.75

# Below this, the router is guessing. Callers can treat a low-confidence
# route as a reason to ask rather than retrieve.
LOW_CONFIDENCE = 0.35


@dataclass(frozen=True)
class Route:
    """A routing decision, with the evidence for it.

    `sources` is always populated, including for a single-source route, so
    that consumers never have to special-case "C" to know what to query.
    """

    label: str
    sources: list[str]
    intent: str = "retrieve"
    confidence: float = 0.0
    matched: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    requires_secret: bool = False
    classifier: str = "heuristic"

    @property
    def names(self) -> list[str]:
        """Human-readable source names, in priority order."""
        return [LABELS[s] for s in self.sources]

    def explain(self) -> str:
        """One line naming the decision and why it was made."""
        why = ", ".join(self.matched) if self.matched else "no strong signal"
        return f"{self.label} ({'+'.join(self.names)}) · {self.intent} · {why}"


@dataclass(frozen=True)
class _Signal:
    """One routing cue: a pattern, the label it argues for, and how strongly.

    `companions` are labels that join the route whenever this signal decides
    it, regardless of their own score. Some questions are inherently
    compound — "what breaks if I change this?" needs the graph, the tests
    that mention it, and what changed recently — and encoding that here is
    more honest than tuning a score margin until the right sources happen to
    fall out.
    """

    label: str
    name: str
    weight: float
    pattern: re.Pattern
    companions: tuple[str, ...] = ()


def _signal(label: str, name: str, weight: float, *patterns: str, companions: tuple[str, ...] = ()) -> _Signal:
    return _Signal(label, name, weight, re.compile("|".join(patterns), re.I), companions)


# Ordered by label for readability; order does not affect scoring.
_SIGNALS: list[_Signal] = [
    # ── History: when did something happen ────────────────────────────────
    _signal("H", "temporal", 3.0,
            r"\byesterday\b", r"\blast (week|night|month|friday|monday)\b",
            r"\bearlier (today|this week)\b", r"\bthis morning\b",
            r"\bwhen did i\b", r"\bhow long (have|did) i\b", r"\ba few days ago\b"),
    _signal("H", "past_activity", 2.0,
            r"\bwhat (was|were) i (doing|working on)\b", r"\bwhat (changed|happened)\b",
            r"\bwhat did i do\b", r"\bsince (yesterday|last)\b",
            r"\bafter i (changed|modified|updated)\b"),
    _signal("H", "recency", 1.0, r"\brecent(ly)?\b", r"\blately\b", r"\bthe other day\b"),

    # ── Graphify: structural relationships ────────────────────────────────
    _signal("G", "callers", 3.0,
            r"\bwhat calls\b", r"\bwho calls\b", r"\bcallers? of\b", r"\bcalled by\b",
            r"\bwhat uses\b", r"\bwhere is .* (called|used) from\b"),
    _signal("G", "dependencies", 3.0,
            r"\bdepends? on\b", r"\bdependents? of\b", r"\bwhat imports\b",
            r"\bimported by\b", r"\bdependency (graph|tree|chain)\b"),
    # Impact is never a graph-only question: what breaks is decided by
    # callers *and* the tests and config that mention it *and* what recently
    # changed around it.
    _signal("G", "impact", 3.0,
            r"\bwhat (could |would |might )?breaks?\b", r"\bimpact of\b",
            r"\bif i (change|remove|rename|delete)\b", r"\bsafe to (remove|delete|rename)\b",
            r"\bblast radius\b",
            companions=("S", "H")),
    # A diagnosis needs structure, the failing text, what changed, and what
    # the current task already established.
    _signal("G", "diagnostic", 2.5,
            r"\bwhy (is|does|did|are|do) .*\b(fail|failing|failed|broken|breaking|not work)",
            r"\bdebug(ging)?\b", r"\bwhat'?s (wrong|going on) with\b",
            r"\bstopped working\b", r"\bregression\b",
            companions=("S", "H", "T")),
    _signal("G", "structure", 1.5,
            r"\barchitecture of\b", r"\bhow does .* (connect|relate|fit together)\b",
            r"\bcall (graph|chain|tree)\b", r"\btrace (through|the flow)\b"),

    # ── Search: exact lexical lookup ──────────────────────────────────────
    _signal("S", "locate", 2.0,
            r"\bwhere is\b", r"\bwhere are\b", r"\bwhich file\b", r"\bfind (the|all|every)\b",
            r"\blocate\b", r"\bgrep\b", r"\bsearch (for|the code)\b"),
    # The constant pattern is explicitly case-*sensitive*: under the module's
    # re.I flag it would match any four-letter word, which quietly turned
    # every question into a lexical one.
    _signal("S", "identifier", 2.0,
            r"(?-i:\b[A-Z][A-Z0-9_]{3,}\b)",
            r"\b\w+\.(py|ts|tsx|js|jsx|json|md|toml|yaml|yml)\b",
            r"\b\w+_\w+\(\)", r"`[^`]+`"),
    _signal("S", "definition", 1.5,
            r"\bdefined\b", r"\bdeclaration of\b", r"\bimplementation of\b",
            r"\bhandled\b", r"\bloaded\b", r"\bset up\b"),

    # ── Read: a specific file or artifact ─────────────────────────────────
    _signal("R", "artifact", 3.0,
            r"\b(that|the) (pdf|document|report|screenshot|file|deck|spreadsheet)\b",
            r"\baccording to\b", r"\bin the attached\b", r"\bthe .* you (made|generated|wrote)\b"),
    _signal("R", "read_file", 2.0,
            r"\bopen (the|this) file\b", r"\bread (the|this) (file|whole)\b",
            r"\bshow me (the|this) (file|contents)\b", r"\bfull (contents|text) of\b"),

    # ── Task state: the work in flight ────────────────────────────────────
    # Resuming needs the state *and* the episode around it: state says what
    # is unfinished, history says what was going on when it stopped.
    _signal("T", "resume", 3.0,
            r"\bcontinue\b", r"\bresume\b", r"\bpick (this|it|that) back up\b",
            r"\bwhere (was|were) (i|we)\b", r"\bwhere did (i|we) (leave|stop)\b",
            r"\bbefore i (stopped|left off|quit|got interrupted)\b",
            r"\bkeep going\b", r"\bcarry on\b",
            companions=("H",)),
    _signal("T", "progress", 2.5,
            r"\bwhat have you (already )?tried\b", r"\bwhat'?s? (left|next|remaining)\b",
            r"\bhow far (are|did)\b", r"\bstatus of (this|the task)\b",
            r"\bam i done\b", r"\bwhat am i working on\b"),
    _signal("T", "action", 2.0,
            r"\bhandle (this|it)\b", r"\bdo (this|it) for me\b", r"\bcan you do\b",
            r"\bgo ahead\b", r"\bfinish (this|it)\b"),

    # ── Memory: durable knowledge ─────────────────────────────────────────
    # What is known about a project is partly durable fact and partly what
    # has been happening in it.
    _signal("M", "recall", 2.5,
            r"\bwhat do you (remember|know) about\b", r"\bdo you remember\b",
            r"\bwhat have i told you\b", r"\bwhat do you know about me\b",
            companions=("H",)),
    _signal("M", "preference", 2.0,
            # Plurals matter here: `my (preference)\b` cannot match "my
            # preferences", because \b demands a boundary immediately after
            # "preference" and the "s" denies it. "what are my preferences"
            # therefore scored zero on every signal and fell through to the
            # default — a code search, for a question about the user.
            r"\bmy (preferences?|setup|configs?|configuration|usual)\b",
            r"\bi (prefer|always|usually|never)\b",
            r"\bwe (use|prefer)\b", r"\bwhich (package manager|provider|model) (do|does)\b"),
    # Questions about the user themself. Their absence was the single biggest
    # hole in this table: measured over ten ordinary memory questions, only one
    # reached M, and "where do I live", "what's my name", "who am I" and
    # "what's my email address" all scored zero and defaulted to S — an exact
    # code search, run against the codebase, to answer a question about a
    # person. Retrieval that cannot be reached is indistinguishable from
    # retrieval that does not exist, which is what "it doesn't know anything
    # about me" actually is.
    #
    # Deliberately broad on the possessive. A first-person possessive question
    # that turns out to have no stored fact costs one empty lookup; the same
    # question sent to a code search costs a wrong answer.
    _signal("M", "personal_fact", 2.5,
            r"\bwho am i\b", r"\bwhere do i (live|work|stay)\b",
            r"\bwhat(?:'s| is| are)? ?my \w+", r"\bwhat are my\b",
            r"\bwhat (city|country|timezone|language) (am|do) i\b",
            r"\bmy (name|email|e-mail|phone|address|birthday|job|role|title|company|employer|timezone)\b",
            r"\bwhat did i tell you about\b",
            companions=("H",)),
    _signal("M", "why_remembered", 2.5,
            r"\bwhy do you (remember|think|believe)\b", r"\bhow do you know\b",
            r"\bwhere did you (get|learn) that\b"),
]

# Intent signals are scored separately: they change what happens to the
# retrieved context, not where it comes from.
_INTENT_SIGNALS: list[tuple[str, re.Pattern]] = [
    ("remember", re.compile(
        r"(?<!you )\bremember (that|this)\b|\bnote that\b|\bkeep in mind\b"
        r"|\bsave (this|that) (to|in) memory\b",
        re.I)),
    ("forget", re.compile(r"\bforget (that|this|about)\b|\bdon'?t remember\b|\bdelete .* (from|out of) memory\b|\bwe switched\b|\bthat'?s (wrong|no longer true)\b", re.I)),
    ("act", re.compile(
        r"\b(please\s+)?(run|deploy|install|delete|create|write|send|commit|push|fix|refactor|rename)\b"
        r"|\bhandle (this|it)\b|\bdo (this|it) for me\b|\btake care of (this|it)\b|\bgo ahead\b",
        re.I)),
]

# Requests about a credential never put the value in ordinary context; they
# route to the secret subsystem, which hands the model a reference.
_CREDENTIAL = re.compile(
    r"\bapi[ _-]?key\b|\btoken\b|\bpassword\b|\bsecret\b|\bcredential\b|\bpassphrase\b", re.I
)

# A question with no strong signal is most often about the code in front of
# the user, and lexical search is the cheapest thing that is usually right.
DEFAULT_LABEL = "S"


def _score(question: str) -> tuple[dict[str, float], list[str], dict[str, list[_Signal]]]:
    scores: dict[str, float] = {label: 0.0 for label in LABELS if label != "C"}
    matched: list[str] = []
    by_label: dict[str, list[_Signal]] = {}
    for signal in _SIGNALS:
        hits = len(signal.pattern.findall(question))
        if hits:
            # Repeated hits of one signal add sub-linearly: three filenames in
            # a question is not three times the evidence that it is lexical.
            scores[signal.label] += signal.weight * (1 + 0.25 * (min(hits, 4) - 1))
            matched.append(signal.name)
            by_label.setdefault(signal.label, []).append(signal)
    return scores, matched, by_label


def _detect_intent(question: str) -> str:
    for intent, pattern in _INTENT_SIGNALS:
        if pattern.search(question):
            return intent
    return "retrieve"


def route(question: str, *, classifier=None, allow_combined: bool = True) -> Route:
    """Decide which substrate (or substrates) should answer `question`.

    `classifier` is an optional callable taking the question and returning a
    single label character — the place a tiny local model plugs in. Its
    answer is accepted only if it is a valid label; anything else falls back
    to the heuristic rather than failing the request, because a router that
    can break is worse than one that is occasionally suboptimal.
    """
    text = (question or "").strip()
    if not text:
        return Route(label=DEFAULT_LABEL, sources=[DEFAULT_LABEL], confidence=0.0)

    intent = _detect_intent(text)
    requires_secret = bool(_CREDENTIAL.search(text))

    if classifier is not None:
        try:
            proposed = (classifier(text) or "").strip().upper()[:1]
        except Exception:
            proposed = ""
        if proposed in LABELS and proposed != "C":
            return Route(
                label=proposed,
                sources=[proposed],
                intent=intent,
                confidence=0.9,
                matched=["classifier"],
                requires_secret=requires_secret,
                classifier="model",
            )

    scores, matched, by_label = _score(text)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_label, top_score = ranked[0]

    if top_score == 0:
        # Nothing matched. A bare mention of remembering still means memory;
        # otherwise fall back to the cheapest generally-useful source.
        fallback = "M" if intent in {"remember", "forget"} else DEFAULT_LABEL
        return Route(
            label=fallback,
            sources=[fallback],
            intent=intent,
            confidence=0.2,
            matched=[],
            scores=scores,
            requires_secret=requires_secret,
        )

    sources = [top_label]
    if allow_combined:
        # Sources the winning signals explicitly ask for, then any label that
        # scored close enough to the winner to be worth consulting anyway.
        for signal in by_label.get(top_label, []):
            for companion in signal.companions:
                if companion not in sources:
                    sources.append(companion)
        for label, score in ranked[1:]:
            if label not in sources and score > 0 and score >= top_score * COMBINED_MARGIN:
                sources.append(label)

    total = sum(scores.values()) or 1.0
    confidence = round(min(0.95, top_score / total + 0.15 * (len(sources) == 1)), 3)
    label = "C" if len(sources) > 1 else top_label

    return Route(
        label=label,
        sources=sources,
        intent=intent,
        confidence=confidence,
        matched=matched,
        scores=scores,
        requires_secret=requires_secret,
    )


def label_prompt() -> str:
    """The instruction for a tiny routing model.

    Kept here so the label set has exactly one definition: adding a label
    without updating the prompt would silently make the classifier unable to
    produce it.
    """
    lines = [
        "Classify the request by which source should answer it.",
        "Reply with exactly one letter and nothing else.",
        "",
    ]
    lines += [
        "M = durable memory / known facts",
        "S = exact code search (strings, symbols, filenames)",
        "G = code structure (callers, dependents, impact)",
        "R = read a specific file or document",
        "T = the task currently in progress",
        "H = what happened previously, and when",
    ]
    return "\n".join(lines)
