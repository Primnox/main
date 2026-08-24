"""In-app guides.

Markdown beside the code, not strings inside it, for the same reason the
provider catalogue is `providers.json`: this is content, it changes on a
different schedule from the runtime, and a guide that requires a rebuild to fix
a sentence is a guide nobody fixes.

Front matter carries the title, a one-line summary and a sort order. The body is
rendered by the same markdown pipeline as a chat reply, so a guide cannot drift
into a second look for headings, tables and code.

WHY THESE ARE SERVED RATHER THAN LINKED. Everything they describe — which
provider is active, whether a breaker is open, what the Privacy Mirror
substituted — is state on this machine. A link to a website would send someone
away from the app to read about the app, and the website cannot see any of it.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("primnox2.guides")

GUIDE_DIR = Path(__file__).parent

# Deliberately not a YAML parser. Three scalar fields do not justify a
# dependency, and a guide with malformed front matter should degrade to "no
# title" rather than fail to load.
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_FIELD = re.compile(r"^([a-z_]+):\s*(.+?)\s*$", re.M)


def _parse(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("could not read guide %s: %s", path.name, exc)
        return None

    meta: dict[str, str] = {}
    body = raw
    match = _FRONT.match(raw)
    if match:
        meta = dict(_FIELD.findall(match.group(1)))
        body = raw[match.end():]

    slug = path.stem
    return {
        "slug": slug,
        "title": meta.get("title", slug.replace("-", " ").capitalize()),
        "summary": meta.get("summary", ""),
        "order": int(meta.get("order", "99")) if meta.get("order", "99").isdigit() else 99,
        "body": body.strip(),
    }


def index() -> list[dict]:
    """Every guide's metadata, in the order they declare. Bodies excluded —
    the list is rendered as a menu and the bodies are most of the payload."""
    guides = [g for g in (_parse(p) for p in sorted(GUIDE_DIR.glob("*.md"))) if g]
    guides.sort(key=lambda g: (g["order"], g["title"]))
    return [{k: v for k, v in g.items() if k != "body"} for g in guides]


def get(slug: str) -> dict | None:
    """One guide, body included. `slug` is a filename stem, so it is validated
    against the actual listing rather than joined onto a path — a slug that
    reaches the filesystem is a directory-traversal bug waiting to happen."""
    if slug not in {g["slug"] for g in index()}:
        return None
    return _parse(GUIDE_DIR / f"{slug}.md")
