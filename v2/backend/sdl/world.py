"""The world: one person, the people around them, and 24 months of it changing.

Generated FIRST, and everything else references it. That ordering is the whole
design — artifacts invented independently and stitched together afterwards
contradict each other, and a benchmark built on contradictions cannot tell a
retrieval failure from a data bug.

The life events are the point. A promotion in month 9 and a reorg in month 14
are what make "which project changed owners after the reorganisation" a real
question with one correct answer, rather than a query over noise.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

MONTHS = 24
START = date(2025, 1, 1)

FIRST = ["Maya", "Idris", "Nadia", "Tomás", "Priya", "Kofi", "Lena", "Arun",
         "Sofia", "Dmitri", "Amara", "Ravi", "Elena", "Joon", "Zara", "Marcus",
         "Yuki", "Femi", "Clara", "Omar", "Ingrid", "Hassan", "Petra", "Diego",
         "Ayesha", "Niels", "Rosa", "Tariq", "Hana", "Bruno"]
LAST = ["Okonkwo", "Lindqvist", "Vasquez", "Ferreira", "Nakamura", "Achebe",
        "Kowalski", "Haddad", "Moreau", "Petrov", "Silva", "Brennan",
        "Castellanos", "Dubois", "Reyes", "Novak", "Adeyemi", "Larsen"]

ORGS = ["Halcyon Systems", "Northwind Analytics", "Meridian Labs", "Kestrel Cloud",
        "Aster Robotics", "Verdant Energy", "Ravelin Security", "Solace Health",
        "Tessellate AI", "Cormorant Freight"]

PROJECT_NAMES = ["Atlas", "Beacon", "Cinder", "Drift", "Ember", "Fathom",
                 "Granite", "Harbour", "Ivory", "Juniper", "Keystone", "Lantern",
                 "Mosaic", "Nimbus", "Orchid", "Pallas", "Quarry", "Ridge"]

REPO_SUFFIXES = ["api", "web", "cli", "etl", "worker", "sdk", "mobile", "docs"]
LANGUAGES = ["python", "typescript", "rust", "go", "react"]

# Capabilities that enter the codebase once and are copied afterwards. The first
# repository to introduce one is a fact with a single correct answer — "which
# repository first introduced OAuth" — and the later adopters are what make that
# question harder than grepping for the word.
FEATURES = ["OAuth", "rate limiting", "structured logging", "feature flags",
            "response caching", "WebSocket transport", "audit trails",
            "background jobs", "schema migrations", "request tracing",
            "cursor pagination", "soft deletes"]

# Recurring commitments. `ends_at` and `starts_at` name a life event, which is
# what turns "which recurring meetings disappeared after the reorganisation"
# into a question the generator can answer exactly. Series that simply lapse are
# added separately, and never in an event month — a lapse that coincides with
# the reorg is indistinguishable from a consequence of it, and a benchmark must
# not mark a system wrong for a distinction the data does not carry.
SERIES_TEMPLATES = [
    ("Platform standup",      "weekly",   0, "work",     None,            "reorg"),
    ("Product standup",       "weekly",   0, "work",     "reorg",         None),
    ("Sprint planning",       "biweekly", 1, "work",     None,            None),
    ("Sprint retro",          "biweekly", 4, "work",     None,            None),
    ("1:1 with manager",      "weekly",   2, "work",     None,            "new_manager"),
    ("1:1 with new manager",  "weekly",   2, "work",     "new_manager",   None),
    ("On-call handover",      "weekly",   4, "work",     None,            None),
    ("Architecture review",   "monthly",  3, "work",     None,            None),
    ("Hiring sync",           "weekly",   1, "work",     None,            "hiring_freeze"),
    ("Climbing session",      "weekly",   2, "personal", None,            None),
    ("Gym",                   "biweekly", 5, "personal", None,            None),
    ("Coffee with Rowan",     "monthly",  6, "personal", None,            None),
    ("Rust study group",      "weekly",   3, "personal", "learned_rust",  None),
    ("Conference prep",       "weekly",   1, "work",     "conference",    None),
]

CADENCE_PER_MONTH = {"weekly": 4, "biweekly": 2, "monthly": 1}

# Which source wins when two of them disagree. A calendar is the system of
# record for when something happens; an email is a deliberate statement; a chat
# message is somebody's recollection. Ranked rather than merely listed, because
# "prefer the latest authoritative source" needs an ordering to mean anything.
AUTHORITY = {"calendar": 3, "email": 2, "chat": 1}

DISPUTE_KINDS = [
    ("meeting_day", "Which day of the week is {subject} held on?",
     ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]),
    ("location", "Where is {subject} held?",
     ["room Aurora", "room Basalt", "room Cobalt", "the annex", "a video call"]),
    ("deadline", "What is the agreed deadline for {subject}?",
     ["the 7th", "the 14th", "the 21st", "the 28th"]),
]

# Preferences that CHANGE. Each is a chain: the later statement supersedes the
# earlier one, and the dataset records both with timestamps so "which preference
# changed most recently" has one answer.
PREFERENCE_ARCS = [
    ("coffee", ["drinks flat whites", "switched to cortados",
                "drinks black filter coffee now"]),
    ("theme", ["prefers dark mode", "switched to light mode"]),
    ("editor", ["uses VS Code", "moved to Neovim"]),
    ("language", ["writes mostly Python", "learning Rust", "writes Rust daily now"]),
    ("soda", ["drinks a cola most afternoons", "stopped drinking soda"]),
    ("commute", ["cycles to the office", "takes the tram since moving"]),
    ("standup", ["prefers morning standups", "prefers async written standups"]),
    ("notes", ["keeps notes in Notion", "moved notes to plain markdown"]),
]

LIFE_EVENTS = [
    (3, "moved_apartment", "Moved from Rasmussen Street to the Kvarter district"),
    (6, "new_laptop", "Replaced the 2021 laptop with a 32GB machine"),
    (9, "promotion", "Promoted to Staff Engineer"),
    (11, "learned_rust", "Finished the Rust book and shipped the first CLI"),
    (14, "reorg", "Company reorganisation — platform and product split"),
    (16, "hiring_freeze", "Hiring freeze announced"),
    (19, "conference", "Spoke at a conference about incremental indexing"),
    (21, "new_manager", "New manager after the reorg settled"),
]


@dataclass
class Person:
    id: str
    name: str
    org: str
    role: str
    joined_month: int = 0
    left_month: int | None = None

    def active(self, month: int) -> bool:
        return self.joined_month <= month and (self.left_month is None
                                               or month < self.left_month)


@dataclass
class Project:
    id: str
    name: str
    org: str
    started_month: int
    owner_id: str
    # Ownership CHANGES at the reorg. Recorded as a list so "who owned Atlas in
    # month 10" and "which projects changed owners after the reorg" are both
    # answerable from the data rather than from a guess.
    owner_history: list[tuple[int, str]] = field(default_factory=list)
    repo: str | None = None
    renamed_from: str | None = None

    def owner_at(self, month: int) -> str:
        owner = self.owner_id
        for changed_at, new_owner in sorted(self.owner_history):
            if changed_at <= month:
                owner = new_owner
        return owner


@dataclass
class Repo:
    id: str
    name: str
    language: str
    project_id: str
    created_month: int


@dataclass
class Series:
    """A recurring commitment, and the reason it started or stopped.

    `ended_by` is the whole point. A calendar of events that simply exist tests
    that dates parse; a standup that vanishes the month of the reorganisation
    tests whether the system can notice an absence — which is the harder thing
    and the one users actually ask about.
    """
    id: str
    title: str
    cadence: str
    weekday: int
    kind: str
    start_month: int
    end_month: int | None = None
    started_by: str | None = None
    ended_by: str | None = None
    attendees: list[str] = field(default_factory=list)

    def runs_in(self, month: int) -> bool:
        return (self.start_month <= month
                and (self.end_month is None or month < self.end_month))


@dataclass
class Dispute:
    """One fact, stated differently by several sources.

    Resolution is authority first, then recency inside the winning tier. A
    calendar entry outranks an email, an email outranks a chat message, and
    between two claims of equal standing the later one wins. Both shapes are
    generated, because a rule that is only ever exercised one way is a rule
    nobody has tested.
    """
    id: str
    topic: str
    question: str
    # The thing under dispute, as a noun phrase ("the Atlas Core sync"). Stored
    # rather than recovered from `question`: parsing it back out picked "the
    # week" out of "which day of the week is the Atlas Core sync on", and every
    # claim in the corpus was then written about the wrong noun.
    about: str = ""
    claims: list[dict] = field(default_factory=list)

    @property
    def resolved(self) -> dict:
        return max(self.claims, key=lambda c: (c["authority"], c["month"]))

    @property
    def stale(self) -> list[dict]:
        winner = self.resolved
        return [c for c in self.claims
                if c["value"] != winner["value"] or c is not winner]


@dataclass
class World:
    seed: int
    subject: dict
    people: list[Person]
    orgs: list[str]
    projects: list[Project]
    events: list[dict]
    months: int = MONTHS
    repos: list[Repo] = field(default_factory=list)
    features: list[dict] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    disputes: list[Dispute] = field(default_factory=list)

    def person(self, pid: str) -> Person | None:
        return next((p for p in self.people if p.id == pid), None)

    def event_month(self, kind: str) -> int | None:
        return next((e["month"] for e in self.events if e["kind"] == kind), None)

    def repo_names(self) -> list[str]:
        return [r.name for r in self.repos]

    def active_people(self, month: int) -> list[Person]:
        return [p for p in self.people if p.active(month)]

    def month_date(self, month: int) -> date:
        year = START.year + (START.month - 1 + month) // 12
        m = (START.month - 1 + month) % 12 + 1
        return date(year, m, 1)

    def month_label(self, month: int) -> str:
        d = self.month_date(month)
        return f"{d.year}-{d.month:02d}"


def build(seed: int = 20260815, months: int = MONTHS, people_count: int = 120,
          project_count: int = 80, repo_count: int = 40,
          dispute_count: int = 24) -> World:
    r = random.Random(seed)

    subject = {
        "id": "person:subject",
        "name": "Devan Ashcroft",
        "dob": "1991-04-17",
        "city": "Halden Bay",
        "role": "Senior Engineer",
        "org": ORGS[0],
        "education": [
            {"year": 2009, "what": "BSc Computer Science, Halden Bay University"},
            {"year": 2013, "what": "MSc Distributed Systems"},
        ],
        "family": [
            {"relation": "sister", "name": "Rowan Ashcroft"},
            {"relation": "partner", "name": "Ines Varela"},
        ],
        "pets": [{"kind": "cat", "name": "Bishop"}],
        "devices": [
            {"kind": "laptop", "name": "ThinkPad X1", "from_month": 0, "to_month": 6},
            {"kind": "laptop", "name": "Framework 16 (32GB)", "from_month": 6},
            {"kind": "phone", "name": "Pixel 8"},
        ],
        "personality": ["direct", "writes things down", "dislikes meetings before 10",
                        "reads specs end to end"],
    }

    # ── people ────────────────────────────────────────────────────────────
    people: list[Person] = []
    used: set[str] = set()
    for i in range(people_count):
        while True:
            name = f"{r.choice(FIRST)} {r.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        org = ORGS[0] if i < people_count * 0.6 else r.choice(ORGS[1:])
        # No CTO in the pool. person:000 is assigned that role below, and
        # several ground-truth answers are phrased "…with <name> (CTO)"; a
        # second CTO in the cast makes those questions ambiguous, so a system
        # that returns the other one's meetings is marked wrong for being right.
        role = r.choice(["Engineer", "Senior Engineer", "Staff Engineer",
                         "Engineering Manager", "Product Manager", "Designer",
                         "Data Scientist", "Analyst", "Recruiter"])
        joined = 0 if i < people_count * 0.5 else r.randrange(0, months - 2)
        # A quarter of the cast leaves. Departures are what make "who was on
        # the team when X happened" a question with a wrong answer available.
        left = None
        if r.random() < 0.25:
            left = min(months, joined + r.randrange(4, months))
        people.append(Person(id=f"person:{i:03d}", name=name, org=org, role=role,
                             joined_month=joined, left_month=left))

    # One CTO, named, because several queries hinge on reaching them.
    people[0] = Person(id="person:000", name=people[0].name, org=ORGS[0],
                       role="CTO", joined_month=0)

    # ── projects ──────────────────────────────────────────────────────────
    projects: list[Project] = []
    for i in range(project_count):
        base = PROJECT_NAMES[i % len(PROJECT_NAMES)]
        name = base if i < len(PROJECT_NAMES) else f"{base} {i // len(PROJECT_NAMES) + 1}"
        started = r.randrange(0, max(1, months - 3))
        owner = r.choice([p for p in people if p.active(started)]).id
        # `repo` is filled in below, once the repositories exist. Repositories
        # are derived FROM projects rather than named independently, so every
        # commit can be traced back to the project it was written for.
        projects.append(Project(id=f"project:{i:03d}", name=name, org=ORGS[0],
                                started_month=started, owner_id=owner, repo=None))

    # Life events are authored against a 24-month life. A shorter pack has to
    # SCALE them, not truncate: dropping the reorg because a pack runs 18 months
    # silently removes the event several ground-truth answers depend on, and the
    # dataset then fails its own validation for a reason nobody would guess.
    events = []
    for m, kind, what in LIFE_EVENTS:
        scaled = m if months >= MONTHS else max(1, round(m * (months - 1) / (MONTHS - 1)))
        events.append({"month": min(scaled, months - 1), "kind": kind, "what": what})

    # ── the reorg: ownership moves, and one project is renamed ────────────
    reorg_month = next(e["month"] for e in events if e["kind"] == "reorg")
    for project in projects:
        if project.started_month < reorg_month and r.random() < 0.3:
            candidates = [p for p in people
                          if p.active(reorg_month) and p.id != project.owner_id]
            if candidates:
                project.owner_history.append((reorg_month, r.choice(candidates).id))
    # A rename with the old name preserved: "every renamed project preserves
    # historical aliases" is a validation rule, and this is what it checks.
    projects[0].renamed_from = projects[0].name
    projects[0].name = f"{projects[0].name} Core"

    def event_month(kind: str) -> int | None:
        return next((e["month"] for e in events if e["kind"] == kind), None)

    # Everything below draws from its OWN stream. Sharing `r` would mean that
    # adding a repository shifts every project owner generated before it, and a
    # generator where one new feature rewrites the whole world produces diffs
    # nobody can review.

    # ── repositories ──────────────────────────────────────────────────────
    repos: list[Repo] = []
    taken: set[str] = set()
    for i in range(repo_count):
        project = projects[i % len(projects)]
        slug = project.name.lower().replace(" ", "-")
        suffix = REPO_SUFFIXES[(i // len(projects)) % len(REPO_SUFFIXES)]
        name = f"{slug}-{suffix}"
        # A duplicate repository name would make "which repo introduced OAuth"
        # ambiguous while looking perfectly fine in the data.
        n = 2
        while name in taken:
            name, n = f"{slug}-{suffix}{n}", n + 1
        taken.add(name)
        repos.append(Repo(id=f"repo:{name}", name=name,
                          language=LANGUAGES[i % len(LANGUAGES)],
                          project_id=project.id,
                          created_month=project.started_month))
        if project.repo is None:
            project.repo = name

    # ── features: introduced once, copied later ───────────────────────────
    fr = random.Random(seed ^ 0xF3A7)
    features: list[dict] = []
    for i, name in enumerate(FEATURES):
        first = repos[(i * 7) % len(repos)]
        first_month = min(months - 2, 1 + (i * 3) % max(1, months - 6))
        adopters = []
        # At least one adopter, always. A feature that exists in exactly one
        # repository makes "which repository FIRST introduced it" answerable by
        # finding the only mention, which tests search and not chronology.
        for j in range(fr.randrange(1, 4)):
            repo = repos[(i * 7 + j * 5 + 3) % len(repos)]
            month = min(months - 1, first_month + 2 + j * 2)
            # Adoption must be strictly later than introduction, or "first"
            # stops being a well-defined word and the answer key is a coin toss.
            if repo.name == first.name or month <= first_month:
                continue
            adopters.append({"repo": repo.name, "month": month})
        features.append({
            "name": name, "first_repo": first.name, "first_month": first_month,
            "adopters": sorted(adopters, key=lambda a: (a["month"], a["repo"])),
        })

    # ── recurring series ──────────────────────────────────────────────────
    sr = random.Random(seed ^ 0x5E12)
    series: list[Series] = []
    for idx, (title, cadence, weekday, kind, starts_at, ends_at) in enumerate(
            SERIES_TEMPLATES):
        start = event_month(starts_at) if starts_at else 0
        end = event_month(ends_at) if ends_at else None
        if start is None:
            continue
        # A series that ends before it begins is not a series. This happens when
        # a short pack scales two life events onto the same month.
        if end is not None and end <= start:
            continue
        cast = [p for p in people if p.active(start)] or people
        size = 2 if kind == "personal" else min(len(cast), sr.randrange(3, 7))
        series.append(Series(
            id=f"series:{idx:02d}", title=title, cadence=cadence,
            weekday=weekday, kind=kind, start_month=start, end_month=end,
            started_by=starts_at, ended_by=ends_at,
            attendees=[p.id for p in sr.sample(cast, min(size, len(cast)))]))

    # Series that simply lapse, with no life event behind them. Without these,
    # "which meetings stopped because of the reorg" could be answered by
    # listing everything that stopped, and the question would be measuring
    # nothing. They are kept OUT of event months on purpose: a lapse landing on
    # the reorg is indistinguishable from a consequence of it, and a benchmark
    # must not mark a system wrong over a distinction its data does not carry.
    event_months = {e["month"] for e in events}
    free = [m for m in range(2, months - 1) if m not in event_months]
    for n, (title, cadence, weekday) in enumerate(
            [("Design critique", "biweekly", 2), ("Book club", "monthly", 4),
             ("Bug triage", "weekly", 1)]):
        if not free:
            break
        end = free[(n * 5 + 3) % len(free)]
        cast = [p for p in people if p.active(0)] or people
        series.append(Series(
            id=f"series:lapsed:{n:02d}", title=title, cadence=cadence,
            weekday=weekday, kind="work", start_month=0, end_month=end,
            started_by=None, ended_by=None,
            attendees=[p.id for p in sr.sample(cast, min(4, len(cast)))]))

    # ── disputes ──────────────────────────────────────────────────────────
    dr = random.Random(seed ^ 0xD152)
    disputes: list[Dispute] = []
    for i in range(dispute_count):
        project = projects[i % len(projects)]
        kind, template, values = DISPUTE_KINDS[i % len(DISPUTE_KINDS)]
        # Not `subject`: that name holds the person this whole world is about,
        # and shadowing it here handed the World a meeting title instead.
        about = f"the {project.name} {'review' if i % 2 else 'sync'}"
        wrong, right = dr.sample(values, 2)
        base = dr.randrange(1, max(2, months - 3))
        if i % 2 == 0:
            # Authority shape: the low-authority claim is the LATER one, so a
            # system that resolves purely by recency gets it wrong. That is the
            # only way this question tests anything.
            claims = [
                {"source_kind": "calendar", "source_id": f"cal:dispute:{i:04d}",
                 "authority": AUTHORITY["calendar"], "month": base,
                 "value": right},
                {"source_kind": "email", "source_id": f"email:dispute:{i:04d}",
                 "authority": AUTHORITY["email"], "month": base,
                 "value": right},
                {"source_kind": "chat", "source_id": f"chat:dispute:{i:04d}",
                 "authority": AUTHORITY["chat"], "month": min(months - 1, base + 1),
                 "value": wrong},
            ]
        else:
            # Recency shape: equal standing, so the later claim wins.
            claims = [
                {"source_kind": "chat", "source_id": f"chat:dispute:{i:04d}a",
                 "authority": AUTHORITY["chat"], "month": base, "value": wrong},
                {"source_kind": "chat", "source_id": f"chat:dispute:{i:04d}b",
                 "authority": AUTHORITY["chat"], "month": min(months - 1, base + 2),
                 "value": right},
            ]
        disputes.append(Dispute(id=f"dispute:{i:04d}", topic=kind,
                                question=template.format(subject=about),
                                about=about, claims=claims))

    return World(seed=seed, subject=subject, people=people, orgs=list(ORGS),
                 projects=projects, events=events, months=months,
                 repos=repos, features=features, series=series,
                 disputes=disputes)
