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
import re
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from . import paths
from .assets import preview
from .assets import service as assets
from .chat import turns
from .kernel import scheduler
from .kernel.events import bus
from .knowledge import facts
from .knowledge import flowchart
from .knowledge import importer as knowledge_importer
from .knowledge import service as knowledge_service   # noqa: F401 — registers memory.graph_build
from .memory import service as memory
from .settings import models as model_profiles
from .settings import service as settings_service
from .settings import tunables
from .sandbox import manager as sandbox
from .sandbox import supervisor
from .kernel.trace import recorder
from .storage import db, vault
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

# CSRF defense for every state-changing HTTP route. CORS above governs
# whether a browser lets a page READ a cross-origin response; it does
# nothing to stop the page from SENDING the request in the first place, so
# without this a page loaded from anywhere could POST /vault/setup or PATCH
# /settings against this loopback server with no interaction beyond loading
# it. /ws already checks Origin for exactly this reason (see its handler's
# comment) — this is the same check for the HTTP side, which had never had
# one.
#
# A real browser attaches Origin to every cross-origin request for these
# methods regardless of whether it needed a preflight, which is what makes
# checking it here sufficient — there is no user session here to bind a
# CSRF token to, only the app's own known set of front-end origins.
#
# Unlike /ws, a MISSING Origin is let through rather than refused. A
# websocket upgrade is always sent by a real browser with Origin attached, so
# its absence is itself suspicious; an ordinary HTTP request has legitimate
# origin-less callers this app must keep working — the test suite's
# TestClient, and any local curl/script a developer points at their own
# loopback port. Failing open on absence still blocks every real
# cross-origin browser attack, which is the actual threat this defends
# against.
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def _verify_origin(request: Request, call_next):
    if request.method in _UNSAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    return await call_next(request)


_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None
_push_sub_id: int | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    bus.bind_loop(_loop)

    paths.configure(APPDATA)

    # If the vault is LOCKED (.vault exists, no plaintext present), decrypt
    # primnox.db -> plaintext BEFORE storage.db ever opens it — the one point
    # in the process where unlocking is provably safe for CONNECTIONS: no
    # other thread exists yet to hold a stale one.
    #
    # That says nothing about the DATA, though, and gating on is_enabled()
    # (merely "does .vault exist") instead of is_locked() ("...AND no
    # plaintext present") conflated the two: a process killed hard (crash,
    # OOM, power loss) skips lock_vault() entirely, leaving a fully current
    # plaintext db + WAL on disk next to a .vault snapshot that only reflects
    # whatever the last CLEAN shutdown wrote. unlock_vault() decrypts that
    # stale snapshot and overwrites db_path unconditionally — on is_enabled()
    # that fires even though a newer plaintext already exists, silently
    # destroying every write made since the last clean lock. Gating on
    # is_locked() instead means "plaintext already on disk" is left alone —
    # strictly safer, since it's the most current copy either way.
    db_path = APPDATA / "primnox.db"
    if vault.is_locked(db_path):
        try:
            vault.unlock_vault(db_path)
            print("[boot] local vault unlocked")
        except PermissionError as exc:
            # No key in the keychain (e.g. a fresh machine) and no mnemonic
            # was supplied — surface this loudly rather than silently booting
            # against a stale or absent plaintext file.
            raise RuntimeError(
                f"Local vault is locked and could not be unlocked automatically: {exc}. "
                "Unlock it with the stored mnemonic before starting the server."
            ) from exc
    elif vault.is_enabled(db_path):
        print("[boot] local vault: plaintext already present (prior run did not "
              "shut down cleanly) — booting against it rather than the older .vault snapshot")

    db.configure(db_path)
    db.init()

    # Stored settings become environment variables here, immediately after the
    # database opens and before anything reads configuration. Later is too late:
    # `gateway.active_provider()` resolves from os.environ, so a setting applied
    # after the first turn would look like it had not saved.
    applied = settings_service.apply_to_environment()
    if applied:
        print(f"[boot] settings applied: {', '.join(applied)}")
    # After the flat settings, so an activated profile is what wins — it is the
    # more specific statement of intent, and it carries the key.
    active_profile = model_profiles.apply_active()
    if active_profile:
        print(f"[boot] model profile: {active_profile}")

    swept = db.sweep_on_boot()
    swept["executions_failed"] = sandbox.sweep_on_boot()
    if any(swept.values()):
        print(f"[boot] swept interrupted work: {swept}")

    global _push_sub_id
    _push_sub_id = bus.subscribe(_push_to_clients)
    recorder.start()
    scheduler.scheduler.start()

    # Provisioning shells out to icacls across the interpreter tree and takes
    # over a minute on a cold machine. Warming it on a background thread keeps
    # startup instant while still having isolation ready before the first
    # execution asks for it.
    _spawn_sandbox_warm_once()

    # Same treatment, for the same reason: spawning the gateway and waiting for
    # it to answer takes seconds, and none of that belongs on the event loop.
    _spawn_omniroute_once()

    print(f"[boot] Primnox V2 ({CRS_VERSION}) on 127.0.0.1:4109 · db={APPDATA / 'primnox.db'}")


@app.on_event("shutdown")
async def _shutdown() -> None:
    """The mirror image of the vault-unlock in _startup(): re-encrypt
    primnox.db and remove the plaintext, but only once nothing else can be
    mid-write to it.

    stop() alone is not that guarantee — it only stops workers from claiming
    NEW jobs. join() waits (up to 10s) for whatever a worker already claimed
    to actually finish, which is what vault.lock_vault()'s "nothing else can
    be mid-write" requires. A job that is still running after 10s (a long
    model call, most likely) means lock is skipped rather than risking a
    torn write mid-encrypt — the plaintext is left as-is, exactly V1's own
    documented fallback for a shutdown it cannot cleanly complete.
    """
    global _loop, _push_sub_id
    scheduler.scheduler.stop()
    clean = scheduler.scheduler.join(timeout=10.0)

    # Release every Computer Use grant before anything else unwinds. Authority
    # over the user's own applications is a live thing, not stored state: a
    # session that outlives the process that was exercising it is a window
    # somebody approved for an agent that no longer exists. Done after join()
    # so a worker mid-click finishes rather than losing its grant underneath
    # it, and guarded because Computer Use may not have loaded at all.
    if tools.COMPUTER_USE:
        from .computer import pointer as computer_pointer
        from .computer import session as computer_sessions
        computer_sessions.close_all("shutdown")
        # And take the overlay's window and thread down with them. Closing the
        # sessions only hides it: the thread is a daemon and would go on the
        # way daemons do, but this process has a lifespan that runs more than
        # once — every `with TestClient(app):` is another cycle — and a
        # top-most window belonging to a shut-down subsystem is not something
        # to leave lying on somebody's desktop between them.
        computer_pointer.shutdown()

    # Undo the startup subscription and drop the loop reference regardless of
    # whether the vault lock below runs — otherwise every new lifespan cycle
    # (each `with TestClient(app):`, and any future production restart path)
    # piles another subscriber onto the shared, module-level bus, and events
    # emitted after this loop closes hand `_push_to_clients` a dead loop:
    # `asyncio.run_coroutine_threadsafe` on a closed loop raises before the
    # coroutine it built is ever scheduled, which is swallowed by
    # `_fanout`'s per-subscriber catch and shows up only as a stray
    # "coroutine was never awaited" warning with no test failure to point at.
    if _push_sub_id is not None:
        bus.unsubscribe(_push_sub_id)
        _push_sub_id = None
    _loop = None
    _clients.clear()

    if not clean:
        print("[shutdown] a worker was still running after 10s — leaving the vault unlocked")
        return

    db_path = APPDATA / "primnox.db"
    if vault.is_enabled(db_path):
        # Windows refuses to delete a file that's still open anywhere in this
        # process, even by the SAME thread — found by actually exercising
        # this path: an async request handler (this one included; FastAPI
        # runs `async def` routes on the event-loop thread, not a pool) opens
        # its own thread-local connection via storage.db.connect(), and
        # _secure_delete()'s unlink() raised WinError 32 against it. Calling
        # configure() again on the SAME path is db.py's own documented way to
        # drop the CALLING thread's cached connection; join() above already
        # got the worker threads' connections out of the way.
        db.configure(db_path)
        vault.lock_vault(db_path)
        print("[shutdown] local vault locked")


_sandbox_warm_started = False
_sandbox_warm_lock = threading.Lock()


def _spawn_sandbox_warm_once() -> None:
    """`_startup()` can legitimately run more than once per process — every
    `with TestClient(app):` triggers a real ASGI startup/shutdown cycle, and
    production itself could add a restart path later. `appcontainer.provision()`
    caches its result in a marker FILE, which is correct across separate
    process launches but does nothing to stop two THREADS in the SAME process
    from both reading "not yet provisioned" and both starting their own
    machine-global `icacls /T` walk over the whole Python venv at once.

    Found by actually running many `_startup()` cycles back to back (13 in a
    row, from a CSRF test opening that many `TestClient`s): multiple
    `primnox2-sandbox-warm` threads piled up, all genuinely stuck inside the
    SAME expensive icacls call simultaneously, each fighting the others for
    disk I/O over the identical multi-thousand-file tree — turning an
    "instant startup, ~80s the first time" cost into "however many overlapping
    startups happened, each taking LONGER than 80s from the contention." A
    module-level flag guarded by a lock is enough: warming is a one-shot
    per-process concern, not a per-lifespan-cycle one.
    """
    global _sandbox_warm_started
    with _sandbox_warm_lock:
        if _sandbox_warm_started:
            return
        _sandbox_warm_started = True
    threading.Thread(target=_warm_sandbox, name="primnox2-sandbox-warm", daemon=True).start()


def _warm_sandbox() -> None:
    backend = supervisor.available_backend()
    print(f"[boot] sandbox backend: {backend or 'NONE — execution will be refused'}")


_omniroute_started = False
_omniroute_lock = threading.Lock()


def _spawn_omniroute_once() -> None:
    """Bring the gateway up with the app, once per process.

    Guarded exactly like the sandbox warm above, and for the same measured
    reason: `_startup()` runs again for every `TestClient(app)`, and two
    threads both finding "not running" would race to spawn two gateways
    fighting for port 20128.
    """
    global _omniroute_started
    if settings_service.get("provider.omniroute_autostart", "on") != "on":
        return
    with _omniroute_lock:
        if _omniroute_started:
            return
        _omniroute_started = True
    threading.Thread(target=_start_omniroute, name="primnox2-omniroute", daemon=True).start()


def _start_omniroute() -> None:
    try:
        result = model_profiles.ensure_omniroute_running()
    except Exception as exc:                                  # pragma: no cover
        # Never fatal. No gateway means cloud turns fail with their own error;
        # a traceback here would take the whole app down over an optional
        # convenience.
        print(f"[boot] omniroute: autostart failed — {exc}")
        return
    if result.get("started"):
        print(f"[boot] omniroute: started pid={result.get('pid')} — {result.get('reason')}")
    else:
        print(f"[boot] omniroute: {result.get('reason')}")


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
    #
    # A MISSING origin is rejected, not waved through. The check used to read
    # `if origin is not None and origin not in ALLOWED_ORIGINS`, which refused a
    # wrong origin and accepted no origin at all — measured: `Origin:
    # https://evil.example` got 403 while omitting the header entirely got 101
    # and the full live stream. Every legitimate client sends one (a browser
    # always does; Tauri sends tauri://localhost), so the header's absence means
    # the caller is not one of them. Trusting the anonymous case more than the
    # named one is backwards.
    origin = ws.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
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

        # Documents the turn authored, for exactly the reason the files above
        # are carried: `turn_workspaces` is durable state, and leaving it out
        # of the state read meant a reopened conversation lost every document
        # the model wrote. `workspaces.for_turn()` already existed and nothing
        # called it, so the canvas simply vanished on reload while the rows
        # sat in the database the whole time.
        docs = workspaces.for_turn(row["turn_id"])
        if docs:
            row["workspaces"] = [{"id": w["id"], "title": w["title"],
                                  "kind": w["kind"], "version": w["current_version"]}
                                 for w in docs]
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


@app.get("/assets/{asset_id}/slide-image/{ref}")
async def slide_image(asset_id: str, ref: int):
    """One picture out of a deck, by the index its preview handed out.

    Separate from the preview rather than inlined as a data URI: a deck of
    photographs would make the describe call tens of megabytes, and the viewer
    only ever needs the pictures on the slide it is showing. Cached hard — the
    bytes are addressed by the asset's own content hash and the shape index, so
    they cannot change under the same URL.
    """
    from fastapi.responses import Response

    asset = assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="no such asset")
    path = Path(asset["path"])
    if not path.is_file():
        raise HTTPException(status_code=410, detail="the stored file is gone")

    found = preview.slide_image(path, ref)
    if found is None:
        raise HTTPException(status_code=404, detail="no such image in this deck")
    blob, content_type = found
    return Response(content=blob, media_type=content_type,
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


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
        # original_name is whatever the uploaded file was called — fully
        # attacker-controlled. Stripping `"` alone isn't enough: a filename
        # with an embedded CR/LF reaches uvicorn's header serializer raw
        # (Starlette's own `filename=` param below takes the non-inline
        # path, which percent-encodes via urllib.parse.quote() and is
        # already safe — this manual header is the one path that wasn't).
        # uvicorn does reject a raw CRLF in a header value outright rather
        # than emit it (confirmed directly: `RuntimeError: Invalid HTTP
        # header value`), so this was never an actual response-splitting
        # exploit — but it was an unhandled crash on that one request for
        # any file uploaded with such a name. Stripping C0 controls and DEL
        # turns that into "renders with a slightly mangled name" instead.
        name = re.sub(r'[\x00-\x1f\x7f]', "", (asset["original_name"] or "file")).replace('"', "")
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


@app.get("/assets/{asset_id}/versions")
async def asset_versions(asset_id: str) -> dict:
    """Version history for a generated asset.

    Empty for anything never regenerated, which is most files. `retention` is
    reported alongside so the client can say whether an old version is
    restorable rather than offering a Revert that may not work.
    """
    from .assets import versions as asset_versions_service
    if assets.get(asset_id) is None:
        raise HTTPException(status_code=404, detail="no such asset")
    return {"versions": asset_versions_service.versions(asset_id),
            "head": asset_versions_service.head(asset_id),
            "retention": asset_versions_service.retention()}


@app.post("/assets/{asset_id}/revert")
async def revert_asset(asset_id: str, request: Request) -> dict:
    """Restore an earlier version by appending it as a new one."""
    from .assets import versions as asset_versions_service
    body = await _json(request)
    try:
        version = int(body.get("version"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="version must be an integer")
    try:
        return asset_versions_service.revert(asset_id, version,
                                             turn_id=body.get("turn_id"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Tasks ────────────────────────────────────────────────────────────────────
# v2.task_state has been built, tested and feeding the model's context through
# v2/context.py since it landed, and no route ever exposed it — so a user could
# not see the work the assistant believed it was in the middle of. These read it
# out. They add no capability the module does not already have: notably there is
# no pause, because `blocked` there means work stopped for a reason outside the
# task rather than because somebody asked it to wait, and `resume()` answers
# "what was I doing" rather than unpausing anything.
#
# Imported inside each handler, matching kernel/scheduler.py and tools/builtins.py:
# v2 is a sibling package rather than a subpackage, and importing it at module
# scope pulls the whole substrate in on app import.


@app.get("/tasks")
async def list_tasks(project: str | None = None, session: str | None = None,
                     limit: int = 20) -> dict:
    """Unfinished tasks, most recently touched first."""
    from v2 import task_state
    return {"tasks": task_state.open_tasks(project=project, session=session,
                                           limit=max(1, min(limit, 100)))}


@app.get("/tasks/resume")
async def resume_task(project: str | None = None, session: str | None = None) -> dict:
    """The one task "continue what I was doing" resolves to, or none.

    Declared before /tasks/{task_id} on purpose — FastAPI matches in order, and
    the other way round "resume" is read as a task id and 404s.
    """
    from v2 import task_state
    return {"task": task_state.resume(project=project, session=session)}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    from v2 import task_state
    task = task_state.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return task


@app.post("/tasks/{task_id}/retarget")
async def retarget_task(task_id: str, request: Request) -> dict:
    """Change what the task is for. Findings survive; the pending plan does not."""
    from v2 import task_state
    body = await _json(request)
    goal = body.get("goal")
    if goal is not None and not str(goal).strip():
        raise HTTPException(status_code=400, detail="goal cannot be empty")
    constraints = body.get("constraints")
    if constraints is not None and not isinstance(constraints, list):
        raise HTTPException(status_code=400, detail="constraints must be a list")
    task = task_state.retarget(task_id, goal=goal, constraints=constraints,
                               drop_pending=bool(body.get("drop_pending", True)))
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return task


@app.post("/tasks/{task_id}/finish")
async def finish_task(task_id: str, request: Request) -> dict:
    """Close a task. Omit `status` to let it be derived from what actually ran —
    task_state refuses an explicit "completed" while work is still unresolved,
    and that refusal surfaces here as a 400 rather than being swallowed."""
    from v2 import task_state
    from v2.task_state import ValidationError
    body = await _json(request)
    try:
        task = task_state.finish(task_id, body.get("status"),
                                 outcome=body.get("outcome"))
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return task


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


# ── Model profiles ───────────────────────────────────────────────────────────
@app.get("/models")
async def list_model_profiles() -> dict:
    return model_profiles.describe()


@app.post("/models")
async def save_model_profile(request: Request) -> dict:
    body = await _json(request)
    try:
        model_profiles.save(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if body.get("activate"):
        model_profiles.activate(body["name"])
    return model_profiles.describe()


@app.post("/models/{name}/model")
async def choose_model(name: str, request: Request) -> dict:
    body = await _json(request)
    model = (body.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="model is required")
    try:
        model_profiles.use_model(name, model)
    except KeyError:
        raise HTTPException(status_code=404, detail=name)
    return model_profiles.describe()


@app.post("/models/{name}/discover")
async def discover_models(name: str) -> dict:
    """Ask the provider what it offers. Ollama natively, everyone else through
    the OpenAI-compatible /v1/models."""
    try:
        found = model_profiles.discover(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=name)
    return {"found": found, **model_profiles.describe()}


@app.post("/models/{name}/activate")
async def activate_model_profile(name: str) -> dict:
    try:
        model_profiles.activate(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=name)
    return model_profiles.describe()


@app.delete("/models/{name}")
async def delete_model_profile(name: str) -> dict:
    if not model_profiles.delete(name):
        raise HTTPException(status_code=404, detail=name)
    return model_profiles.describe()


# ── Does it actually work? ───────────────────────────────────────────────────
@app.post("/models/{name}/test")
async def test_model_profile(name: str) -> dict:
    """Probe a saved profile with its stored key.

    A pass means reachable and authenticated, not "chat works" — some endpoints
    serve /models to anyone and reject completions without a plan. The wording
    in the UI is held to that distinction.
    """
    from .settings import connections

    try:
        return connections.test_profile(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=name)


@app.post("/models/test")
async def test_model_candidate(request: Request) -> dict:
    """Try an endpoint and key BEFORE committing them to a profile.

    Records no health: a typo in an add form should not leave a circuit behind
    it for a provider the user never actually adopted.
    """
    from .settings import connections

    body = await _json(request)
    return connections.test_candidate(
        str(body.get("base_url") or ""), str(body.get("api_key") or ""))


@app.post("/models/test-all")
async def test_all_model_profiles() -> dict:
    from .settings import connections

    return {"results": connections.test_all()}


@app.post("/models/discover-all")
async def discover_all_models() -> dict:
    """Refresh every saved profile's model list in one pass."""
    return {"found": model_profiles.discover_all(), **model_profiles.describe()}


# ── Portability ──────────────────────────────────────────────────────────────
@app.get("/models/export")
async def export_model_profiles() -> dict:
    """Profiles as portable JSON, deliberately WITHOUT keys — an export is a
    file that gets mailed, committed by accident, or attached to a bug report."""
    return model_profiles.export_profiles()


@app.post("/models/import")
async def import_model_profiles(request: Request) -> dict:
    body = await _json(request)
    try:
        result = model_profiles.import_profiles(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**result, **model_profiles.describe()}


# ── The user's own annotations ───────────────────────────────────────────────
@app.post("/models/{name}/favourite")
async def favourite_model_profile(name: str, request: Request) -> dict:
    body = await _json(request)
    return {"favourites": model_profiles.set_favourite(name, bool(body.get("pinned", True)))}


@app.post("/models/{name}/note")
async def note_model_profile(name: str, request: Request) -> dict:
    """A line of the user's own — which account it bills to, why it was added.
    The catalogue's `hint` is the vendor's words; this is theirs."""
    body = await _json(request)
    return {"notes": model_profiles.set_note(name, str(body.get("note") or ""))}


@app.get("/models/health")
async def model_health() -> dict:
    """What routing currently believes about every endpoint it has called.

    The first thing to look at when a turn went somewhere unexpected: which
    circuits are open, how long until they probe again, and the score each
    candidate would be ranked by right now. `chain` is the order this instant —
    the active provider first, then the fallbacks best-first.
    """
    from .models import health as model_health_state
    from .models import routing as model_routing

    chain = []
    try:
        for candidate in model_routing.chain():
            explanation = model_routing.score(candidate)
            chain.append({**explanation.as_dict(), "origin": candidate.origin,
                          "local": candidate.is_local})
    except Exception as exc:                                  # noqa: BLE001
        # A broken chain must not break the page that exists to diagnose it.
        chain = [{"error": f"{type(exc).__name__}: {exc}"}]

    return {"circuits": model_health_state.snapshot(), "chain": chain,
            "attempts_allowed": tunables.get("models.failover_attempts")}


@app.get("/models/telemetry")
async def model_telemetry() -> dict:
    """The header of Mission Control. Measured values only — see the module
    docstring for what is deliberately absent and why."""
    from .settings import telemetry

    return telemetry.snapshot()


@app.get("/models/capabilities")
async def model_capabilities() -> dict:
    """What each configured provider can actually do, side by side.

    Read from the capability registry the gateway already consults when it
    decides whether to send a `tools` array — not from a benchmark, because
    Primnox has never run one. Context window, tool calling and vision are
    facts about a model. "Which is better at coding" is a rating, Primnox has
    no data for it, and a five-star column invented to fill a table is a
    published benchmark whether or not it is labelled as one.
    """
    from .models import gateway
    from .models import health as circuits

    rows = []
    for profile in model_profiles.profiles():
        base = (profile.get("base_url") or "").rstrip("/")
        model = profile.get("model") or ""
        caps = gateway.capabilities_for(base, model)
        circuit = circuits.circuit(f"{base}|{model}")
        rows.append({
            "name": profile["name"],
            "model": model,
            "local": gateway.on_device_for(profile.get("kind", ""), base),
            "tool_calling": caps.tool_calling,
            "vision": caps.vision,
            "json_mode": caps.json_mode,
            "streaming": caps.streaming,
            "context_window": caps.context_window,
            "max_output": caps.max_output,
            "parallel_tool_calls": caps.parallel_tool_calls,
            # Measured, unlike the rest of this row, and null until it has run.
            "latency_ms": circuit.latency_ms,
            "calls": circuit.calls,
        })
    return {"providers": rows}


@app.get("/models/omniroute")
async def omniroute_status() -> dict:
    """Is the gateway up, and what is behind it?

    Its own route rather than a field on /models because the probe is a network
    call, and the settings screen must still render when the answer is "not
    installed" — which on a fresh machine is the normal answer, not an error.
    """
    return model_profiles.omniroute_status()


@app.post("/models/health/reset")
async def reset_model_health(request: Request) -> dict:
    """Forget what routing believes — for someone who has just fixed the thing
    a breaker is waiting out and does not want to wait for the cooldown."""
    body = await _json(request)
    key = (body.get("key") or "").strip() or None
    from .models import health as model_health_state
    cleared = model_health_state.reset(key)
    return {"cleared": cleared, "circuits": model_health_state.snapshot()}


# ── Guides ───────────────────────────────────────────────────────────────────
@app.get("/guides")
async def list_guides() -> dict:
    """Titles and summaries, without the bodies — the index is a menu."""
    from . import guides

    return {"guides": guides.index()}


@app.get("/guides/{slug}")
async def read_guide(slug: str) -> dict:
    from . import guides

    guide = guides.get(slug)
    if guide is None:
        raise HTTPException(status_code=404, detail=slug)
    return guide


# ── Tunables ─────────────────────────────────────────────────────────────────
@app.get("/tunables")
async def read_tunables() -> dict:
    # Each row carries its provenance — environment, saved, or default — because
    # "why is this 40" is the only question anyone asks of a settings screen.
    return {"tunables": tunables.describe()}


@app.patch("/tunables")
async def write_tunables(request: Request) -> dict:
    body = await _json(request)
    result = tunables.set_many(body.get("tunables") or {})
    return {**result, "tunables": tunables.describe()}


@app.post("/tunables/reset")
async def reset_tunables(request: Request) -> dict:
    body = await _json(request)
    return {"reset": tunables.reset(body.get("key")), "tunables": tunables.describe()}


# ── Settings ─────────────────────────────────────────────────────────────────
@app.get("/settings")
async def read_settings() -> dict:
    # Never returns the API key — only whether one is present. A settings screen
    # that displays your own key displays it to whoever is behind you.
    return settings_service.describe()


@app.patch("/settings")
async def write_settings(request: Request) -> dict:
    body = await _json(request)
    result = settings_service.set_many(body.get("settings") or {})
    if body.get("api_key") is not None:
        settings_service.set_api_key(body["api_key"])
        result["api_key_present"] = settings_service.has_api_key()
    return {**result, **settings_service.describe()}


# ── Vault ────────────────────────────────────────────────────────────────────
# Setup and disable both operate on a snapshot copy (setup_vault/disable_vault
# never touch the live plaintext — see storage/vault.py's module docstring),
# so unlike lock/unlock these are safe to call from a request handler while
# the app is running.
@app.get("/vault")
async def vault_status() -> dict:
    db_path = APPDATA / "primnox.db"
    return {
        "enabled": vault.is_enabled(db_path),
        "locked": vault.is_locked(db_path),
    }


@app.post("/vault/setup")
async def vault_setup(request: Request) -> dict:
    db_path = APPDATA / "primnox.db"
    if vault.is_enabled(db_path):
        raise HTTPException(status_code=409, detail="Vault is already enabled")
    body = await _json(request)
    mnemonic = (body.get("mnemonic") or "").strip() or None
    try:
        phrase = vault.setup_vault(db_path, mnemonic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Returned once. The caller MUST show this to the user now — neither the
    # keychain entry nor primnox.db itself can reproduce it afterwards.
    return {"mnemonic": phrase}


@app.post("/vault/disable")
async def vault_disable() -> dict:
    db_path = APPDATA / "primnox.db"
    if not vault.is_enabled(db_path):
        raise HTTPException(status_code=409, detail="Vault is not enabled")
    try:
        vault.disable_vault(db_path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"enabled": False}


# ── Memory ───────────────────────────────────────────────────────────────────
@app.get("/memories")
async def list_memories(category: str | None = None, q: str | None = None) -> dict:
    rows = memory.search(q) if q else memory.live(category)
    return {"memories": rows, "stats": memory.stats(),
            "categories": list(memory.CATEGORIES)}


@app.post("/memories")
async def create_memory(request: Request) -> dict:
    body = await _json(request)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    return memory.remember(
        text,
        category=body.get("category") or memory.DEFAULT_CATEGORY,
        provenance=memory.EXPLICIT,
    )


@app.patch("/memories/{memory_id}")
async def edit_memory(memory_id: str, request: Request) -> dict:
    body = await _json(request)
    if body.get("restore"):
        if not memory.restore(memory_id):
            raise HTTPException(status_code=404, detail=memory_id)
        return {"id": memory_id, "restored": True}
    if not memory.update(memory_id, body.get("text") or ""):
        raise HTTPException(status_code=404, detail=memory_id)
    return {"id": memory_id, "updated": True}


@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str) -> dict:
    # Soft delete: `forget` sets deleted_at rather than removing the row, so a
    # later import cannot resurrect something the user chose to forget.
    if not memory.forget(memory_id):
        raise HTTPException(status_code=404, detail=memory_id)
    return {"id": memory_id, "forgotten": True}


@app.delete("/memories")
async def delete_all_memories() -> dict:
    return {"forgotten": memory.forget_all()}


# ── Knowledge graph ──────────────────────────────────────────────────────────
@app.get("/knowledge/scopes")
async def knowledge_scopes() -> dict:
    """What can be viewed, with the user's own knowledge FIRST.

    Ordering is the product decision here. An indexed repository is a
    developer's view of a codebase, and opening a feature called "what Primnox
    knows" on `_startup()` calling `_warm_sandbox()` describes the application
    rather than the person using it. Corpora are labelled `Indexed:` so a node
    count against one can never read as knowledge about the user.
    """
    facts_stats = facts.stats()
    scopes = [{"scope": facts.SCOPE, "label": "What Primnox knows about you",
               "nodes": facts_stats["nodes"], "kind": "facts",
               "by_kind": facts_stats["by_kind"], "updated_at": None}]

    # Every conversation scope was labelled "This conversation", so a picker
    # holding five of them offered the same words five times and the only way to
    # tell them apart was the node count. That phrase is right when the graph is
    # opened FROM a conversation — there it really is *this* one — and useless in
    # a list of all of them. Named after the conversation instead.
    titles = {c["id"]: c["title"] for c in turns.list_conversations(limit=1000)}

    for row in knowledge_service.indexed_scopes():
        scope = row["scope"]
        if scope.startswith("conv:"):
            title = titles.get(scope[5:])
            label = title or "A conversation"
            kind = "conversation"
        else:
            label = f"Indexed: {scope}"
            kind = "corpus"
        scopes.append({**row, "kind": kind, "label": label})
    return {"scopes": scopes}


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


@app.post("/knowledge/flowchart", response_class=HTMLResponse)
async def flowchart_view(request: Request) -> HTMLResponse:
    """Render a mermaid flowchart through Graphify's viewer.

    POST rather than GET: a diagram is a body, and putting one in a query
    string would break on the first newline.
    """
    body = await _json(request)
    source = body.get("source") or ""
    html = flowchart.render_html(source)
    if html is None:
        raise HTTPException(status_code=422,
                            detail="not a flowchart this renderer understands")
    return HTMLResponse(html)


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
    # -1 defers to the tunable; an explicit limit=0 means everything.
    node_limit = -1 if limit is None else (limit or None)

    # The user's own knowledge is derived on read rather than stored, so it does
    # not go through the scope table.
    if scope == facts.SCOPE:
        if node_limit == -1:
            node_limit = tunables.get("knowledge.view_node_limit") or None
        html = facts.render_html(node_limit)
        if html is None:
            raise HTTPException(
                status_code=404,
                detail="nothing saved yet — memories, decisions and documents "
                       "appear here as you use Primnox")
        return HTMLResponse(html)

    html = knowledge_service.render_html(scope, node_limit=node_limit)
    if html is None:
        raise HTTPException(status_code=404, detail=f"nothing indexed under {scope!r}")
    return HTMLResponse(html)


async def _json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}
