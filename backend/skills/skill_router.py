# skills/skill_router.py
import ast
import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from skills.adapted_skill import parse_skill_md, make_adapted_skill_class
from logger import get_logger

log = get_logger("skills")

SKILL_REGISTRY: dict = {}   # ext → skill class (or _SkillMeta stub, see below)
TRIGGER_MAP: dict = {}       # trigger word → skill class (or _SkillMeta stub)
CLAUDE_SKILLS_REGISTRY: dict = {}  # name → dynamically-created skill class (SKILL.md packages)


# ── Dependency validation ─────────────────────────────────────────────────────

def _normalize_pip_dep(dep) -> tuple[str, str]:
    """REQUIRES_PIP entries are usually just the import name, which usually
    matches the pip package name — but not always (`import PIL` comes from
    `pip install Pillow`, `import pptx` comes from `pip install
    python-pptx`). An entry needing a different install name can be a
    (import_name, pip_name) tuple instead of a bare string."""
    if isinstance(dep, tuple):
        return dep
    return (dep, dep)


def _check_pip_deps_from_list(requires_pip) -> list[tuple[str, str]]:
    """Return (import_name, pip_name) for each dep in `requires_pip` that
    isn't importable — the check itself never imports anything beyond the
    dependency probe, so it costs nothing extra for skills that turn out to
    be unusable."""
    missing = []
    for dep in requires_pip:
        import_name, pip_name = _normalize_pip_dep(dep)
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append((import_name, pip_name))
    return missing


def _check_pip_deps(skill_cls) -> list[tuple[str, str]]:
    return _check_pip_deps_from_list(getattr(skill_cls, "REQUIRES_PIP", []))


# ── Lazy metadata (see discover_skills docstring) ─────────────────────────────

@dataclass(eq=False)
class _SkillMeta:
    """Routing metadata extracted from a *_skill.py file via static AST
    parsing, WITHOUT importing the module. Stands in for the real skill
    class in SKILL_REGISTRY/TRIGGER_MAP until the skill is actually about to
    run — `_resolve_skill_class()` does the real import at that point and
    caches the resolved class back into the registries.

    `eq=False` keeps identity-based equality/hashing (the default for a
    plain object) instead of dataclass's usual field-based `__eq__`, which
    would make instances unhashable — callers put these in sets to dedupe."""
    module_name: str
    class_name: str
    name: str
    description: str = ""
    trigger_words: tuple = field(default_factory=tuple)
    supported_extensions: tuple = field(default_factory=tuple)
    creation_artifact_words: tuple = field(default_factory=tuple)
    REQUIRES_PIP: tuple = field(default_factory=tuple)
    is_island_skill: bool = False


def _literal_or_default(node, default):
    if node is None:
        return default
    try:
        return ast.literal_eval(node)
    except Exception:
        return default


def _extract_skill_meta(file_path: Path, module_name: str) -> "_SkillMeta | None":
    """Statically parses a *_skill.py file to pull out routing metadata —
    name, description, trigger words, extensions, pip deps — without
    importing it (and whatever heavy third-party libraries it might pull in
    at module scope). Returns None if no recognizable BaseSkill/
    BaseIslandSkill subclass with simple literal class attributes is found;
    callers should fall back to a real import in that case rather than
    silently dropping the skill — this is a fast path, not a guarantee."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except Exception:
        return None

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = [b.id for b in node.bases if isinstance(b, ast.Name)]
        if "BaseSkill" not in base_names and "BaseIslandSkill" not in base_names:
            continue

        values = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                values[stmt.targets[0].id] = stmt.value

        return _SkillMeta(
            module_name=module_name,
            class_name=node.name,
            name=_literal_or_default(values.get("name"), node.name),
            description=_literal_or_default(values.get("description"), ""),
            trigger_words=tuple(_literal_or_default(values.get("trigger_words"), ())),
            supported_extensions=tuple(_literal_or_default(values.get("supported_extensions"), ())),
            creation_artifact_words=tuple(_literal_or_default(values.get("creation_artifact_words"), ())),
            REQUIRES_PIP=tuple(_literal_or_default(values.get("REQUIRES_PIP"), ())),
            is_island_skill="BaseIslandSkill" in base_names,
        )
    return None


def _resolve_skill_class(entry):
    """`entry` is either an already-imported BaseSkill subclass (island
    skills, or anything the static-parse fallback already imported) or a
    lazy `_SkillMeta` stub. Returns the real class, importing it — and
    caching the resolved class back into SKILL_REGISTRY/TRIGGER_MAP so
    later lookups skip the metadata step — on first use."""
    if isinstance(entry, type):
        return entry

    try:
        module = importlib.import_module(entry.module_name)
        skill_cls = getattr(module, entry.class_name)
    except Exception as e:
        log.error(f"Failed to lazily load skill '{entry.name}': {e}")
        return None

    for ext in entry.supported_extensions:
        if SKILL_REGISTRY.get(ext.lower()) is entry:
            SKILL_REGISTRY[ext.lower()] = skill_cls
    for word in entry.trigger_words:
        if TRIGGER_MAP.get(word.lower()) is entry:
            TRIGGER_MAP[word.lower()] = skill_cls
    return skill_cls


# ── Registration ──────────────────────────────────────────────────────────────

def register_skill(skill_cls):
    """Eager path: used for island skills (need a live instance from boot
    for background polling — laziness doesn't apply to a skill whose whole
    job is running on a timer) and as the fallback when a *_skill.py file
    can't be statically parsed."""
    missing = _check_pip_deps(skill_cls)
    if missing:
        pip_names = [pip_name for _, pip_name in missing]
        log.warning(
            f"Skipping skill '{skill_cls.name}' — missing pip packages: "
            f"{', '.join(pip_names)}. Run: pip install {' '.join(pip_names)}"
        )
        return

    skill = skill_cls()
    log.info(f"Registered skill: {skill.name}")
    for ext in skill.supported_extensions:
        SKILL_REGISTRY[ext.lower()] = skill_cls
    for word in skill.trigger_words:
        TRIGGER_MAP[word.lower()] = skill_cls


def _discover_via_import(module_name: str):
    """The pre-lazy-loading discovery path — imports the module up front and
    registers every BaseSkill subclass found in it. Used for island skills
    (always eager) and as a fallback when static AST parsing can't make
    sense of a file (e.g. dynamically-built class attributes)."""
    try:
        module = importlib.import_module(module_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseSkill)
                and obj is not BaseSkill
                and not inspect.isabstract(obj)
            ):
                register_skill(obj)
    except Exception as e:
        log.error(f"Failed to load skill module {module_name}: {e}")


# ── Claude Skill (SKILL.md) discovery ─────────────────────────────────────────

def _claude_skills_dir() -> Path:
    return Path(__file__).parent / "claude_skills"


def _discover_claude_skills():
    """Second, fully additive discovery pass: real Anthropic Claude Skill
    packages (SKILL.md format) dropped into skills/claude_skills/<name>/.
    Runs after the *_skill.py pass and only ever adds new keys to
    CLAUDE_SKILLS_REGISTRY, so it can't affect existing skills' lazy-loading
    or pip-dep-check behavior. One malformed package is logged and skipped
    rather than breaking discovery of the others."""
    claude_skills_dir = _claude_skills_dir()
    if not claude_skills_dir.is_dir():
        return

    for folder in sorted(p for p in claude_skills_dir.iterdir() if p.is_dir()):
        skill_md = folder / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            parsed = parse_skill_md(skill_md)
        except Exception as e:
            log.warning(f"Skipping malformed SKILL.md at {skill_md}: {e}")
            continue

        skill_cls = make_adapted_skill_class(folder, parsed)
        CLAUDE_SKILLS_REGISTRY[parsed.name.lower().replace(" ", "_")] = skill_cls
        # Document skills also claim their file types, so an attached
        # .pdf/.docx/.xlsx/.pptx routes here by exact extension lookup
        # without needing the semantic router (or a model call) at all.
        for ext in skill_cls.supported_extensions:
            SKILL_REGISTRY[ext.lower()] = skill_cls
        log.info(f"Registered Claude Skill: {parsed.name} ({folder})")


# ── Auto-discovery ────────────────────────────────────────────────────────────

def discover_skills():
    """
    Drop a *_skill.py file in skills/ and it auto-registers — no manual wiring.
    Missing REQUIRES_PIP packages cause a warning skip instead of a crash.

    Most skills are registered *lazily*: their routing metadata (name,
    triggers, extensions, pip deps) is extracted via static AST parsing, and
    the actual module — along with whatever heavy third-party libraries it
    imports inside execute() — is only imported the first time the skill is
    actually invoked (see _resolve_skill_class). A skill whose pip deps
    aren't installed costs zero import time this way, instead of being
    imported first and only then discovered to be unusable.

    Island skills (BaseIslandSkill subclasses, e.g. calendar) are the
    exception — FeedManager needs a live instance from boot to poll on a
    timer, so laziness doesn't apply to them; they're imported immediately,
    same as before this file gained the lazy path.
    """
    skills_dir = Path(__file__).parent

    # Files that are abstract base classes — never instantiate directly
    _SKIP_FILES = {"base_skill.py", "base_island_skill.py"}

    for file_path in skills_dir.glob("*_skill.py"):
        if file_path.name in _SKIP_FILES:
            continue

        module_name = f"skills.{file_path.stem}"
        meta = _extract_skill_meta(file_path, module_name)

        if meta is None:
            _discover_via_import(module_name)
            continue

        if meta.is_island_skill:
            _discover_via_import(module_name)
            continue

        missing = _check_pip_deps_from_list(meta.REQUIRES_PIP)
        if missing:
            pip_names = [pip_name for _, pip_name in missing]
            log.warning(
                f"Skipping skill '{meta.name}' — missing pip packages: "
                f"{', '.join(pip_names)}. Run: pip install {' '.join(pip_names)}"
            )
            continue

        for ext in meta.supported_extensions:
            SKILL_REGISTRY[ext.lower()] = meta
        for word in meta.trigger_words:
            TRIGGER_MAP[word.lower()] = meta
        log.info(f"Registered skill (lazy): {meta.name}")

    _discover_claude_skills()


discover_skills()


# ── Lookup helpers ────────────────────────────────────────────────────────────

def get_skill_for_extension(ext: str):
    return SKILL_REGISTRY.get(ext.lower())


def get_skill_for_trigger(text: str):
    if not text:
        return None
    lowered = text.lower()
    for trigger, skill_cls in TRIGGER_MAP.items():
        if trigger in lowered:
            return skill_cls

    # Exact trigger phrases miss real phrasing ("craete me a pdf where...").
    # Fall back to a tolerant creation-intent check for skills that declare
    # `creation_artifact_words` (currently the file-generation skills) — order
    # independent and tolerant of a misspelled verb, unlike the phrase match above.
    from skills.intent_utils import expresses_creation_intent
    checked = set()
    for skill_cls in TRIGGER_MAP.values():
        if skill_cls in checked:
            continue
        checked.add(skill_cls)
        artifact_words = getattr(skill_cls, "creation_artifact_words", ())
        if artifact_words and expresses_creation_intent(text, artifact_words):
            return skill_cls
    return None


def resolve_skill_for_message(text: str):
    """Pick the skill for a plain chat message — the entry point core.py uses.

    Asks semantic_router.classify() first (understands intent, and is the
    only way the SKILL.md packages are reachable at all, since they carry no
    trigger words). Falls back to the legacy substring/creation-verb match
    when the model is unreachable or returns nothing usable — offline and
    provider-down sessions keep whatever routing they had before, rather
    than losing skills entirely.
    """
    if not text:
        return None

    from skills.semantic_router import classify
    name = classify(text)
    if name:
        entry = get_skill_by_name(name)
        if entry:
            return entry
        # classify() validates against the catalog, so this means the
        # catalog and the registries disagree — worth surfacing rather than
        # silently pretending nothing matched.
        log.warning(f"Semantic router returned unresolvable skill '{name}'; using trigger words.")

    return get_skill_for_trigger(text)


def get_skill_by_name(name: str):
    """Resolve a skill class by its describe()-style name (lowercase,
    underscored) — used for explicit invocation (e.g. the LLM's `use_skill`
    tool) where the caller names a skill directly rather than relying on
    trigger-word/extension matching. Works uniformly for real classes and
    lazy _SkillMeta stubs — both expose a plain `.name` attribute."""
    if not name:
        return None
    target = name.lower().replace(" ", "_")
    for skill_cls in list(SKILL_REGISTRY.values()) + list(TRIGGER_MAP.values()) + list(CLAUDE_SKILLS_REGISTRY.values()):
        if skill_cls.name.lower().replace(" ", "_") == target:
            return skill_cls
    return None


def list_skills() -> list[dict]:
    """Return {name, description, triggers} for every registered skill
    (deduped by name) — built directly from routing metadata, never
    instantiating (or even importing) a skill just to list it. This used to
    call describe() on a fresh instance of every skill, which meant listing
    them required importing all of them regardless of whether any would
    ever actually run that session."""
    seen = set()
    out = []
    for entry in list(SKILL_REGISTRY.values()) + list(TRIGGER_MAP.values()) + list(CLAUDE_SKILLS_REGISTRY.values()):
        name = getattr(entry, "name", None)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            "name": name.lower().replace(" ", "_"),
            "description": getattr(entry, "description", ""),
            "triggers": {
                "extensions": tuple(getattr(entry, "supported_extensions", ())),
                "words": tuple(getattr(entry, "trigger_words", ())),
            },
        })
    return out


# ── Main router ───────────────────────────────────────────────────────────────

def route_skill(
    file_path: str | None = None,
    user_message: str | None = None,
    session_id: str | None = None,
    chat_history: list | None = None,
    metadata: dict | None = None,
    skill_name: str | None = None,
    progress=None,
) -> dict:
    """
    Route to the right skill, build a SkillContext, call skill.run(), and
    return a plain dict for backward compatibility with server.py.

    `skill_name`, when given, bypasses extension/trigger-word matching and
    resolves the skill directly by its describe()-style name — used by the
    LLM's `use_skill` tool, which names a skill explicitly rather than
    relying on the user's phrasing to match a trigger word.
    """
    log.info(f"Routing skill — path={file_path!r}, message={str(user_message)[:60]!r}, skill_name={skill_name!r}")

    if skill_name:
        skill_entry = get_skill_by_name(skill_name)
        if not skill_entry:
            log.warning(f"No skill registered with name '{skill_name}'.")
            return {"success": False, "error": f"No skill named '{skill_name}'. Use list_skills to see available names."}
    elif file_path:
        ext = Path(file_path).suffix.lstrip(".").lower()
        skill_entry = get_skill_for_extension(ext)
        # Do NOT fall through to trigger lookup when a file is attached —
        # an unrecognised extension should return no-match, not accidentally
        # fire a trigger-word skill using the user's message text.
        if not skill_entry:
            log.warning(f"No skill registered for extension '.{ext}'.")
            return {"success": False, "error": f"No skill available for .{ext} files."}
    else:
        skill_entry = resolve_skill_for_message(user_message)

    if not skill_entry:
        log.warning("No matching skill found.")
        return {"success": False, "error": "No matching skill found."}

    skill_cls = _resolve_skill_class(skill_entry)
    if not skill_cls:
        return {"success": False, "error": f"Skill '{getattr(skill_entry, 'name', skill_name)}' failed to load."}

    skill = skill_cls()
    log.info(f"Executing skill: {skill.name}")

    ctx = SkillContext(
        file_path=file_path,
        user_message=user_message,
        session_id=session_id,
        chat_history=chat_history or [],
        metadata=metadata or {},
        progress=progress,
    )

    result: SkillResult = skill.run(ctx)

    return {
        "success": result.success,
        "output_text": result.output_text,
        "output_path": result.output_path,
        "confidence": result.confidence,
        "elapsed_ms": result.elapsed_ms,
        "skill_name": skill.name,
        "error": result.error,
        **result.extras
    }
