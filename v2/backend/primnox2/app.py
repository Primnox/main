"""Gateway — transport only, no business logic (ARCH §4).

HTTP for commands, WebSocket for the event stream. The socket is the only way
events reach a client; no subsystem writes to it directly (CRS §12.5).

Every handler here is a thin call into a service. When a handler starts making
decisions, that decision belongs in a service instead — the shape of this file
is the guard against a second `core.py` growing in the transport layer.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from . import paths
from .assets import preview
from .assets import service as assets
from .chat import turns
from .kernel import scheduler
from .kernel.events import bus
from .knowledge import importer as knowledge_importer
from .knowledge import service as knowledge_service   # noqa: F401 — registers memory.graph_build
from .sandbox import manager as sandbox
from .sandbox import supervisor
from .kernel.trace import recorder
from .storage import db
from .tools import registry as tool_registry
from .tools import runtime as tools          # noqa: F401 — registers builtin tools
from .tools.permissions import broker
from .workspaces import service as workspaces

CRS_VERSION = "CRS/1.0"

APPDATA = Path(os.getenv("PRIMNOX2_HOME", Path.home() / "Documents" / "Primnox2"))
ALLOWED_ORIGINS = {
    "http://localhost:5273", "http://127.0.0.1:5273",
    "http://localhost:5173", "http://127.0.0.1:5173",
    "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
}

app = FastAPI(title="Primnox V2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    bus.bind_loop(_loop)

    paths.configure(APPDATA)
    db.configure(APPDATA / "primnox.db")
    db.init()

    swept = db.sweep_on_boot()
    swept["executions_failed"] = sandbox.sweep_on_boot()
    if any(swept.values()):
        print(f"[boot] swept interrupted work: {swept}")

    bus.subscribe(_push_to_clients)
    recorder.start()
    scheduler.scheduler.start()

    # Provisioning shells out to icacls across the interpreter tree and takes
    # over a minute on a cold machine. Warming it on a background thread keeps
    # startup instant while still having isolation ready before the first
    # execution asks for it.
    threading.Thread(target=_warm_sandbox, name="primnox2-sandbox-warm", daemon=True).start()

    print(f"[boot] Primnox V2 ({CRS_VERSION}) on 127.0.0.1:4109 · db={APPDATA / 'primnox.db'}")


def _warm_sandbox() -> None:
    backend = supervisor.available_backend()
    print(f"[boot] sandbox backend: {backend or 'NONE — execution will be refused'}")


def _push_to_clients(event: dict) -> None:
    """Bus subscriber. Runs on a worker thread, so it hops to the event loop.

    Delivery is best-effort by design (CRS §7.2): a dropped socket write is
    recoverable because the event is already durable, and the client will pull
    it on reconnect.
    """
    if _loop is None:
        return
    message = json.dumps(event)

    async def _send() -> None:
        for ws in list(_clients):
            try:
                await ws.send_text(message)
            except Exception:
                _clients.discard(ws)

    asyncio.run_coroutine_threadsafe(_send(), _loop)


# ── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # FastAPI's HTTP middleware does not run for websocket upgrades, so the
    # origin check has to be here. Without it any web page could open
    # ws://127.0.0.1:4109/ws and read the whole event stream.
    origin = ws.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await ws.close(code=1008)
        return

    await ws.accept()
    _clients.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") != "hello":
                continue

            # CRS §8.1 — the reconnect handshake.
            last_seen = int(msg.get("last_event_seen", 0))
            conversations = list(msg.get("conversations") or [])
            head = bus.head()

            if last_seen < bus.min_retained():
                # §8.3 — the cursor predates retention; a partial replay would
                # silently omit events, so demand a full resync instead.
                await ws.send_text(json.dumps({
                    "kind": "sync.required", "scope": "system",
                    "payload": {"reason": "retention", "head": head},
                }))
                continue

            for event in bus.replay(last_seen, conversations):
                await ws.send_text(json.dumps(event))

            # §8.1.2 — sent even when zero events were replayed. It is the
            # client's signal that it is live, and carries the cursor it should
            # adopt (§8.2.2).
            await ws.send_text(json.dumps({
                "kind": "sync.complete", "scope": "system",
                "payload": {"head": head, "crs": CRS_VERSION},
            }))
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict:
    from .models import gateway
    return {
        "ok": True, "crs": CRS_VERSION, "head": bus.head(),
        "model": gateway.describe_active(),
        "sandbox": supervisor.available_backend(),
        "tools": [s.name for s in tool_registry.all_specs()],
    }


# ── Conversations and turns ──────────────────────────────────────────────────
@app.get("/conversations")
async def list_conversations(archived: bool = False) -> dict:
    return {"conversations": turns.list_conversations(archived=archived),
            "folders": turns.list_folders()}


@app.post("/conversations")
async def create_conversation(request: Request) -> dict:
    body = await _json(request)
    return turns.create_conversation(
        title=body.get("title", "New Chat"),
        incognito=bool(body.get("incognito", False)),
    )


@app.patch("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: Request) -> dict:
    """Rename, pin, file or archive. One endpoint, because they are all the
    same operation on the same row and separate routes for each would be four
    ways to say `UPDATE conversations`."""
    body = await _json(request)
    result: dict = {"id": conversation_id}
    try:
        if "title" in body:
            result.update(turns.rename_conversation(conversation_id, body["title"]))
        if "pinned" in body:
            result.update(turns.set_pinned(conversation_id, bool(body["pinned"])))
        if "folder_id" in body:
            result.update(turns.move_conversation(conversation_id, body["folder_id"] or None))
        if "archived" in body:
            result.update(turns.archive_conversation(conversation_id, bool(body["archived"])))
    except KeyError:
        raise HTTPException(status_code=404, detail="no such conversation or folder")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict:
    """Permanent, and only when asked for permanently.

    Archiving is a PATCH — it hides a conversation and keeps it. This removes
    it, along with its turns, messages and events. Assets survive: a report
    should not vanish because the chat that produced it was tidied away.
    """
    try:
        return turns.delete_conversation(conversation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such conversation")


# ── Folders ──────────────────────────────────────────────────────────────────
@app.get("/folders")
async def list_folders() -> dict:
    return {"folders": turns.list_folders()}


@app.post("/folders")
async def create_folder(request: Request) -> dict:
    body = await _json(request)
    try:
        return turns.create_folder(body.get("name", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.patch("/folders/{folder_id}")
async def rename_folder(folder_id: str, request: Request) -> dict:
    body = await _json(request)
    try:
        return turns.rename_folder(folder_id, body.get("name", ""))
    except KeyError:
        raise HTTPException(status_code=404, detail="no such folder")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str) -> dict:
    """The folder goes; its conversations return to the top level."""
    try:
        return turns.delete_folder(folder_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such folder")


def _conversation_exists(conversation_id: str) -> bool:
    if turns.is_incognito(conversation_id):
        return True
    row = db.connect().execute("SELECT 1 FROM conversations WHERE id = ?",
                               (conversation_id,)).fetchone()
    return row is not None


@app.get("/conversations/{conversation_id}/history")
async def history(conversation_id: str) -> dict:
    # CRS §11.2.3 — an incognito conversation that the runtime no longer holds
    # is gone, and that has to be said. Returning an empty transcript would
    # render as a conversation the user simply had not spoken in yet, which is
    # the silent tolerance the section prohibits.
    if not _conversation_exists(conversation_id):
        return {"turns": [], "head": bus.head(), "gone": True}

    # CRS §3.3.3 — a state read, not a replay.
    rows = turns.get_history(conversation_id)
    # A turn parked in `awaiting_input` is blocked on a question the database
    # does not hold. The state read has to carry it, or reloading mid-prompt
    # leaves the turn waiting on something the user can no longer answer.
    for row in rows:
        if row["status"] == "awaiting_input":
            question = broker.pending_for_turn(row["turn_id"])
            if question:
                row["permission"] = question

        # The files a turn produced are durable state, not replay — they are
        # rows in `turn_assets`. Leaving them out meant reopening a
        # conversation lost every generated document: the chips vanished, and
        # with them the only route to the file. Tool rows and executions are
        # still event-derived and still disappear (audit gap 9); the files no
        # longer do, because they are the part with something behind them.
        files = assets.for_turn(row["turn_id"])
        if files:
            row["assets"] = [{"id": a["id"], "name": a["original_name"],
                              "kind": a["kind"]} for a in files]
    return {"turns": rows, "head": bus.head(),
            "incognito": turns.is_incognito(conversation_id)}


@app.post("/conversations/{conversation_id}/turns")
async def create_turn(conversation_id: str, request: Request) -> dict:
    body = await _json(request)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if not _conversation_exists(conversation_id):
        # Chiefly an incognito conversation the runtime has forgotten. Without
        # this the insert dies on a foreign key and the user gets a 500 for
        # something with a perfectly good explanation.
        raise HTTPException(
            status_code=404,
            detail="That conversation no longer exists. An incognito chat is "
                   "held in memory only, so restarting Primnox ends it.",
        )

    incognito = turns.is_incognito(conversation_id)
    if incognito and body.get("asset_ids"):
        raise HTTPException(
            status_code=400,
            detail="Attachments aren't available in an incognito chat: an "
                   "asset is stored on disk (CRS §11.2.4).",
        )

    # Returns before any model work starts (ARCH §4.1). The turn_id in this
    # response is what makes cancellation and attribution possible at all.
    turn = turns.create_turn(conversation_id, text)
    for asset_id in body.get("asset_ids") or []:
        assets.attach(turn["turn_id"], asset_id)

    scheduler.enqueue(turn["turn_id"], "chat.reply",
                      {"conversation_id": conversation_id, "text": text})
    return turn


@app.delete("/turns/{turn_id}")
async def cancel_turn(turn_id: str) -> dict:
    # CRS §9.1 — idempotent; cancelling an already-terminal turn succeeds.
    broker.cancel_for_turn(turn_id)
    return turns.cancel(turn_id)


@app.post("/turns/{turn_id}/retry")
async def retry_turn(turn_id: str) -> dict:
    """CRS §5.2.3 — retry makes a new turn, it never reopens the failed one."""
    try:
        turn = turns.retry_turn(turn_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # The new turn already knows both of these. Reading them back out of the
    # table instead meant retrying an incognito turn found no row, raised, and
    # left a turn queued that nothing would ever pick up.
    scheduler.enqueue(turn["turn_id"], "chat.reply",
                      {"conversation_id": turn["conversation_id"], "text": turn["text"]})
    return turn


@app.get("/turns/{turn_id}/executions")
async def turn_executions(turn_id: str) -> dict:
    return {"executions": sandbox.for_turn(turn_id)}


@app.get("/turns/{turn_id}/trace")
async def turn_trace(turn_id: str) -> dict:
    """The Replay Recorder's dump — what actually happened, in order.

    This is the answer to "my response duplicated": replay the turn instead of
    guessing at it.
    """
    trace = recorder.dump(turn_id)
    if trace is None:
        raise HTTPException(status_code=404,
                            detail="no trace for that turn (tracing is off by default)")
    return {**trace, "timeline": recorder.timeline(turn_id)}


@app.post("/turns/{turn_id}/trace")
async def watch_turn(turn_id: str) -> dict:
    recorder.watch(turn_id)
    return {"ok": True, "watching": turn_id}


# ── Assets ───────────────────────────────────────────────────────────────────
@app.post("/assets")
async def upload_asset(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    turn_id: str | None = Form(None),
) -> dict:
    """Hash and register, then return. Extraction is a job (ARCH §2.5).

    V1 parsed the file here, inside the request, on the event loop — which is
    why a large PDF froze the whole app.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if turns.is_incognito(conversation_id):
        # An asset is bytes on disk plus rows describing them. Accepting one
        # into an incognito conversation would persist the very thing the
        # conversation promises not to (§11.2.4).
        raise HTTPException(
            status_code=400,
            detail="Attachments aren't available in an incognito chat — an "
                   "uploaded file is stored on disk, and an incognito "
                   "conversation writes nothing.",
        )
    return assets.ingest_bytes(data, file.filename or "upload",
                               conversation_id=conversation_id, turn_id=turn_id)


@app.get("/assets")
async def list_assets() -> dict:
    return {"assets": assets.list_assets()}


@app.get("/assets/{asset_id}")
async def get_asset(asset_id: str) -> dict:
    asset = assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="no such asset")
    return asset


@app.get("/assets/{asset_id}/preview")
async def preview_asset(asset_id: str) -> dict:
    """A read-only description of an asset, shaped for display.

    Read-only in the strong sense: the preview layer has no write path at all,
    and the SQLite branch opens its file with `mode=ro` so that even looking at
    a database cannot leave a journal beside it.
    """
    asset = assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="no such asset")
    return preview.describe(asset)


@app.get("/assets/{asset_id}/download")
async def download_asset(asset_id: str, inline: bool = False):
    """Serve the bytes, so a generated file is one click away.

    Content is served from the content-addressed store under the *original*
    filename, so a download arrives as `report.pdf` rather than as its sha256.

    `inline=1` is what the built-in viewer uses. `filename=` sets
    `Content-Disposition: attachment`, and a browser given an attachment
    downloads it rather than rendering it — so an <iframe> pointed at the
    ordinary URL saves a PDF to disk instead of showing it.
    """
    from fastapi.responses import FileResponse

    asset = assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="no such asset")
    path = Path(asset["path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail="the stored file is gone")

    media_type = asset.get("mime") or "application/octet-stream"
    if inline:
        name = (asset["original_name"] or "file").replace('"', "")
        return FileResponse(path, media_type=media_type, headers={
            "Content-Disposition": f'inline; filename="{name}"'})
    return FileResponse(path, media_type=media_type,
                        filename=asset["original_name"])


# ── Workspaces ───────────────────────────────────────────────────────────────
@app.get("/workspaces")
async def list_workspaces() -> dict:
    return {"workspaces": workspaces.list_workspaces()}


@app.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str, version: int | None = None) -> dict:
    ws = workspaces.get(workspace_id, version)
    if ws is None:
        raise HTTPException(status_code=404, detail="no such workspace")
    return ws


@app.post("/workspaces/{workspace_id}/revert")
async def revert_workspace(workspace_id: str, request: Request) -> dict:
    body = await _json(request)
    try:
        return workspaces.revert(workspace_id, int(body.get("version", 1)),
                                 conversation_id=body.get("conversation_id"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/workspaces/{workspace_id}/diff")
async def diff_workspace(workspace_id: str, a: int, b: int) -> dict:
    return workspaces.diff(workspace_id, a, b)


# ── Permissions ──────────────────────────────────────────────────────────────
@app.post("/permissions/{request_id}")
async def resolve_permission(request_id: str, request: Request) -> dict:
    """The answer to a `permission.request`. The turn is parked in
    `awaiting_input` until this arrives (CRS §5.1)."""
    body = await _json(request)
    choice = body.get("choice", "deny")
    return {"ok": broker.resolve(request_id, choice), "choice": choice}


@app.get("/tools")
async def list_tools() -> dict:
    return {"tools": [
        {"name": s.name, "description": s.description, "danger": s.danger,
         "parameters": s.parameters,
         "manifest": s.manifest.to_dict() if s.manifest else None}
        for s in tool_registry.all_specs()
    ]}


# ── Knowledge graph ──────────────────────────────────────────────────────────
@app.get("/knowledge/scopes")
async def knowledge_scopes() -> dict:
    return {"scopes": knowledge_service.indexed_scopes()}


@app.post("/knowledge/index")
async def knowledge_index(request: Request) -> dict:
    """Queue an index build over a directory. Returns immediately with a job id.

    A 1M-line repository takes minutes to walk, so this cannot be synchronous —
    the point of the graph is that it is built before the question, not during
    it (CRS §2.2, ambient work).
    """
    body = await _json(request)
    target = (body.get("target") or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="target is required")
    path = Path(target).expanduser()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{path} does not exist")
    if not knowledge_importer.available():
        raise HTTPException(status_code=503,
                            detail="graphify is not installed (pip install graphifyy)")

    scope = (body.get("scope") or "").strip() or f"dir:{path.name}"
    job_id = knowledge_service.request_build(path, scope=scope)
    return {"job_id": job_id, "scope": scope, "target": str(path)}


@app.get("/knowledge/graph")
async def knowledge_graph(scope: str) -> dict:
    return knowledge_service.graph_json(scope)


@app.get("/knowledge/view", response_class=HTMLResponse)
async def knowledge_view(scope: str, limit: int | None = None) -> HTMLResponse:
    """Graphify's own viewer, rendered from our tables.

    Served as HTML rather than returned as data because the exporter produces a
    complete self-contained page — reimplementing it in the frontend would mean
    rebuilding community colouring and layout against a graph library we do not
    maintain, to land behind where upstream already is.
    """
    # `limit=0` means "all of it" — an explicit opt-in to the hairball, rather
    # than the default nobody chose.
    node_limit = knowledge_service.DEFAULT_NODE_LIMIT if limit is None else (limit or None)
    html = knowledge_service.render_html(scope, node_limit=node_limit)
    if html is None:
        raise HTTPException(status_code=404, detail=f"nothing indexed under {scope!r}")
    return HTMLResponse(html)


async def _json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}
