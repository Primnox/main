# skills/skill_router.py
import os
import importlib
import inspect
from pathlib import Path
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skills")

SKILL_REGISTRY: dict = {}   # ext → skill class
TRIGGER_MAP: dict = {}       # trigger word → skill class


# ── Dependency validation ─────────────────────────────────────────────────────

def _check_pip_deps(skill_cls) -> list[str]:
    """Return a list of REQUIRES_PIP packages that are not importable."""
    missing = []
    for pkg in getattr(skill_cls, "REQUIRES_PIP", []):
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


# ── Registration ──────────────────────────────────────────────────────────────

def register_skill(skill_cls):
    missing = _check_pip_deps(skill_cls)
    if missing:
        log.warning(
            f"Skipping skill '{skill_cls.name}' — missing pip packages: "
            f"{', '.join(missing)}. Run: pip install {' '.join(missing)}"
        )
        return

    skill = skill_cls()
    log.info(f"Registered skill: {skill.name}")
    for ext in skill.supported_extensions:
        SKILL_REGISTRY[ext.lower()] = skill_cls
    for word in skill.trigger_words:
        TRIGGER_MAP[word.lower()] = skill_cls


# ── Auto-discovery ────────────────────────────────────────────────────────────

def discover_skills():
    """
    Drop a *_skill.py file in skills/ and it auto-registers — no manual wiring.
    Missing REQUIRES_PIP packages cause a warning skip instead of a crash.
    """
    skills_dir = Path(__file__).parent

    # Files that are abstract base classes — never instantiate directly
    _SKIP_FILES = {"base_skill.py", "base_island_skill.py"}

    for file_path in skills_dir.glob("*_skill.py"):
        if file_path.name in _SKIP_FILES:
            continue

        module_name = f"skills.{file_path.stem}"
        try:
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseSkill)
                    and obj is not BaseSkill
                    and not inspect.isabstract(obj)
                ):
                    register_skill(obj)
        except Exception as e:
            log.error(f"Failed to load skill module {module_name}: {e}")


discover_skills()


# ── Lookup helpers ────────────────────────────────────────────────────────────

def get_skill_for_extension(ext: str):
    return SKILL_REGISTRY.get(ext.lower())


def get_skill_for_trigger(text: str):
    if not text:
        return None
    text = text.lower()
    for trigger, skill_cls in TRIGGER_MAP.items():
        if trigger in text:
            return skill_cls
    return None


def list_skills() -> list[dict]:
    """Return describe() dicts for every registered skill (deduped by name)."""
    seen = set()
    out = []
    for skill_cls in list(SKILL_REGISTRY.values()) + list(TRIGGER_MAP.values()):
        if skill_cls.name not in seen:
            seen.add(skill_cls.name)
            try:
                out.append(skill_cls().describe())
            except Exception as e:
                log.warning(f"Skipping skill '{skill_cls.name}' in list — failed to instantiate: {e}")
    return out


# ── Main router ───────────────────────────────────────────────────────────────

def route_skill(
    file_path: str | None = None,
    user_message: str | None = None,
    session_id: str | None = None,
    chat_history: list | None = None,
    metadata: dict | None = None
) -> dict:
    """
    Route to the right skill, build a SkillContext, call skill.run(), and
    return a plain dict for backward compatibility with server.py.
    """
    log.info(f"Routing skill — path={file_path!r}, message={str(user_message)[:60]!r}")

    skill_cls = None
    if file_path:
        ext = Path(file_path).suffix.lstrip(".").lower()
        skill_cls = get_skill_for_extension(ext)
        # Do NOT fall through to trigger lookup when a file is attached —
        # an unrecognised extension should return no-match, not accidentally
        # fire a trigger-word skill using the user's message text.
        if not skill_cls:
            log.warning(f"No skill registered for extension '.{ext}'.")
            return {"success": False, "error": f"No skill available for .{ext} files."}
    else:
        skill_cls = get_skill_for_trigger(user_message)

    if not skill_cls:
        log.warning("No matching skill found.")
        return {"success": False, "error": "No matching skill found."}

    skill = skill_cls()
    log.info(f"Executing skill: {skill.name}")

    ctx = SkillContext(
        file_path=file_path,
        user_message=user_message,
        session_id=session_id,
        chat_history=chat_history or [],
        metadata=metadata or {}
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
