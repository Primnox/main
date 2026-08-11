"""Renders the memory DB out to plain, editable Markdown files — one per
topic — mirrored into a local git repo.

Why this exists: a SQLite table of dedup'd strings is not something a user
can actually audit. This makes "what does Primnox think it knows about me"
answerable by opening a folder, and "that's wrong, forget it" as simple as
deleting a line and re-rendering.

The DB stays the source of truth for search (FTS5 is fast, keep it). This is
a generated view of that data, regenerated wholesale on each call rather than
incrementally patched — memory counts here are small enough (hundreds, not
millions) that a full re-render is cheap, and "wholesale regenerate" means
there's no incremental-sync state to get out of sync with the DB.
"""
import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from logger import get_logger
from memory import list_memories, memory_score
from settings_manager import load_settings

log = get_logger("memory_mirror")

MEMORY_DIR = Path.home() / "Documents" / "Primnox" / "Memory"

_LOCAL_ONLY_MODELS = {"Ollama_Local", "LlamaCpp_Local"}

# Primnox runs windowless on Windows — without this, every git subprocess
# call here briefly flashes a console window (same fix as project_context.py).
_POPEN_KWARGS = {}
if sys.platform == "win32":
    _POPEN_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "misc"


def _topic_key(mem: dict) -> str:
    return mem.get("topic") or mem.get("category") or "misc"


def _topic_title(topic_key: str) -> str:
    # "project:primnox" -> "Project: Primnox"; "session" -> "Session"
    return ": ".join(part.replace("-", " ").replace("_", " ").strip().capitalize()
                      for part in topic_key.split(":"))


def _is_full_local() -> bool:
    try:
        return load_settings().get("active_model") in _LOCAL_ONLY_MODELS
    except Exception:
        return False


def _render_text(text: str, full_local: bool) -> str:
    """Same cloud-boundary logic as the chat Privacy Mirror: nothing leaves
    the device in full-local mode, so there's nothing to scrub. Otherwise the
    on-disk file gets the same PII scrub a cloud-bound message would, so
    reading your own memory folder later doesn't hand you (or anything else
    with filesystem access) raw PII by default.
    """
    if full_local or not text:
        return text
    try:
        from privacy_mirror import redact_text
        return redact_text(text)
    except Exception as e:
        log.warning(f"Memory mirror scrub failed, writing raw text: {e}")
        return text


# Per-topic fingerprint of the last render, so a render with nothing changed
# can skip straight past the expensive part (PII scrubbing + formatting every
# line) instead of redoing it just to discover the output is identical. Reset
# on process restart, which is fine — Primnox runs continuously in the tray,
# so this is a same-session cache, not a durability guarantee.
_last_fingerprint: dict = {}


def _topic_fingerprint(mems: list, full_local: bool) -> str:
    # Deliberately built from data already in hand (key + access_count), not
    # from the memory text — computing this must stay cheap, or it defeats
    # the point of checking it before doing the expensive rendering work.
    parts = sorted(f"{m['key']}:{m.get('access_count', 0)}" for m in mems)
    parts.append(f"full_local:{full_local}")  # a privacy-mode flip must force a re-scrub
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _run_git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args, cwd=str(cwd), capture_output=True, text=True, timeout=10, **_POPEN_KWARGS,
    )


def _ensure_git_repo(dir_path: Path) -> None:
    if (dir_path / ".git").exists():
        return
    try:
        _run_git(["init", "-q"], dir_path)
    except Exception as e:
        log.warning(f"Could not init memory mirror git repo: {e}")


def _commit_if_dirty(dir_path: Path, message: str) -> None:
    try:
        status = _run_git(["status", "--porcelain"], dir_path)
        if status.returncode != 0 or not status.stdout.strip():
            return
        _run_git(["add", "-A"], dir_path)
        _run_git(
            ["-c", "user.name=Primnox", "-c", "user.email=primnox@local", "commit", "-q", "-m", message],
            dir_path,
        )
    except Exception as e:
        log.warning(f"Memory mirror commit failed: {e}")


def render_memory_mirror() -> int:
    """Regenerate the Markdown mirror. Returns the number of topic files written."""
    try:
        memories = list_memories(include_stale=False)
    except Exception as e:
        log.error(f"Could not load memories for mirror: {e}")
        return 0

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_git_repo(MEMORY_DIR)
    full_local = _is_full_local()

    groups: dict = defaultdict(list)
    for mem in memories:
        groups[_topic_key(mem)].append(mem)

    written_slugs = set()
    for topic_key, mems in groups.items():
        slug = _slug(topic_key)
        written_slugs.add(slug)

        fp = _topic_fingerprint(mems, full_local)
        if _last_fingerprint.get(slug) == fp and (MEMORY_DIR / f"{slug}.md").exists():
            continue  # identity + recall counts unchanged since last render — nothing to do
        _last_fingerprint[slug] = fp

        mems.sort(key=lambda m: memory_score(m["timestamp"], m["access_count"]), reverse=True)

        lines = [f"# {_topic_title(topic_key)}", ""]
        for mem in mems:
            text = _render_text(mem["text"], full_local)
            date = (mem.get("timestamp") or "")[:10]
            tag = "" if mem.get("provenance", "explicit") == "explicit" else " _(Primnox's guess — correct me if wrong)_"
            lines.append(f"- {text}{tag}  ")
            lines.append(f"  <sub>{date}</sub>")
        content = "\n".join(lines) + "\n"

        path = MEMORY_DIR / f"{slug}.md"
        try:
            existing = path.read_text(encoding="utf-8") if path.exists() else None
        except Exception:
            existing = None
        if existing != content:
            path.write_text(content, encoding="utf-8")

    # Drop files (and cached fingerprints) for topics that no longer have any
    # live memories, so neither accumulates empty husks as things go stale.
    for existing_file in MEMORY_DIR.glob("*.md"):
        if existing_file.stem not in written_slugs:
            try:
                existing_file.unlink()
            except Exception:
                pass
    for stale_slug in set(_last_fingerprint) - written_slugs:
        del _last_fingerprint[stale_slug]

    _commit_if_dirty(MEMORY_DIR, f"memory: sync {len(memories)} memories across {len(groups)} topics")

    return len(groups)
