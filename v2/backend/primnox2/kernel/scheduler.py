"""Job queue and workers — CRS/1.0 §6, §9.

Replaces V1's single mutex held across the entire pipeline (core.py:332), which
is why Enter-spam there bought ~11 seconds per queued message with no way out.

Here the conversation write lock covers only history mutation; streaming, tools
and assets run unlocked, and a bounded pool stops five queued turns becoming
five concurrent model streams.
"""
from __future__ import annotations

import json
import queue
import threading
import time
import traceback

from ..chat import ephemeral, turns
from ..ids import JOB, new_id
from ..models import gateway
from ..skills import loader as skills
from ..storage import db
from .events import bus

now_ms = lambda: int(time.time() * 1000)

# Streaming batches tokens the way V1 did — every 100ms or 5 tokens — because
# one event per token would put thousands of rows in the log for one reply.
FLUSH_INTERVAL_S = 0.1
FLUSH_TOKENS = 5

# How long a turn waits for an attached document to finish ingesting before it
# gives up and says so. Long enough for a large PDF, short enough that a stuck
# ingestion does not hold a conversation open indefinitely.
ASSET_WAIT_S = 120


def enqueue(turn_id: str | None, kind: str, payload: dict, *, idempotent: bool = False,
            cancellable: bool = True, priority: int = 0, max_attempts: int = 1) -> str:
    # Self-healing rather than trusting some earlier call to have guaranteed
    # workers are alive. They usually are, but app.py's shutdown hook makes
    # `with TestClient(app):` a REAL stop() of this same process-global
    # scheduler on __exit__ (added for vault locking) — something it never
    # used to do. Any caller enqueueing after an unrelated test file's
    # TestClient closes (an HTTP test, an asset ingest not routed through a
    # chat turn — anything) hits an empty worker pool with nothing left to
    # restart it, and the job just written sits in "queued" for the full
    # wait timeout with no worker ever alive to claim it. Cheap to check, and
    # start() is a no-op-shaped generation swap when workers are already
    # running, so this costs nothing on the common path where nothing
    # upstream touched it.
    if not any(t.is_alive() for t in scheduler._threads):
        scheduler.start()

    jid = new_id(JOB)

    # A job row stores its payload as a column, and for `chat.reply` that
    # payload *is* the user's message. So an incognito turn cannot use the
    # table even setting the foreign key aside: queueing the work would write
    # the very text incognito exists to keep off the disk (§11.2.1).
    if ephemeral.has_turn(turn_id):
        ephemeral.enqueue_job({
            "id": jid, "turn_id": turn_id, "kind": kind, "status": "queued",
            "idempotent": int(idempotent), "cancellable": int(cancellable),
            "priority": priority, "payload": json.dumps(payload),
            "max_attempts": max_attempts, "attempts": 0,
            "cancel_requested": False, "created_at": now_ms(),
        })
        _wake.set()
        return jid

    with db.tx() as c:
        c.execute(
            "INSERT INTO jobs (id,turn_id,kind,status,idempotent,cancellable,priority,"
            "                  payload,max_attempts,created_at)"
            " VALUES (?,?,?, 'queued', ?,?,?,?,?,?)",
            (jid, turn_id, kind, int(idempotent), int(cancellable), priority,
             json.dumps(payload), max_attempts, now_ms()),
        )
    _wake.set()
    return jid


class Scheduler:
    def __init__(self, workers: int = 3) -> None:
        self.workers = workers
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

    def start(self) -> None:
        # A FRESH Event every generation, never a clear()d one — this is what
        # makes restart safe rather than merely possible. A cleared-and-reused
        # Event is racy: `stop()` sets it to kill generation N, but a
        # generation-N worker only checks it between jobs (up to a 0.5s poll
        # wait), and if `start()` calls clear() before that worker wakes up
        # and notices, the flag it eventually checks now reads "not stopped"
        # — that worker never exits, and keeps calling _claim() forever as an
        # untracked extra thread. Each thread is handed its OWN generation's
        # Event as an argument, not a live reference to `self._stop` — so a
        # later generation replacing `self._stop` cannot retroactively
        # un-stop it.
        #
        # But that swap has its own failure mode if nothing signals the
        # OUTGOING generation first: whoever called start() without calling
        # stop() on the previous one (conftest.py's session fixture does
        # exactly this — it starts the scheduler directly, once, and a test
        # that separately opens `TestClient(app)` triggers app.py's lifespan
        # hooks calling start() AGAIN on the same singleton) leaves that
        # earlier generation's threads holding a flag object `self._stop` no
        # longer points to. No future stop() can ever reach them — not a
        # race, a guaranteed leak, reproduced directly by starting a
        # scheduler, then cycling TestClient a few times, and dumping every
        # live thread's stack: the original three sit in `_wake.wait()`
        # forever. Signalling the CURRENT `self._stop` here, before it gets
        # replaced, is what stop() would have done for them if anyone had
        # called it — this makes start() implicitly "stop whatever generation
        # is running, then start the next one" rather than "start another
        # generation alongside whatever is already there."
        self._stop.set()
        _wake.set()

        stop_flag = threading.Event()
        self._stop = stop_flag
        self._threads = [t for t in self._threads if t.is_alive()]
        for i in range(self.workers):
            t = threading.Thread(target=self._loop, args=(stop_flag,),
                                 name=f"primnox2-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        _wake.set()

    def join(self, timeout: float | None = None) -> bool:
        """Block until every worker thread has actually exited (not merely
        been told to). `stop()` only sets a flag a worker checks between
        jobs — a worker mid-`_run()` keeps its DB connection open until that
        job finishes, and anything that needs no other thread holding one
        (vault.lock_vault(), a schema migration) needs this, not stop() alone.

        Returns False if `timeout` elapsed with a thread still alive, so a
        caller with a hard deadline (e.g. shutdown) can decide whether to
        proceed anyway rather than hang forever on a stuck job.
        """
        deadline = None if timeout is None else time.time() + timeout
        clean = True
        for t in self._threads:
            remaining = None if deadline is None else max(0.0, deadline - time.time())
            t.join(timeout=remaining)
            if t.is_alive():
                clean = False
        return clean

    def _claim(self) -> dict | None:
        """Atomically take one queued job. Two workers must never claim the same
        row, so the SELECT and the UPDATE are one transaction."""
        # In-memory work first — it is always interactive, and there is never
        # much of it.
        job = ephemeral.claim_job()
        if job is not None:
            return job

        with db.tx() as c:
            row = c.execute(
                "SELECT * FROM jobs WHERE status='queued'"
                " ORDER BY priority DESC, created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            c.execute(
                "UPDATE jobs SET status='running', started_at=?, attempts=attempts+1 WHERE id=?",
                (now_ms(), row["id"]),
            )
            return dict(row)

    def _loop(self, stop_flag: threading.Event) -> None:
        try:
            while not stop_flag.is_set():
                job = self._claim()
                if job is None:
                    _wake.wait(timeout=0.5)
                    _wake.clear()
                    continue
                try:
                    self._run(job)
                except Exception:
                    traceback.print_exc()
                    self._finish(job["id"], "failed", error=traceback.format_exc(limit=3))
        finally:
            # _claim() opens a connection on this thread on its very first
            # poll, whether or not a job was ever queued — so by the time
            # `stop()` breaks this loop, every worker holds one open. join()
            # waiting for the thread to exit says nothing about that handle;
            # closing it explicitly here is what makes "every worker has
            # joined" also mean "every worker's DB connection is closed" —
            # which storage.vault.lock_vault()'s file-delete needs to be true
            # on Windows, where a still-open handle blocks the unlink outright
            # rather than just risking a race.
            db.close_connection()

    def _finish(self, job_id: str, status: str, *, error: str | None = None, result: dict | None = None) -> None:
        if ephemeral.has_job(job_id):
            ephemeral.update_job(job_id, status=status, error=error,
                                 result=result, finished_at=now_ms())
            return
        with db.tx() as c:
            c.execute(
                "UPDATE jobs SET status=?, error=?, result=?, finished_at=? WHERE id=?",
                (status, error, json.dumps(result) if result else None, now_ms(), job_id),
            )

    def _cancelled(self, job_id: str) -> bool:
        if ephemeral.has_job(job_id):
            return ephemeral.job_cancelled(job_id)
        row = db.connect().execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    # ── job kinds ────────────────────────────────────────────────────────
    # Registry rather than an if-chain: a service registers its kinds at
    # import time, which is what stops the dispatcher becoming the next
    # place every feature has to be edited into.
    def _run(self, job: dict) -> None:
        handler = HANDLERS.get(job["kind"])
        if handler is None:
            self._finish(job["id"], "failed", error=f"no handler registered for {job['kind']}")
            return
        handler(self, job)

    def _run_chat(self, job: dict) -> None:
        """The conversation workflow: context → model → tool? → model → done.

        The loop is what makes a Turn own *all* the work its answer required.
        A tool call is not a separate conversation; it is another step inside
        the same turn, which is why cancelling the turn cancels the tool.
        """
        # Imported here, not at module scope: the tool package registers job
        # kinds back into this module at import time, so a top-level import
        # would be circular.
        from ..assets import service as assets
        from ..context import service as context
        from ..tools import runtime as tools
        from ..tools.registry import ToolContext

        payload = json.loads(job["payload"])
        turn_id = job["turn_id"]
        conversation_id = payload["conversation_id"]
        cancelled = lambda: self._cancelled(job["id"])

        status = turns.status_of(turn_id)
        if status is None or status in turns.TERMINAL:
            self._finish(job["id"], "cancelled")
            return

        # The guard above checks the TURN, but every event this job emits names
        # the CONVERSATION, and `events.conversation_id` is a foreign key. A
        # chat deleted while its reply was in flight therefore passed the turn
        # check and then killed the job on the first emit with an unhandled
        # IntegrityError — a stack trace in the log for something the user did
        # on purpose. Deleting a conversation cancels its work; it is not a
        # fault.
        if not ephemeral.is_incognito(conversation_id):
            alive = db.connect().execute(
                "SELECT 1 FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            if alive is None:
                self._finish(job["id"], "cancelled")
                return

        bus.emit("job.started", {"job_id": job["id"], "kind": "chat.reply", "label": "Generating reply"},
                 conversation_id=conversation_id, turn_id=turn_id)

        turns.set_status(turn_id, "building_context")

        # A turn referencing an asset that is not ready must wait on it or fail
        # explicitly (§2.6). Proceeding with empty content is prohibited — it
        # is what made V1 look like it was ignoring uploaded files.
        if not self._await_assets(job, turn_id, conversation_id, assets):
            return

        incognito = turns.is_incognito(conversation_id)
        bundle = context.build(conversation_id, payload["text"], turn_id=turn_id)
        messages = list(bundle.messages)
        messages.insert(1, {"role": "system",
                            "content": tools.system_prompt(incognito=incognito)})

        # Skills that this request looks like it needs, inlined now rather than
        # fetched by the model. The model *can* fetch one — `read_skill` is a
        # tool — but a round trip on the local 7B costs ~8s and carries the
        # tool-loop risk, and a turn that says "make me a deck" does not need
        # to be asked whether it meant it.
        for skill in skills.select(payload["text"]):
            messages.insert(2, {"role": "system", "content": skill.body})
            bus.emit("job.progress", {"job_id": job["id"], "skill": skill.name},
                     conversation_id=conversation_id, turn_id=turn_id)

        if cancelled():
            turns.finish_cancelled(turn_id, "")
            self._finish(job["id"], "cancelled")
            return

        visible_total: list[str] = []
        # Accumulated across every model call in the turn. A tool turn makes
        # several, and reporting only the last one would understate what the
        # turn actually cost by a factor of the number of steps.
        totals = {"input_tokens": 0, "output_tokens": 0,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                  "prompt_tokens_total": 0,
                  "model_calls": 0, "tool_calls": 0, "model": None}
        ctx = ToolContext(job_id=job["id"], turn_id=turn_id,
                          conversation_id=conversation_id, should_cancel=cancelled)
        corrections = 0

        # Bound once, not per iteration: a settings change landing mid-turn
        # would otherwise move the ceiling under a loop that is already running.
        max_steps = tools.max_tool_steps()

        for step in range(max_steps + 1):
            # Each model call in a turn writes its own prose, and joining them
            # with nothing between runs one into the next. Measured live: a
            # turn whose two calls both said "12 * 12 = 144" rendered as
            # "14412 * 12 = 144". Emitted as a token as well as accumulated, so
            # the live stream and the stored message do not disagree.
            if step and visible_total and not visible_total[-1].endswith(("\n", " ")):
                visible_total.append("\n\n")
                bus.emit("token", {"text": "\n\n"},
                         conversation_id=conversation_id, turn_id=turn_id)

            reply, stopped = self._stream_once(job, turn_id, conversation_id,
                                               messages, visible_total, totals)
            if stopped:
                return

            plan = tools.parse_plan(reply)
            if plan:
                bus.emit("plan.proposed", {"plan": plan},
                         conversation_id=conversation_id, turn_id=turn_id)

            call = tools.parse_call(reply)
            if call is None:
                break

            if step == max_steps:
                # A model that keeps calling tools is looping, not working.
                visible_total.append("\n\n[Stopped: too many tool steps in one turn.]")
                break

            if call.get("malformed"):
                # One structured correction, then it is treated as prose. The
                # comment said that; the code did not — it `continue`d every
                # time, so a model that kept making the same escaping mistake
                # burned all eight steps and produced nothing but the stop
                # message. Measured: three document tasks in a row, ~90s each,
                # zero executions.
                corrections += 1
                if corrections > 1:
                    visible_total.append(
                        "\n\n[I couldn't read the tool call that was produced, "
                        "so nothing was run.]")
                    break
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content":
                                 f'Your tool block was malformed ({call["malformed"]}). '
                                 f'Send the code with no JSON at all, like this:\n'
                                 f'<tool name="{call["name"]}">\n```\n…code…\n```\n</tool>'})
                continue

            turns.set_status(turn_id, "tool_running")
            totals["tool_calls"] += 1
            result = tools.execute(call["name"], call["arguments"], ctx)

            if cancelled():
                turns.finish_cancelled(turn_id, "".join(visible_total))
                self._finish(job["id"], "cancelled")
                return

            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": tools.format_result(result)})

        final = "".join(visible_total).strip()
        if not final:
            # A turn that completes with nothing to show is not a success. It
            # happens when the model emits an unterminated tool block: the
            # stream filter correctly withholds the markup, and there is no
            # prose behind it, so the user gets a turn that finished and said
            # nothing. Measured on qwen2.5:7b — 2 of 8 turns. A failure with a
            # reason and a Retry beats a blank reply (§10.1).
            turns.fail(turn_id, "empty_reply",
                       "The model replied with an unfinished tool call and no "
                       "text. Nothing was lost — try again.", retryable=True)
            self._finish(job["id"], "failed", error="no visible text")
            return

        turns.complete(turn_id, final, usage=totals)
        bus.emit("job.completed", {"job_id": job["id"], "status": "completed"},
                 conversation_id=conversation_id, turn_id=turn_id)
        self._finish(job["id"], "completed")

    def _await_assets(self, job: dict, turn_id: str, conversation_id: str, assets) -> bool:
        """Block until referenced assets finish ingesting. False == turn ended."""
        pending = assets.pending_for_turn(turn_id)
        if not pending:
            return True

        turns.set_status(turn_id, "tool_running", detail="Reading attached documents")
        deadline = time.time() + ASSET_WAIT_S
        while time.time() < deadline:
            if self._cancelled(job["id"]):
                turns.finish_cancelled(turn_id, "")
                self._finish(job["id"], "cancelled")
                return False
            pending = assets.pending_for_turn(turn_id)
            if not pending:
                return True
            time.sleep(0.2)

        turns.fail(turn_id, "asset_unavailable",
                   "An attached document is still being processed. Try again in a moment.",
                   retryable=True)
        self._finish(job["id"], "failed", error=f"assets not ready: {pending}")
        return False

    def _stream_once(self, job: dict, turn_id: str, conversation_id: str,
                     messages: list[dict], visible_total: list[str],
                     totals: dict | None = None) -> tuple[str, bool]:
        """One model call. Returns (raw reply, turn_ended?).

        Protocol markup is kept out of the token stream: the user reads prose,
        not `<tool name=…>`. The raw text is still returned in full, because
        that is what gets parsed.
        """
        from ..tools.runtime import StreamFilter

        turns.set_status(turn_id, "thinking")
        streaming = False
        screen = StreamFilter()
        buf: list[str] = []
        raw: list[str] = []
        last_flush = time.time()

        def flush() -> None:
            if not buf:
                return
            text = "".join(buf)
            buf.clear()
            bus.emit("token", {"text": text}, conversation_id=conversation_id, turn_id=turn_id)

        # Batched the same way as the reply text, and for the same reason —
        # one event per SSE chunk would put thousands of rows in the log for
        # a single reasoning-heavy reply. A distinct kind ("thinking", not
        # "token") rather than a marker inside the text: the frontend renders
        # it in its own collapsed block, not inline with the answer, so it
        # has to be separable without parsing.
        thinking_buf: list[str] = []
        thinking_last_flush = time.time()

        def on_thinking(piece: str) -> None:
            nonlocal thinking_last_flush
            thinking_buf.append(piece)
            if time.time() - thinking_last_flush > FLUSH_INTERVAL_S or len(thinking_buf) >= FLUSH_TOKENS:
                flush_thinking()
                thinking_last_flush = time.time()

        def flush_thinking() -> None:
            if not thinking_buf:
                return
            text = "".join(thinking_buf)
            thinking_buf.clear()
            bus.emit("thinking", {"text": text}, conversation_id=conversation_id, turn_id=turn_id)

        usage: dict = {}
        scrub_map: list = []
        try:
            for token in gateway.stream_completion(messages, usage=usage, scrub_map=scrub_map,
                                                    on_thinking=on_thinking):
                # CRS §9.2 — a cancellation checkpoint on every iteration of
                # the token loop. Without one, "stop" cannot take effect until
                # the provider finishes on its own.
                if self._cancelled(job["id"]):
                    flush()
                    flush_thinking()
                    turns.finish_cancelled(turn_id, "".join(visible_total))
                    self._finish(job["id"], "cancelled")
                    return "", True

                raw.append(token)
                shown = screen.feed(token)
                if shown:
                    if not streaming:
                        # First visible token — the turn is no longer waiting,
                        # it is writing.
                        turns.set_status(turn_id, "streaming")
                        streaming = True
                    buf.append(shown)
                    visible_total.append(shown)
                if time.time() - last_flush > FLUSH_INTERVAL_S or len(buf) >= FLUSH_TOKENS:
                    flush()
                    last_flush = time.time()

            tail = screen.flush()
            if tail:
                if not streaming:
                    turns.set_status(turn_id, "streaming")
                buf.append(tail)
                visible_total.append(tail)
            flush()
            flush_thinking()
            if totals is not None:
                totals["model_calls"] += 1
                for field in ("input_tokens", "output_tokens", "prompt_tokens_total",
                              "cache_creation_input_tokens", "cache_read_input_tokens"):
                    totals[field] = totals.get(field, 0) + (usage.get(field) or 0)
                totals["model"] = usage.get("model") or totals.get("model")
            if scrub_map:
                # The on-device reveal: what left pseudonymized, and what it
                # stood for. Never sent anywhere but this socket.
                bus.emit("privacy.scrub", {"mapping": scrub_map},
                         conversation_id=conversation_id, turn_id=turn_id)
        except Exception as exc:
            flush()
            flush_thinking()
            code, message, retryable = _classify(exc)
            turns.fail(turn_id, code, message, retryable, partial_text="".join(visible_total))
            self._finish(job["id"], "failed", error=str(exc))
            return "", True

        return "".join(raw), False


def _classify(exc: Exception) -> tuple[str, str, bool]:
    """CRS §10.2 — map a provider failure to an actionable, honest error.

    `retryable` has to be truthful: a missing key and a rate limit are both
    failures, but only one of them is worth showing a retry button for.
    """
    text = str(exc).lower()
    if "no api key is configured" in text:
        return "provider_auth", str(exc), False
    if "401" in text or "unauthor" in text or "invalid_api_key" in text:
        return "provider_auth", "That API key was rejected. Check it in Settings.", False
    # 403 is a refusal, not a hiccup. Classifying it as retryable would show a
    # Retry button that can never succeed, which is exactly the dishonesty
    # §10.1.2 exists to prevent.
    if "403" in text or "forbidden" in text:
        return ("provider_auth",
                "The provider refused this request (403). The key is reaching it but "
                "isn't allowed to use this model — check the key's permissions, or the "
                "base URL if you're going through a proxy.", False)
    if "429" in text or "rate limit" in text:
        return "provider_rate_limited", "The provider is rate-limiting us. Give it a moment.", True
    if "402" in text or "quota" in text or "billing" in text or "insufficient" in text:
        return "provider_quota", "The provider says this account is out of quota.", False
    if "404" in text or "model_not_found" in text:
        return "model_unavailable", "That model isn't available on this account.", False
    if "context" in text and "length" in text:
        return "context_overflow", "This chat has outgrown the model's context window.", False
    if any(code in text for code in ("500", "502", "503", "504", "bad gateway",
                                     "service unavailable", "gateway time")):
        return "provider_unreachable", "The provider is having trouble right now.", True
    # A proxy answering 200 with a non-JSON body lands here. V1 surfaced the raw
    # JSONDecodeError as a chat message from "Primnox"; naming it plainly is the
    # difference between an actionable failure and a baffling one.
    if "expecting value" in text or "jsondecode" in text:
        return ("provider_unreachable",
                "The provider returned a response that wasn't valid JSON — usually a "
                "proxy or gateway error page rather than the model.", True)
    if "urlopen" in text or "connection" in text or "timed out" in text:
        return "provider_unreachable", "Couldn't reach the model provider.", True
    return "internal", "Something went wrong generating the reply.", True


HANDLERS: dict[str, object] = {
    "chat.reply": Scheduler._run_chat,
}


def register(kind: str, handler) -> None:
    """Services register their job kinds here (CRS §12.1).

    `asset.ocr`, `tool.python`, `context.build` and the rest arrive this way —
    the kernel coordinates, it does not grow a branch per capability.
    """
    if not any(kind.startswith(p) for p in
               ("chat.", "tool.", "asset.", "context.", "workspace.", "memory.", "maintenance.")):
        raise ValueError(f"job kind must be namespaced by service: {kind!r}")
    HANDLERS[kind] = handler


_wake = threading.Event()
scheduler = Scheduler()
