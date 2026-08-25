"""Graphify: structural code intelligence.

Graphify is not a better grep, and the failure this module is written
against is the assumption that it was. Using graph proximity for a question
that needed lexical precision — "where is API_KEY handled?" — produced worse
answers than a plain search, more slowly. So the division of labour is fixed
and narrow:

    exact string, filename, symbol lookup   → search (grep)
    where is this defined                   → search + file read
    what calls this                         → Graphify
    what depends on this module             → Graphify
    what breaks if this changes             → Graphify + search + history

There is no "graph before grep" hook here, and nothing in this module should
ever be called speculatively. It is selected by the retrieval router when a
question is genuinely structural.

Three things the architecture demands and this implements:

* **Corpus filtering.** A graph over `node_modules`, minified bundles and
  generated protobuf stubs answers every question with noise. The index
  covers the code a person wrote, and skips the rest by directory, by glob,
  by size, and by a minification heuristic.
* **Stale-index detection.** Every indexed file records its size, mtime and
  content hash. Query results carry a `stale` flag when the file on disk no
  longer matches, so an obsolete answer is never returned confidently.
* **Honest confidence.** Python is parsed with `ast`, which is exact. Other
  languages are matched with regexes, which is not, and their edges carry a
  lower confidence that survives all the way out to the caller.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import os
import re
from pathlib import Path

from v2 import ids, store
from v2.world_model import ValidationError, entity_id, project_id

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.graphify")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.graphify")


# ── Corpus rules ─────────────────────────────────────────────────────────────

# Directories that are never source the user wrote. Dependencies, build
# output, caches and virtual environments.
DEFAULT_EXCLUDE_DIRS: set[str] = {
    ".git", ".hg", ".svn", ".idea", ".vscode",
    "node_modules", "bower_components", "vendor", "third_party", "site-packages",
    "dist", "build", "out", "target", ".next", ".nuxt", ".output",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    ".venv", "venv", "env", ".env",
    "coverage", "htmlcov", ".gradle", "Pods",
}

# Files that are generated, minified or otherwise not hand-written.
DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = (
    "*.min.js", "*.min.css", "*.bundle.js", "*.map", "*.lock",
    "*_pb2.py", "*_pb2_grpc.py", "*.pb.go", "*.g.dart",
    "*.generated.*", "*-generated.*", "*.d.ts",
)

# Anything larger than this is either data or generated; parsing it costs
# more than the structure it would contribute is worth.
MAX_FILE_BYTES = 1_000_000

# A file whose longest line is this many characters is minified, whatever its
# extension claims. Catches bundles that dodge the glob rules.
MINIFIED_LINE_LENGTH = 2000

PYTHON_SUFFIXES = {".py", ".pyi"}
JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
INDEXABLE_SUFFIXES = PYTHON_SUFFIXES | JS_SUFFIXES

# Confidence attached to edges by how they were derived. Python's AST is
# exact; a regex over TypeScript is a good guess and says so.
CONFIDENCE_AST = 1.0
CONFIDENCE_REGEX = 0.6

# Words that look like calls in a regex scan but are language syntax.
_JS_KEYWORDS = {
    "if", "for", "while", "switch", "catch", "return", "function", "typeof", "new",
    "await", "yield", "delete", "void", "in", "of", "do", "else", "case", "throw",
    "super", "this", "constructor", "import", "export", "require", "class", "let",
    "const", "var", "async", "instanceof",
}

_JS_IMPORT = re.compile(
    r"""(?:^|\s)(?:import\s[^;]*?from\s*|export\s[^;]*?from\s*|import\s*)['"]([^'"]+)['"]"""
    r"""|require\(\s*['"]([^'"]+)['"]\s*\)""",
    re.M,
)
_JS_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M
)
_JS_ARROW = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
    re.M,
)
_JS_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)", re.M)
_JS_CALL = re.compile(r"(?:^|[^\w$.])([A-Za-z_$][\w$]*)\s*\(")


_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS code_files (
        id          TEXT PRIMARY KEY,
        project_id  TEXT,
        root        TEXT NOT NULL,
        rel_path    TEXT NOT NULL,
        module      TEXT,
        language    TEXT NOT NULL,
        size        INTEGER NOT NULL,
        mtime       REAL NOT NULL,
        hash        TEXT NOT NULL,
        indexed_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_code_files_root ON code_files(root, rel_path)",
    "CREATE INDEX IF NOT EXISTS idx_code_files_module ON code_files(module)",
    """
    CREATE TABLE IF NOT EXISTS symbols (
        id          TEXT PRIMARY KEY,
        file_id     TEXT NOT NULL,
        project_id  TEXT,
        name        TEXT NOT NULL,
        qualname    TEXT NOT NULL,
        kind        TEXT NOT NULL,
        line        INTEGER NOT NULL,
        end_line    INTEGER,
        language    TEXT NOT NULL,
        confidence  REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id)",
    """
    CREATE TABLE IF NOT EXISTS code_edges (
        id            TEXT PRIMARY KEY,
        project_id    TEXT,
        kind          TEXT NOT NULL,
        src_file      TEXT NOT NULL,
        src_symbol    TEXT,
        src_qualname  TEXT,
        target_name   TEXT NOT NULL,
        target_symbol TEXT,
        target_file   TEXT,
        line          INTEGER,
        confidence    REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_edges_target ON code_edges(kind, target_name)",
    "CREATE INDEX IF NOT EXISTS idx_edges_src ON code_edges(kind, src_file)",
    "CREATE INDEX IF NOT EXISTS idx_edges_target_file ON code_edges(kind, target_file)",
]


def _init() -> None:
    store.ensure_schema("graphify", _SCHEMA)


# ── Corpus walking ───────────────────────────────────────────────────────────


def _load_gitignore(root: Path) -> list[str]:
    """Read simple patterns from .gitignore, best effort.

    Deliberately partial: plain names and globs are honoured, negations and
    path anchoring are not. A repository's own ignore file is the best
    available statement of what is generated, and getting most of it right
    beats indexing `dist/` because full gitignore semantics were too much
    work.
    """
    path = root / ".gitignore"
    if not path.is_file():
        return []
    patterns: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#") or entry.startswith("!"):
                continue
            patterns.append(entry.rstrip("/").lstrip("/"))
    except OSError as exc:  # pragma: no cover - unreadable ignore file
        log.debug("could not read .gitignore (%s)", exc)
    return patterns


def _looks_minified(text: str) -> bool:
    """True if the file is machine-generated regardless of its extension."""
    return any(len(line) > MINIFIED_LINE_LENGTH for line in text.splitlines()[:200])


def _peek_minified(path: Path, probe_bytes: int = 65536) -> bool:
    """Apply the minification heuristic without reading the whole file.

    This has to happen during the walk rather than at parse time, so that
    "what is in the corpus?" and "what got indexed?" cannot disagree — a
    file excluded at parse time but still listed by the walk would look
    permanently un-indexed to the freshness check.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            chunk = handle.read(probe_bytes)
    except OSError:
        # Unreadable is not part of the corpus either.
        return True
    return _looks_minified(chunk)


def _language(path: Path) -> str | None:
    if path.suffix in PYTHON_SUFFIXES:
        return "python"
    if path.suffix in JS_SUFFIXES:
        return "javascript"
    return None


def walk_corpus(
    root: Path,
    *,
    exclude_dirs: set[str] | None = None,
    exclude_globs: tuple[str, ...] | None = None,
    use_gitignore: bool = True,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> list[Path]:
    """Every file worth indexing under `root`.

    Exposed separately from :func:`index` because "what is even in the
    corpus?" is the first question when a graph answers with noise, and it
    should be answerable without building an index.
    """
    root = Path(root).resolve()
    skip_dirs = DEFAULT_EXCLUDE_DIRS | set(exclude_dirs or ())
    globs = DEFAULT_EXCLUDE_GLOBS + tuple(exclude_globs or ())
    ignored = _load_gitignore(root) if use_gitignore else []

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs
            and not d.startswith(".")
            and not any(fnmatch.fnmatch(d, pattern) for pattern in ignored)
        ]
        for filename in filenames:
            path = current / filename
            if _language(path) is None:
                continue
            if any(fnmatch.fnmatch(filename, pattern) for pattern in globs):
                continue
            rel = path.relative_to(root).as_posix()
            if any(
                fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(filename, pattern)
                for pattern in ignored
            ):
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            if _peek_minified(path):
                continue
            found.append(path)
    return sorted(found)


def _module_name(rel_path: str) -> str:
    """Dotted module name for a Python file path."""
    parts = rel_path.split("/")
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].rsplit(".", 1)[0]
    return ".".join(p for p in parts if p)


# ── Parsing ──────────────────────────────────────────────────────────────────


class _PythonVisitor(ast.NodeVisitor):
    """Collect definitions, imports and call sites with their scope.

    Calls are attributed to the enclosing function or class, which is what
    makes "what calls this" answerable at symbol granularity instead of only
    at file granularity.
    """

    def __init__(self, module: str) -> None:
        self.module = module
        self.scope: list[str] = []
        self.symbols: list[dict] = []
        self.imports: list[dict] = []
        self.calls: list[dict] = []

    # -- definitions --
    def _definition(self, node, kind: str) -> None:
        qualname = ".".join(self.scope + [node.name])
        self.symbols.append(
            {
                "name": node.name,
                "qualname": qualname,
                "kind": kind,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", None),
            }
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):  # noqa: N802 - ast API
        self._definition(node, "function")

    def visit_AsyncFunctionDef(self, node):  # noqa: N802 - ast API
        self._definition(node, "function")

    def visit_ClassDef(self, node):  # noqa: N802 - ast API
        self._definition(node, "class")

    # -- imports --
    def visit_Import(self, node):  # noqa: N802 - ast API
        for alias in node.names:
            self.imports.append({"module": alias.name, "line": node.lineno, "level": 0})
        self.generic_visit(node)

    def visit_ImportFrom(self, node):  # noqa: N802 - ast API
        # A relative import records its level so it can be resolved against
        # the importing file's own package rather than the project root.
        self.imports.append(
            {"module": node.module or "", "line": node.lineno, "level": node.level or 0}
        )
        self.generic_visit(node)

    # -- calls --
    def visit_Call(self, node):  # noqa: N802 - ast API
        target = None
        func = node.func
        if isinstance(func, ast.Name):
            target = func.id
        elif isinstance(func, ast.Attribute):
            target = func.attr
        if target:
            self.calls.append(
                {
                    "target": target,
                    "line": node.lineno,
                    "scope": ".".join(self.scope) or None,
                }
            )
        self.generic_visit(node)


def _parse_python(text: str, module: str) -> dict:
    """Parse Python exactly, or report the syntax error and index nothing.

    A file that does not parse is a fact worth recording — a half-parsed
    file would silently drop the symbols after the error, and a graph with
    invisible holes is worse than one that admits them.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"symbols": [], "imports": [], "calls": [], "error": f"syntax error at line {exc.lineno}"}
    visitor = _PythonVisitor(module)
    visitor.visit(tree)
    return {
        "symbols": visitor.symbols,
        "imports": visitor.imports,
        "calls": visitor.calls,
        "error": None,
    }


def _parse_javascript(text: str) -> dict:
    """Approximate JS/TS structure with regexes.

    Everything found here is marked at regex confidence. This exists so that
    a TypeScript frontend is not a blind spot in dependency and impact
    questions — not because a regex understands JavaScript.
    """
    symbols: list[dict] = []
    imports: list[dict] = []
    calls: list[dict] = []

    lines = text.splitlines()
    line_starts: list[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line) + 1

    def line_of(position: int) -> int:
        low, high = 0, len(line_starts) - 1
        while low <= high:
            mid = (low + high) // 2
            if line_starts[mid] <= position:
                low = mid + 1
            else:
                high = mid - 1
        return max(1, low)

    for pattern, kind in ((_JS_FUNCTION, "function"), (_JS_ARROW, "function"), (_JS_CLASS, "class")):
        for match in pattern.finditer(text):
            name = match.group(1)
            symbols.append(
                {
                    "name": name,
                    "qualname": name,
                    "kind": kind,
                    "line": line_of(match.start()),
                    "end_line": None,
                }
            )

    for match in _JS_IMPORT.finditer(text):
        module = match.group(1) or match.group(2)
        if module:
            imports.append({"module": module, "line": line_of(match.start()), "level": 0})

    defined = {s["name"] for s in symbols}
    for match in _JS_CALL.finditer(text):
        name = match.group(1)
        if name in _JS_KEYWORDS:
            continue
        line = line_of(match.start())
        # Skip the declaration site itself, which matches the call pattern.
        if name in defined and any(s["name"] == name and s["line"] == line for s in symbols):
            continue
        calls.append({"target": name, "line": line, "scope": None})

    return {"symbols": symbols, "imports": imports, "calls": calls, "error": None}


# ── Indexing ─────────────────────────────────────────────────────────────────


def _file_id(root: Path, rel_path: str, project: str | None) -> str:
    return entity_id("file", rel_path, project) if project else ids.stable_id(
        "entity", "file", str(root), rel_path
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.debug("could not read %s (%s)", path, exc)
        return None


def _index_file(conn, root: Path, path: Path, project: str | None, scope: str | None) -> dict | None:
    """Parse and store one file. Returns a summary, or None if it was skipped."""
    text = _read(path)
    if text is None:
        return None
    if _looks_minified(text):
        return None

    rel = path.relative_to(root).as_posix()
    language = _language(path)
    stat = path.stat()
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:32]
    file_id = _file_id(root, rel, project)
    module = _module_name(rel) if language == "python" else rel

    parsed = (
        _parse_python(text, module) if language == "python" else _parse_javascript(text)
    )
    confidence = CONFIDENCE_AST if language == "python" else CONFIDENCE_REGEX

    conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM code_edges WHERE src_file = ?", (file_id,))
    conn.execute(
        """
        INSERT INTO code_files (id, project_id, root, rel_path, module, language, size, mtime,
                                hash, indexed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            module = excluded.module, language = excluded.language, size = excluded.size,
            mtime = excluded.mtime, hash = excluded.hash, indexed_at = excluded.indexed_at,
            root = excluded.root, rel_path = excluded.rel_path
        """,
        (
            file_id, scope, str(root), rel, module, language, stat.st_size, stat.st_mtime,
            digest, store.utc_now(),
        ),
    )

    for symbol in parsed["symbols"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO symbols (id, file_id, project_id, name, qualname, kind, line,
                                            end_line, language, confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ids.stable_id("entity", "symbol", file_id, symbol["qualname"], symbol["line"]),
                file_id, scope, symbol["name"], symbol["qualname"], symbol["kind"],
                symbol["line"], symbol["end_line"], language, confidence,
            ),
        )

    for imported in parsed["imports"]:
        target = imported["module"]
        if imported.get("level"):
            # Relative import: rebuild the absolute module from the importing
            # file's package, so `from .vault import x` in a/b/c.py resolves
            # against a.b rather than the project root.
            package = module.rsplit(".", max(0, imported["level"] - 1))[0] if "." in module else ""
            parent = ".".join(module.split(".")[: -imported["level"]]) or package
            target = f"{parent}.{target}" if target else parent
        if not target:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO code_edges (id, project_id, kind, src_file, src_symbol,
                                               src_qualname, target_name, target_symbol,
                                               target_file, line, confidence)
            VALUES (?,?, 'imports', ?, NULL, NULL, ?, NULL, NULL, ?, ?)
            """,
            (
                ids.stable_id("relationship", file_id, "imports", target, imported["line"]),
                scope, file_id, target, imported["line"], confidence,
            ),
        )

    for call in parsed["calls"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO code_edges (id, project_id, kind, src_file, src_symbol,
                                               src_qualname, target_name, target_symbol,
                                               target_file, line, confidence)
            VALUES (?,?, 'calls', ?, NULL, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                ids.stable_id("relationship", file_id, "calls", call["target"], call["line"]),
                scope, file_id, call["scope"], call["target"], call["line"], confidence,
            ),
        )

    return {
        "file_id": file_id,
        "rel_path": rel,
        "language": language,
        "symbols": len(parsed["symbols"]),
        "imports": len(parsed["imports"]),
        "calls": len(parsed["calls"]),
        "error": parsed["error"],
    }


def _resolve(conn, scope: str | None) -> int:
    """Link edges to the definitions they refer to.

    Resolution is deliberately conservative: a call is bound to a symbol only
    when exactly one definition in the project has that name. An ambiguous
    name stays unresolved and is still answerable by name, which is honest —
    guessing which `run()` was meant would produce confident wrong answers.
    """
    where, params = ("WHERE project_id IS ?", [scope])

    modules: dict[str, str] = {}
    basenames: dict[str, list[str]] = {}
    for row in conn.execute(f"SELECT id, module, rel_path FROM code_files {where}", params):
        if row["module"]:
            modules[row["module"]] = row["id"]
            basenames.setdefault(row["module"].split(".")[-1], []).append(row["id"])
        stem = row["rel_path"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        basenames.setdefault(stem, []).append(row["id"])

    definitions: dict[str, list[str]] = {}
    for row in conn.execute("SELECT id, name FROM symbols WHERE project_id IS ?", params):
        definitions.setdefault(row["name"], []).append(row["id"])

    resolved = 0
    for row in conn.execute(
        f"SELECT id, kind, target_name FROM code_edges {where}", params
    ).fetchall():
        if row["kind"] == "imports":
            target = row["target_name"]
            file_id = modules.get(target)
            if file_id is None:
                candidates = basenames.get(target.split(".")[-1] if target else "", [])
                file_id = candidates[0] if len(candidates) == 1 else None
            if file_id:
                conn.execute("UPDATE code_edges SET target_file = ? WHERE id = ?", (file_id, row["id"]))
                resolved += 1
        else:
            candidates = definitions.get(row["target_name"], [])
            if len(candidates) == 1:
                conn.execute(
                    "UPDATE code_edges SET target_symbol = ? WHERE id = ?", (candidates[0], row["id"])
                )
                resolved += 1
    return resolved


def index(
    root: str | Path,
    *,
    project: str | None = None,
    exclude_dirs: set[str] | None = None,
    exclude_globs: tuple[str, ...] | None = None,
    use_gitignore: bool = True,
    max_file_bytes: int = MAX_FILE_BYTES,
    link_world_model: bool = False,
) -> dict:
    """Build (or rebuild) the graph for a tree.

    `link_world_model` additionally materialises a `file` entity per indexed
    file and a `contains` edge from the project, so the graph and the world
    model refer to the same objects. It is off by default because indexing
    should stay cheap — a large repository is thousands of files, and most
    callers only want structure.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValidationError(f"{root} is not a directory")
    _init()

    scope = project_id(project)
    files = walk_corpus(
        root,
        exclude_dirs=exclude_dirs,
        exclude_globs=exclude_globs,
        use_gitignore=use_gitignore,
        max_file_bytes=max_file_bytes,
    )

    indexed, skipped, errors = 0, 0, []
    with store.transaction() as conn:
        conn.execute("DELETE FROM code_files WHERE root = ? AND project_id IS ?", (str(root), scope))
        for path in files:
            summary = _index_file(conn, root, path, project, scope)
            if summary is None:
                skipped += 1
                continue
            indexed += 1
            if summary["error"]:
                errors.append({"file": summary["rel_path"], "error": summary["error"]})
        resolved = _resolve(conn, scope)

    if link_world_model:
        _link_world_model(root, project)

    report = {
        "root": str(root),
        "project_id": scope,
        "files_seen": len(files),
        "files_indexed": indexed,
        "files_skipped": skipped,
        "edges_resolved": resolved,
        "errors": errors,
        "indexed_at": store.utc_now(),
    }
    log.info("graphify indexed %s files under %s", indexed, root)
    return report


def _link_world_model(root: Path, project: str | None) -> None:
    """Materialise indexed files as world-model entities under the project."""
    from v2 import world_model

    scope = project_id(project)
    project_entity = None
    if project:
        project_entity = world_model.upsert_entity(
            "project", project if not ids.is_id(project) else str(root.name),
            prov=world_model.SYSTEM_OBSERVED,
        )
    rows = store.connect().execute(
        "SELECT rel_path, language FROM code_files WHERE root = ? AND project_id IS ?",
        (str(root), scope),
    ).fetchall()
    for row in rows:
        entity = world_model.upsert_entity(
            "file", row["rel_path"], project=project,
            attributes={"language": row["language"]},
            prov=world_model.SYSTEM_OBSERVED,
        )
        if project_entity:
            world_model.relate(project_entity["id"], "contains", entity["id"],
                               prov=world_model.SYSTEM_OBSERVED)


# ── Freshness ────────────────────────────────────────────────────────────────


def _stat_of(root: str, rel_path: str) -> tuple[float, int] | None:
    try:
        stat = (Path(root) / rel_path).stat()
    except OSError:
        return None
    return stat.st_mtime, stat.st_size


def _is_stale(row) -> bool:
    """True if the file on disk no longer matches what was indexed."""
    current = _stat_of(row["root"], row["rel_path"])
    if current is None:
        return True
    mtime, size = current
    return size != row["size"] or abs(mtime - row["mtime"]) > 1e-6


def health(root: str | Path, *, project: str | None = None) -> dict:
    """Compare the index against the filesystem.

    Returns the changed, deleted and never-indexed files, so a stale answer
    can be detected and repaired instead of being returned confidently.
    """
    root = Path(root).resolve()
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        "SELECT * FROM code_files WHERE root = ? AND project_id IS ?", (str(root), scope)
    ).fetchall()

    indexed = {row["rel_path"]: row for row in rows}
    changed = [row["rel_path"] for row in rows if _stat_of(row["root"], row["rel_path"]) and _is_stale(row)]
    missing = [row["rel_path"] for row in rows if _stat_of(row["root"], row["rel_path"]) is None]
    on_disk = {p.relative_to(root).as_posix() for p in walk_corpus(root)}
    new = sorted(on_disk - set(indexed))

    return {
        "root": str(root),
        "indexed": len(indexed),
        "changed": sorted(changed),
        "missing": sorted(missing),
        "new": new,
        "healthy": not (changed or missing or new),
    }


def refresh(root: str | Path, *, project: str | None = None) -> dict:
    """Re-index only what actually changed.

    A full rebuild of a large repository on every edit is the reason stale
    indexes get tolerated. Incremental refresh is what makes keeping the
    graph current cheap enough to actually do.
    """
    root = Path(root).resolve()
    status = health(root, project=project)
    if status["healthy"]:
        return {**status, "reindexed": 0, "removed": 0}

    scope = project_id(project)
    reindexed, removed = 0, 0
    with store.transaction() as conn:
        for rel in status["missing"]:
            file_id = _file_id(root, rel, project)
            conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM code_edges WHERE src_file = ?", (file_id,))
            conn.execute("DELETE FROM code_files WHERE id = ?", (file_id,))
            removed += 1
        for rel in status["changed"] + status["new"]:
            path = root / rel
            if not path.is_file():
                continue
            if _index_file(conn, root, path, project, scope) is not None:
                reindexed += 1
        resolved = _resolve(conn, scope)

    return {**health(root, project=project), "reindexed": reindexed, "removed": removed,
            "edges_resolved": resolved}


# ── Queries ──────────────────────────────────────────────────────────────────


def _file_row(file_id: str):
    return store.connect().execute("SELECT * FROM code_files WHERE id = ?", (file_id,)).fetchone()


def _decorate(rows: list[dict]) -> list[dict]:
    """Attach a `stale` flag to query results.

    One stat call per distinct file, cached within the call, so marking a
    result set costs a few syscalls rather than a rescan.
    """
    cache: dict[str, bool] = {}
    for record in rows:
        file_id = record.get("file_id")
        if file_id and file_id not in cache:
            row = _file_row(file_id)
            cache[file_id] = _is_stale(row) if row is not None else True
        record["stale"] = cache.get(file_id, False)
    return rows


def definitions(name: str, *, project: str | None = None, limit: int = 20) -> list[dict]:
    """Where a symbol is defined.

    Included for completeness of the graph API, but note the routing rule:
    "where is X defined" is usually better served by lexical search plus a
    file read. This is for when the graph is already the right tool.
    """
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        """
        SELECT s.*, f.rel_path, f.root, f.language AS file_language
          FROM symbols s JOIN code_files f ON s.file_id = f.id
         WHERE s.name = ? AND s.project_id IS ?
         ORDER BY f.rel_path, s.line LIMIT ?
        """,
        (name, scope, limit),
    ).fetchall()
    return _decorate([dict(r) for r in rows])


def callers(name: str, *, project: str | None = None, limit: int = 100) -> list[dict]:
    """What calls this symbol.

    Matched by name, and additionally by resolved symbol when the name was
    unambiguous. Each result carries the confidence of the edge, so a
    regex-derived TypeScript caller is distinguishable from an AST-derived
    Python one.
    """
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        """
        SELECT e.*, f.rel_path, f.root, f.language
          FROM code_edges e JOIN code_files f ON e.src_file = f.id
         WHERE e.kind = 'calls' AND e.target_name = ? AND e.project_id IS ?
         ORDER BY f.rel_path, e.line LIMIT ?
        """,
        (name, scope, limit),
    ).fetchall()
    return _decorate(
        [
            {
                "file_id": r["src_file"],
                "rel_path": r["rel_path"],
                "caller": r["src_qualname"],
                "target": r["target_name"],
                "line": r["line"],
                "confidence": r["confidence"],
                "language": r["language"],
            }
            for r in rows
        ]
    )


def callees(qualname: str, *, project: str | None = None, limit: int = 100) -> list[dict]:
    """What this function calls.

    Scoped by the enclosing qualified name recorded at parse time, so
    `Vault.unlock` returns what that method calls rather than everything in
    the file.
    """
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        """
        SELECT e.*, f.rel_path, f.root
          FROM code_edges e JOIN code_files f ON e.src_file = f.id
         WHERE e.kind = 'calls' AND e.project_id IS ?
           AND (e.src_qualname = ? OR e.src_qualname LIKE ?)
         ORDER BY e.line LIMIT ?
        """,
        (scope, qualname, f"{qualname}.%", limit),
    ).fetchall()
    return _decorate(
        [
            {
                "file_id": r["src_file"],
                "rel_path": r["rel_path"],
                "caller": r["src_qualname"],
                "target": r["target_name"],
                "line": r["line"],
                "confidence": r["confidence"],
            }
            for r in rows
        ]
    )


def dependencies(rel_path: str, *, project: str | None = None, limit: int = 200) -> list[dict]:
    """What a file imports."""
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        """
        SELECT e.target_name, e.line, e.confidence, e.target_file, f.rel_path AS src_path,
               t.rel_path AS target_path
          FROM code_edges e
          JOIN code_files f ON e.src_file = f.id
     LEFT JOIN code_files t ON e.target_file = t.id
         WHERE e.kind = 'imports' AND f.rel_path = ? AND e.project_id IS ?
         ORDER BY e.line LIMIT ?
        """,
        (rel_path, scope, limit),
    ).fetchall()
    return [
        {
            "module": r["target_name"],
            "line": r["line"],
            "confidence": r["confidence"],
            "resolved_path": r["target_path"],
            "internal": r["target_file"] is not None,
        }
        for r in rows
    ]


def dependents(rel_path: str, *, project: str | None = None, limit: int = 200) -> list[dict]:
    """What imports this file — the question a graph exists to answer."""
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        """
        SELECT e.line, e.confidence, e.target_name, f.id AS file_id, f.rel_path, f.root
          FROM code_edges e
          JOIN code_files f ON e.src_file = f.id
          JOIN code_files t ON e.target_file = t.id
         WHERE e.kind = 'imports' AND t.rel_path = ? AND e.project_id IS ?
         ORDER BY f.rel_path LIMIT ?
        """,
        (rel_path, scope, limit),
    ).fetchall()
    return _decorate(
        [
            {
                "file_id": r["file_id"],
                "rel_path": r["rel_path"],
                "line": r["line"],
                "via": r["target_name"],
                "confidence": r["confidence"],
            }
            for r in rows
        ]
    )


def symbols_in(rel_path: str, *, project: str | None = None, limit: int = 500) -> list[dict]:
    """Every symbol defined in a file, in source order."""
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        """
        SELECT s.name, s.qualname, s.kind, s.line, s.end_line, s.confidence
          FROM symbols s JOIN code_files f ON s.file_id = f.id
         WHERE f.rel_path = ? AND s.project_id IS ?
         ORDER BY s.line LIMIT ?
        """,
        (rel_path, scope, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def impact(
    target: str,
    *,
    project: str | None = None,
    depth: int = 2,
    limit: int = 100,
) -> dict:
    """What could break if this changes.

    `target` is a file path or a symbol name. Impact is the union of direct
    callers and the transitive import closure, bounded by `depth` — an
    unbounded closure in a well-connected codebase returns "everything",
    which is true and useless.

    The result is explicitly labelled as an inference: this is evidence that
    something *could* be affected, not a claim that it will be.
    """
    _init()
    scope = project_id(project)

    direct_callers = callers(target, project=project, limit=limit)
    seed_paths: list[str] = []
    if store.connect().execute(
        "SELECT 1 FROM code_files WHERE rel_path = ? AND project_id IS ?", (target, scope)
    ).fetchone():
        seed_paths.append(target)
    for definition in definitions(target, project=project):
        if definition["rel_path"] not in seed_paths:
            seed_paths.append(definition["rel_path"])

    reached: dict[str, int] = {}
    frontier = list(seed_paths)
    for level in range(1, max(1, depth) + 1):
        next_frontier: list[str] = []
        for path in frontier:
            for record in dependents(path, project=project, limit=limit):
                if record["rel_path"] in reached or record["rel_path"] in seed_paths:
                    continue
                reached[record["rel_path"]] = level
                next_frontier.append(record["rel_path"])
        frontier = next_frontier
        if not frontier:
            break

    tests = sorted(
        path for path in list(reached) + seed_paths
        if "test" in path.rsplit("/", 1)[-1].lower()
    )

    return {
        "target": target,
        "seed_files": seed_paths,
        "callers": direct_callers,
        "dependents": [{"rel_path": path, "distance": level} for path, level in sorted(reached.items())],
        "tests": tests,
        "depth": depth,
        "truncated": len(reached) >= limit,
        # The graph shows reachability, not causation. Labelling this an
        # inference is what keeps "could break" from being reported as "will
        # break".
        "origin": "inferred",
    }


def search_symbols(prefix: str, *, project: str | None = None, limit: int = 50) -> list[dict]:
    """Symbols whose name starts with `prefix` — for disambiguation, not search."""
    _init()
    scope = project_id(project)
    rows = store.connect().execute(
        """
        SELECT s.name, s.qualname, s.kind, s.line, f.rel_path
          FROM symbols s JOIN code_files f ON s.file_id = f.id
         WHERE s.name LIKE ? AND s.project_id IS ?
         ORDER BY s.name LIMIT ?
        """,
        (f"{prefix}%", scope, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def stats(*, project: str | None = None) -> dict:
    """Index size, by language and edge kind."""
    _init()
    scope = project_id(project)
    conn = store.connect()
    files = conn.execute(
        "SELECT language, COUNT(*) AS n FROM code_files WHERE project_id IS ? GROUP BY language",
        (scope,),
    ).fetchall()
    edges = conn.execute(
        "SELECT kind, COUNT(*) AS n FROM code_edges WHERE project_id IS ? GROUP BY kind", (scope,)
    ).fetchall()
    symbol_count = conn.execute(
        "SELECT COUNT(*) AS n FROM symbols WHERE project_id IS ?", (scope,)
    ).fetchone()["n"]
    return {
        "files": {r["language"]: r["n"] for r in files},
        "symbols": symbol_count,
        "edges": {r["kind"]: r["n"] for r in edges},
    }


def purge_project(project: str) -> dict:
    """Delete a project's index."""
    _init()
    scope = project_id(project)
    with store.transaction() as conn:
        symbols = conn.execute("DELETE FROM symbols WHERE project_id = ?", (scope,)).rowcount
        edges = conn.execute("DELETE FROM code_edges WHERE project_id = ?", (scope,)).rowcount
        files = conn.execute("DELETE FROM code_files WHERE project_id = ?", (scope,)).rowcount
    return {
        "project_id": scope,
        "files_deleted": files,
        "symbols_deleted": symbols,
        "edges_deleted": edges,
    }
