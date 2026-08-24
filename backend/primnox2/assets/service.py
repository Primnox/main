"""Asset Service — CRS §2.6.

Chat never parses a file. A file becomes an Asset, ingestion happens as a job,
and chat only ever sees an `asset_id`.

V1 parsed uploads inline in the HTTP handler, on the event loop, which is why
a large PDF froze the whole app and a scanned one silently sent the model an
empty string. Here the handler hashes and returns; everything expensive runs
on a worker and reports through events.

Content addressing means identical bytes deduplicate to one asset (§2.6). Two
uploads of the same PDF cost one ingestion, and the second upload is instant.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import time
from pathlib import Path

from .. import paths
from ..ids import ASSET, new_id
from ..kernel import scheduler
from ..kernel.events import bus
from ..storage import db

now_ms = lambda: int(time.time() * 1000)

# Target size of a retrieval chunk, in characters. Small enough that a hit is
# specific, large enough that a paragraph is not split mid-thought.
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150

_EXT_KIND = {
    ".pdf": "pdf",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".bmp": "image", ".webp": "image", ".tiff": "image",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".flac": "audio",
    ".mp4": "video", ".mov": "video", ".mkv": "video", ".avi": "video",
    ".zip": "archive", ".tar": "archive", ".gz": "archive", ".7z": "archive",
    ".py": "code", ".js": "code", ".ts": "code", ".tsx": "code", ".jsx": "code",
    ".rs": "code", ".go": "code", ".java": "code", ".c": "code", ".h": "code",
    ".cpp": "code", ".cs": "code", ".rb": "code", ".sh": "code", ".sql": "code",
    ".html": "code", ".css": "code", ".json": "code", ".yaml": "code", ".yml": "code",
    ".txt": "text", ".md": "text", ".rst": "text", ".csv": "text", ".log": "text",
}

# Decoded as text directly. Everything else needs an extractor.
_TEXTUAL = {"text", "code"}


def kind_for(name: str) -> str:
    return _EXT_KIND.get(Path(name).suffix.lower(), "other")


# ── Ingestion ────────────────────────────────────────────────────────────────
def ingest_bytes(
    data: bytes,
    original_name: str,
    *,
    source: str = "upload",
    conversation_id: str | None = None,
    turn_id: str | None = None,
) -> dict:
    """Hash, store, register, and queue extraction. Returns immediately.

    The expensive half — extraction, chunking — is an `asset.ingest` job, so
    this stays fast enough to call from a request handler.
    """
    sha = hashlib.sha256(data).hexdigest()

    existing = db.connect().execute(
        "SELECT * FROM assets WHERE sha256=?", (sha,)
    ).fetchone()
    if existing is not None:
        # §2.6 — identical bytes are one asset. Re-uploading a file the user
        # already has is free and produces no second ingestion.
        asset = dict(existing)
        if turn_id:
            attach(turn_id, asset["id"])
        return {**asset, "deduplicated": True}

    path = paths.asset_path(sha)
    if not path.exists():
        path.write_bytes(data)

    aid = new_id(ASSET)
    kind = kind_for(original_name)
    mime = mimetypes.guess_type(original_name)[0]

    with db.tx() as c:
        c.execute(
            "INSERT INTO assets (id,kind,source,original_name,path,sha256,bytes,mime,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?, 'ingesting', ?)",
            (aid, kind, source, original_name, str(path), sha, len(data), mime, now_ms()),
        )
    if turn_id:
        attach(turn_id, aid)

    scheduler.enqueue(
        None, "asset.ingest",
        {"asset_id": aid, "conversation_id": conversation_id, "turn_id": turn_id},
        # Ingestion is pure: same bytes in, same text out. Safe to retry after
        # a crash, which is what lets the boot sweep requeue it (§10.3.1).
        idempotent=True, max_attempts=3, priority=5,
    )
    return {
        "id": aid, "kind": kind, "source": source, "original_name": original_name,
        "sha256": sha, "bytes": len(data), "mime": mime, "status": "ingesting",
        "deduplicated": False,
    }


def attach(turn_id: str, asset_id: str) -> None:
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO turn_assets (turn_id, asset_id) VALUES (?,?)",
                  (turn_id, asset_id))


# ── Extraction ───────────────────────────────────────────────────────────────
def _extract_text(path: Path, kind: str) -> tuple[str | None, dict]:
    """Return (text, metadata). `None` text means "needs OCR", not "empty".

    That distinction is the whole point of this function. V1 collapsed them and
    sent the model an empty string for every scanned PDF, which reads to the
    user as the model ignoring their document.
    """
    meta: dict = {}

    if kind in _TEXTUAL:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), meta
        except OSError as exc:
            return None, {"error": str(exc)}

    if kind == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore
            except ImportError:
                return None, {"ocr_required": True, "reason": "no pdf extractor installed"}
        try:
            reader = PdfReader(str(path))
            pages = [(p.extract_text() or "") for p in reader.pages]
            meta["page_count"] = len(pages)
            text = "\n\n".join(pages).strip()
            if not text:
                # A PDF with pages but no extractable text is a scan.
                meta["ocr_required"] = True
                return None, meta
            return text, meta
        except Exception as exc:
            return None, {"ocr_required": True, "reason": f"{type(exc).__name__}: {exc}"}

    if kind in ("image", "screenshot"):
        # OCR belongs here (V1 has easyocr). Until it is bridged, the asset is
        # honestly marked as needing it rather than pretending to be empty.
        return None, {"ocr_required": True}

    if kind in ("audio", "video"):
        return None, {"transcription_required": True}

    return None, {"unsupported": True}


def _chunk(text: str) -> list[str]:
    """Split on paragraph boundaries, with overlap so a sentence spanning a
    boundary is still retrievable from one chunk."""
    if not text:
        return []
    from ..settings import tunables
    chunk_chars = tunables.get("assets.chunk_chars")
    overlap = tunables.get("assets.chunk_overlap")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_chars:
            current = f"{current}\n\n{para}" if current else para
            continue
        if current:
            chunks.append(current)
        if len(para) <= chunk_chars:
            current = para
            continue
        # A single paragraph longer than a chunk is cut on a stride, keeping
        # an overlap so nothing falls between two cuts.
        step = chunk_chars - overlap
        for i in range(0, len(para), step):
            piece = para[i:i + chunk_chars]
            if piece:
                chunks.append(piece)
        current = ""
    if current:
        chunks.append(current)
    return chunks


def _run_ingest(sched, job: dict) -> None:
    """`asset.ingest` — hash → store → extract → chunk → ready."""
    payload = json.loads(job["payload"])
    asset_id = payload["asset_id"]
    conversation_id = payload.get("conversation_id")

    row = db.connect().execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if row is None:
        sched._finish(job["id"], "failed", error=f"asset {asset_id} vanished")
        return

    scope = {"conversation_id": conversation_id} if conversation_id else {"scope": "ambient"}
    bus.emit("job.started", {"job_id": job["id"], "kind": "asset.ingest",
                             "label": f"Reading {row['original_name']}"}, **scope)

    text, meta = _extract_text(Path(row["path"]), row["kind"])
    chunks = _chunk(text or "")

    with db.tx() as c:
        for ordinal, chunk in enumerate(chunks):
            c.execute(
                "INSERT INTO asset_chunks (id,asset_id,ordinal,text) VALUES (?,?,?,?)",
                (new_id("chunk"), asset_id, ordinal, chunk),
            )
        c.execute(
            "UPDATE assets SET status='ready', extracted_text=?, page_count=?, metadata=?, ingested_at=?"
            " WHERE id=?",
            (text, meta.get("page_count"), json.dumps(meta), now_ms(), asset_id),
        )

    # Index it into the knowledge graph, so the next turn reaches this document
    # through citations rather than by pasting it whole into the prompt. Done
    # here rather than on first use because the whole premise is that the graph
    # exists BEFORE the question — building it lazily would put a tree-sitter
    # parse on the latency path of the reply.
    #
    # Best effort, and deliberately quiet: an asset that fails to index is still
    # a perfectly good asset, and the context service falls back to its text.
    try:
        from ..knowledge import importer as knowledge_importer
        from ..knowledge import service as knowledge_service

        if text and knowledge_importer.available():
            knowledge_service.request_build(
                Path(row["path"]),
                scope=knowledge_service.scope_for_asset(asset_id),
                conversation_id=conversation_id,
                asset_id=asset_id,
            )
    except Exception as exc:  # pragma: no cover - never block ingestion
        print(f"assets: graph indexing skipped for {asset_id}: {exc}")

    # `ready` with no text is a real, useful state: the asset exists, its bytes
    # are stored, and the metadata says why there is no text yet.
    bus.emit("asset.ready", {
        "asset_id": asset_id, "kind": row["kind"], "name": row["original_name"],
        "chars": len(text or ""), "chunks": len(chunks),
        "ocr_required": bool(meta.get("ocr_required")),
    }, **scope)
    sched._finish(job["id"], "completed", result={"chars": len(text or ""), "chunks": len(chunks)})


def fail_asset(asset_id: str, reason: str, conversation_id: str | None = None) -> None:
    with db.tx() as c:
        c.execute("UPDATE assets SET status='failed', metadata=? WHERE id=?",
                  (json.dumps({"error": reason}), asset_id))
    scope = {"conversation_id": conversation_id} if conversation_id else {"scope": "ambient"}
    bus.emit("asset.failed", {"asset_id": asset_id, "reason": reason}, **scope)


# ── Reads ────────────────────────────────────────────────────────────────────
def get(asset_id: str) -> dict | None:
    row = db.connect().execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
    return d


def for_turn(turn_id: str) -> list[dict]:
    rows = db.connect().execute(
        "SELECT a.* FROM assets a JOIN turn_assets ta ON ta.asset_id = a.id"
        " WHERE ta.turn_id=? ORDER BY a.created_at",
        (turn_id,),
    )
    return [dict(r) for r in rows]


def pending_for_turn(turn_id: str) -> list[str]:
    """Assets a turn references that are not `ready` yet (§2.6).

    A turn must wait on these or fail explicitly. Proceeding with empty content
    is prohibited.
    """
    rows = db.connect().execute(
        "SELECT a.id FROM assets a JOIN turn_assets ta ON ta.asset_id = a.id"
        " WHERE ta.turn_id=? AND a.status != 'ready'",
        (turn_id,),
    )
    return [r["id"] for r in rows]


def list_assets(limit: int = 200) -> list[dict]:
    rows = db.connect().execute(
        "SELECT id,kind,source,original_name,bytes,status,created_at FROM assets"
        " ORDER BY created_at DESC LIMIT ?", (limit,),
    )
    return [dict(r) for r in rows]


def search(query: str, limit: int = 8) -> list[dict]:
    """Substring search over chunks.

    Deliberately not embeddings yet: the retrieval interface is what the rest
    of the system depends on, and it should not change when the ranking behind
    it is upgraded. `asset_embeddings` exists for that upgrade.
    """
    if not query.strip():
        return []
    rows = db.connect().execute(
        "SELECT c.asset_id, c.ordinal, c.text, a.original_name"
        "  FROM asset_chunks c JOIN assets a ON a.id = c.asset_id"
        " WHERE c.text LIKE ? AND a.status='ready'"
        " ORDER BY c.asset_id, c.ordinal LIMIT ?",
        (f"%{query.strip()}%", limit),
    )
    return [dict(r) for r in rows]


scheduler.register("asset.ingest", _run_ingest)
