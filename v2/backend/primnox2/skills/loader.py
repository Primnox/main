"""Skills — capability instructions that are only paid for when used.

The system prompt is the one string every turn carries, so anything added to it
is charged to every question forever. Measured: teaching the model about themed
documents cost ~209 tokens on each turn, including the ones that will never
produce a document. Three more capabilities taught the same way and the preamble
would be larger than most replies.

A skill inverts that. The prompt carries one line per skill — a name and when to
use it — and the instructions themselves arrive only when the turn looks like it
needs them.

Selection happens in the runtime, not through the model. Asking the model to
request a skill costs a whole extra round trip, and on the local 7B a round trip
is ~8 seconds and carries a 1-in-20 chance of the tool loop running away. A
keyword match costs nothing and cannot loop. A model that wants one anyway can
still ask: `read_skill` is a registered tool.

    skills/
      themed-documents/SKILL.md
      <name>/SKILL.md

Each file opens with a `---` frontmatter block carrying `name`, `description`
and `triggers`; everything after it is the instruction body.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SKILLS_DIR = Path(__file__).parent


# Anything a skill's own instructions can tell the model to open. Restricted by
# extension rather than by path so a skill directory can be reorganised without
# touching this, but never so broadly that "read a file from the skill" becomes
# a way to read the rest of the machine.
READABLE_SUFFIXES = {".md", ".css", ".json", ".txt", ".js", ".html", ".svg"}
MAX_ASSET_CHARS = 60_000


@dataclass
class Skill:
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    body: str = ""
    root: Path | None = None

    def index_line(self) -> str:
        return f"- {self.name}: {self.description}"

    def assets(self) -> list[str]:
        """Supporting files, relative to the skill directory."""
        if self.root is None:
            return []
        return sorted(
            str(p.relative_to(self.root)).replace("\\", "/")
            for p in self.root.rglob("*")
            if p.is_file() and p.suffix.lower() in READABLE_SUFFIXES
            and p.name != "SKILL.md"
        )

    def read_asset(self, relative: str) -> str | None:
        """Read one supporting file, or None if it is not one.

        A skill's instructions routinely say "include the full contents of
        viewport-base.css in every presentation", so the files beside SKILL.md
        are part of the skill, not decoration. The resolved path is checked to
        be inside the skill directory: `relative` arrives from the model, and
        `../../../etc/passwd` is the obvious thing to try.
        """
        if self.root is None:
            return None
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root.resolve())
        except ValueError:
            return None
        if not target.is_file() or target.suffix.lower() not in READABLE_SUFFIXES:
            return None
        text = target.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_ASSET_CHARS:
            return text[:MAX_ASSET_CHARS] + "\n… (truncated)"
        return text


_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


def _parse(text: str, fallback_name: str, root: Path | None = None) -> Skill | None:
    match = _FRONTMATTER.match(text)
    if not match:
        return None
    head, body = match.group(1), match.group(2).strip()
    fields: dict[str, str] = {}
    for line in head.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()
    triggers = [t.strip().lower() for t in fields.get("triggers", "").split(",") if t.strip()]
    return Skill(
        name=fields.get("name") or fallback_name,
        description=fields.get("description", ""),
        triggers=triggers,
        body=body,
        root=root,
    )


_cache: dict[str, Skill] | None = None


def all_skills(refresh: bool = False) -> dict[str, Skill]:
    global _cache
    if _cache is not None and not refresh:
        return _cache
    found: dict[str, Skill] = {}
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        try:
            skill = _parse(path.read_text(encoding="utf-8"), path.parent.name, path.parent)
        except OSError:
            continue
        if skill and skill.name:
            found[skill.name] = skill
    _cache = found
    return found


def index() -> str:
    """The always-present cost: one line each, so the model knows what exists."""
    skills = all_skills()
    if not skills:
        return ""
    lines = "\n".join(s.index_line() for s in skills.values())
    return ("Skills — extra instructions available on demand. Ask for one with "
            '<tool name="read_skill">{"name": "…"}</tool> if a turn needs it:\n'
            f"{lines}")


def get(name: str) -> Skill | None:
    return all_skills().get((name or "").strip().lower())


# Skill bodies are inlined into the prompt, so an unbounded selection is an
# unbounded prompt. 32k chars is roughly 8k tokens: comfortable for a 128k
# model, and the most a 32k-context local model can give up before the history
# it needs starts falling out of the window.
INLINE_BUDGET_CHARS = 32_000


def select(text: str, limit: int = 2) -> list[Skill]:
    """Which skills this request looks like it needs.

    Still a substring match on declared triggers — a cleverer matcher would be
    a second thing that can be wrong about a request, and the failure mode of
    missing one is that the model asks, which still works.

    Two things it is not naive about:

    SPECIFICITY. Skills are ranked by their LONGEST matching trigger, not by
    filename order. `themed-documents` declares the bare word `deck`, which is a
    substring of "pitch deck", "html deck" and every other deck phrase — so
    without ranking it fires alongside `frontend-slides` on every request either
    could serve, and the model receives two contradictory sets of instructions.
    The longer match is the more specific claim on the request.

    BUDGET. Bodies are inlined, and `frontend-slides` alone is ~29k characters.
    Selecting two large skills would spend most of a local model's context
    before it reads the question. The highest-ranked skill is always included
    even if it exceeds the budget by itself — dropping it would leave the turn
    with no instructions at all, which is worse than a tight window.
    """
    lowered = (text or "").lower()
    scored: list[tuple[int, Skill]] = []
    for skill in all_skills().values():
        matched = [t for t in skill.triggers if t in lowered]
        if matched:
            scored.append((max(len(t) for t in matched), skill))
    if not scored:
        return []
    scored.sort(key=lambda pair: (-pair[0], pair[1].name))

    # Only skills matching as specifically as the best one. Two skills that
    # claim the same request are ALTERNATIVES, not supplements: "create a pitch
    # deck" matches frontend-slides on "pitch deck" and themed-documents on the
    # bare "deck", and loading both hands the model one set of instructions for
    # building an HTML deck and another for building a .pptx, for the same
    # sentence. An exact tie is real ambiguity and does load both.
    best = scored[0][0]
    chosen: list[Skill] = []
    spent = 0
    for score, skill in scored:
        if score < best or len(chosen) >= limit:
            break
        if chosen and spent + len(skill.body) > INLINE_BUDGET_CHARS:
            break
        chosen.append(skill)
        spent += len(skill.body)
    return chosen
