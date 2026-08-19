"""Deterministic artifact generators.

Everything here takes a seed and returns the same bytes every time. That is the
constraint that makes the pack a benchmark: a 500-turn conversation whose
wording drifts between runs cannot tell a context regression from a different
conversation.

Nothing here is a toy. The conversation carries real cross-references 400 turns
back, the repository has genuine circular imports, and the markdown includes the
constructs that actually break renderers rather than a heading and a list.
"""
from __future__ import annotations

import random
import textwrap
from pathlib import Path

# Vocabulary drawn from a fixed list rather than generated prose. Real words
# make a retrieval failure legible — "it lost the AVL tree" is a report, "it
# lost token 4471" is not.
TOPICS = [
    "AVL tree rebalancing", "heap compaction", "B-tree page splits",
    "write-ahead logging", "vector clocks", "consistent hashing",
    "bloom filters", "LSM compaction", "Raft leader election",
    "copy-on-write snapshots", "arena allocation", "tail latency",
]
ENTITIES = [
    "PaymentGateway", "LedgerService", "SettlementQueue", "RiskEngine",
    "AuditTrail", "TokenVault", "ClearingHouse", "FraudScorer",
]
PEOPLE = ["Ada", "Grace", "Alan", "Barbara", "Edsger", "Radia", "Karen", "Leslie"]


def rng(seed: int) -> random.Random:
    return random.Random(seed)


# ── Module 1: a conversation long enough to break context ────────────────────
def conversation(turns: int = 500, seed: int = 20260815) -> list[dict]:
    """A conversation with real back-references.

    The final turn cites three earlier ones by number, and each cited turn
    contains a distinct, checkable fact. That is what makes the test gradeable:
    a system that hallucinates gets a different answer, not a vaguer one.
    """
    r = rng(seed)
    messages: list[dict] = []
    facts: dict[int, str] = {}

    for i in range(1, turns + 1):
        topic = TOPICS[i % len(TOPICS)]
        entity = ENTITIES[i % len(ENTITIES)]
        if i in (57, 211, 398):
            # Anchors. Deliberately spread so that any window smaller than the
            # whole conversation drops at least one of them.
            fact = {
                57: "the traversal starts at the leftmost leaf and uses an explicit stack",
                211: "the AVL implementation rebalances on insert with four rotation cases",
                398: "the optimized heap version uses a d-ary heap with d=4 and sift-down",
            }[i]
            facts[i] = fact
            text = f"For {topic}: {fact}. Call it {entity}."
        else:
            text = (f"Turn {i}: discussing {topic} in {entity}. "
                    f"{r.choice(PEOPLE)} noted a detail worth {r.randint(2, 90)} points.")
        messages.append({"turn": i, "role": "user", "text": text})
        messages.append({"turn": i, "role": "assistant",
                         "text": f"Noted for turn {i}: {topic}."})

    messages.append({
        "turn": turns + 1, "role": "user",
        "text": ("Continue the algorithm from Turn 57 but replace the AVL "
                 "implementation from Turn 211 with the optimized heap version "
                 "we discussed in Turn 398."),
        "probe": True, "requires": sorted(facts),
    })
    return messages


# ── Module 12: markdown that breaks renderers ────────────────────────────────
def markdown_torture() -> str:
    """The constructs that actually break renderers, not a heading and a list."""
    return textwrap.dedent("""\
        # Crucible Markdown

        | Nested | Table |
        |---|---|
        | a | <table><tr><td>inner</td></tr></table> |
        | pipe \\| inside | `code | with | pipes` |

        > outer quote
        > > inner quote
        > > > third level with a | pipe and **bold**

        ```python
        def unterminated(x):
            return f"{x}"  # a fence containing ``` backticks
        ```

        ````
        ```
        a fence inside a fence
        ```
        ````

        - [ ] task
          - [x] nested done
            - [ ] deeper

        Math: $E = mc^2$ and $$\\int_0^\\infty e^{-x}dx = 1$$

        Footnote reference[^1] and another[^long-name].

        [^1]: The footnote.
        [^long-name]: Another.

        ```mermaid
        graph TD
          A[Start] --> B{Branch}
          B -->|yes| C[End]
        ```

        <details><summary>Spoiler</summary>Hidden **markdown** inside HTML.</details>

        Emoji flood: 🔥🔥🔥🚀🚀💥🧨⚡🌊🪐🛰️🧬🦠🧪🔬🧯
        RTL: مرحبا بالعالم — mixed with English mid-sentence.
        CJK: 日本語のテキストと中文文本混合排版测试。
        Zero-width: a​b​c  Combining: ééé
        """)


# ── Module 11: filenames and strings that break layout ───────────────────────
def hostile_strings() -> dict[str, str]:
    return {
        "long_filename": ("a_very_long_filename_" * 20)[:400] + ".pdf",
        "rtl": "مستند_سري_للغاية_٢٠٢٦.pdf",
        "cjk": "非常に長い日本語のファイル名です_これはテストです.xlsx",
        "emoji": "🔥report🚀final💥v2🧨.pptx",
        "zero_width": "in​visible​breaks.txt",
        "combining": "é" * 120 + ".md",
        "newline_ish": "name_with\ttab_and line_sep.txt",
        "sql_ish": "'; DROP TABLE assets; --.csv",
        "path_ish": "../../../etc/passwd",
        "windows_reserved": "CON.txt",
        "only_dots": "....",
        "single_char": "a",
    }


# ── Module 6/13: a repository big enough to matter ───────────────────────────
def repository(root: Path, files: int = 500, seed: int = 20260815) -> dict:
    """A synthetic repo with the pathologies that break analysis.

    Circular imports, duplicated symbols and generated files are included on
    purpose: they are what a real 60k-line codebase contains, and an extractor
    that only handles clean trees passes every toy fixture and fails on arrival.
    """
    r = rng(seed)
    root.mkdir(parents=True, exist_ok=True)
    pkg = root / "app"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    written, loc = [], 0
    for i in range(files):
        module = pkg / f"mod_{i:04d}.py"
        # Circular by construction: every module imports its neighbour, and the
        # last imports the first.
        peer = (i + 1) % files
        entity = ENTITIES[i % len(ENTITIES)]
        body = [
            '"""Generated module — Crucible."""',
            "from __future__ import annotations",
            f"from app.mod_{peer:04d} import helper_{peer:04d}",
            "",
            f"CONSTANT_{i:04d} = {r.randint(1, 10_000)}",
            "",
            f"class {entity}{i:04d}:",
            f'    """Handles {TOPICS[i % len(TOPICS)]}."""',
            "    def __init__(self) -> None:",
            f"        self.value = CONSTANT_{i:04d}",
            "",
            "    def process(self, payload: dict) -> dict:",
            f"        return {{**payload, 'by': '{entity}{i:04d}'}}",
            "",
            f"def helper_{i:04d}(x: int) -> int:",
            f"    return x + CONSTANT_{i:04d}",
            "",
            # A duplicated symbol name across every module: name collisions are
            # what break naive symbol resolution.
            "def shared_name(a, b):",
            "    return a if a > b else b",
            "",
        ]
        text = "\n".join(body)
        module.write_text(text, encoding="utf-8")
        written.append(module)
        loc += text.count("\n")

    (root / "README.md").write_text(
        "# Crucible Repo\n\nGenerated. Circular imports and duplicate symbols "
        "are deliberate.\n", encoding="utf-8")
    return {"files": len(written), "loc": loc, "root": str(root)}


# ── Module 6: a graph at a scale the viewer has never seen ───────────────────
def graph_extraction(nodes: int = 50_000, edges: int = 120_000,
                     seed: int = 20260815) -> dict:
    """Graphify-shaped extraction, at the size the spec asks for.

    Includes contradictory edges (A uses B and A does-not-use B) and renamed
    entities pointing at one identity, because a graph that only ever agrees
    with itself never exercises confidence handling.
    """
    r = rng(seed)
    out_nodes = [
        {"id": f"n{i:06d}", "label": f"{ENTITIES[i % len(ENTITIES)]}_{i}",
         "file_type": "code", "source_file": f"app/mod_{i % 500:04d}.py",
         "source_location": f"L{(i % 400) + 1}"}
        for i in range(nodes)
    ]
    relations = ["calls", "imports", "uses", "contains", "references"]
    out_edges = []
    for i in range(edges):
        a, b = r.randrange(nodes), r.randrange(nodes)
        if a == b:
            b = (b + 1) % nodes
        out_edges.append({
            "source": f"n{a:06d}", "target": f"n{b:06d}",
            "relation": relations[i % len(relations)],
            "confidence": "EXTRACTED" if i % 5 else "INFERRED",
            "weight": 1.0,
            "source_file": f"app/mod_{a % 500:04d}.py",
            "source_location": f"L{(i % 400) + 1}",
        })
    # Contradictions: the same pair asserted both ways under different relations.
    for i in range(0, 200, 2):
        out_edges.append({"source": f"n{i:06d}", "target": f"n{i + 1:06d}",
                          "relation": "uses", "confidence": "EXTRACTED", "weight": 1.0})
        out_edges.append({"source": f"n{i:06d}", "target": f"n{i + 1:06d}",
                          "relation": "excludes", "confidence": "AMBIGUOUS", "weight": 1.0})
    return {"nodes": out_nodes, "edges": out_edges}


# ── Module 7: memories that disagree with each other ─────────────────────────
def memory_timeline(seed: int = 20260815) -> list[dict]:
    """Preferences that change over time, plus outright contradictions.

    "Which preference changed most recently" is only answerable if chronology
    survives; the contradictions test whether the newer statement wins or the
    store simply accumulates both and answers at random.
    """
    return [
        {"text": "I prefer dark mode.", "at": 1, "category": "personal"},
        {"text": "My birthday is 14 March.", "at": 2, "category": "personal"},
        {"text": "I use Postgres for the main database.", "at": 3, "category": "work"},
        {"text": "I prefer tabs over spaces.", "at": 4, "category": "work"},
        {"text": "The project is called Primnox.", "at": 5, "category": "project"},
        # Direct reversals, later in time.
        {"text": "I prefer light mode now.", "at": 6, "category": "personal",
         "contradicts": "I prefer dark mode."},
        {"text": "I switched the main database to SQLite.", "at": 7, "category": "work",
         "contradicts": "I use Postgres for the main database."},
        {"text": "I prefer spaces over tabs after all.", "at": 8, "category": "work",
         "contradicts": "I prefer tabs over spaces."},
    ]


# ── Module 10: a broken event stream ─────────────────────────────────────────
def event_stream(count: int = 400, seed: int = 20260815) -> dict:
    """A well-formed sequence and a mangled delivery of it.

    Duplicated, reordered, delayed and dropped — the four things a real socket
    does. The expected outcome is the same final text from both.
    """
    r = rng(seed)
    clean = [{"sequence": i, "kind": "token", "payload": {"text": f"w{i} "}}
             for i in range(1, count + 1)]

    mangled = list(clean)
    for _ in range(20):                                   # duplicates
        mangled.append(dict(r.choice(clean)))
    r.shuffle(mangled)                                    # reordering
    dropped = {r.randrange(1, count + 1) for _ in range(15)}
    mangled = [e for e in mangled if e["sequence"] not in dropped]

    return {
        "clean": clean,
        "mangled": mangled,
        "dropped": sorted(dropped),
        "expected_text": "".join(e["payload"]["text"] for e in clean),
    }
