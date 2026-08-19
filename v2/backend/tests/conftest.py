"""Verification Layer fixtures.

One runtime per session: the database path is fixed at configure() time and
worker threads cache their own connections, so re-pointing it per test would
leave threads writing to a database the test no longer knows about. Tests
isolate themselves with their own conversations instead, which is also closer
to how the runtime actually runs.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Set before importing the tool package: the broker reads it at import time.
os.environ.setdefault("PRIMNOX2_AUTO_APPROVE", "all")

# Set before ANY primnox2 import, because app.py resolves it at module scope:
#
#   APPDATA = Path(os.getenv("PRIMNOX2_HOME", Path.home()/"Documents"/"Primnox2"))
#
# and its startup handler calls db.configure(APPDATA/"primnox.db"). Without this
# the moment a test constructs a TestClient, FastAPI's startup event points the
# whole runtime at the developer's REAL database and the suite starts writing to
# it. Pinning it here makes that impossible rather than merely discouraged.
TEST_HOME = Path(tempfile.mkdtemp(prefix="primnox2-verify-"))
os.environ["PRIMNOX2_HOME"] = str(TEST_HOME)

from primnox2 import paths                                    # noqa: E402
from primnox2.chat import turns                               # noqa: E402
from primnox2.kernel import scheduler as scheduler_module     # noqa: E402
from primnox2.kernel.events import bus                        # noqa: E402
from primnox2.models import gateway                           # noqa: E402
from primnox2.storage import db                               # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def runtime():
    # The same directory PRIMNOX2_HOME names, so that a TestClient's startup
    # handler reconfiguring the runtime lands on the database the tests are
    # already using instead of a second one.
    root = TEST_HOME
    paths.configure(root)
    db.configure(root / "primnox.db")
    db.init()
    scheduler_module.scheduler.start()
    yield root
    scheduler_module.scheduler.stop()


@pytest.fixture
def fresh_db():
    """Empty knowledge tables, without re-pointing the database.

    The session runtime above fixes the db path once because worker threads
    cache their own connections; re-pointing per test would leave them writing
    somewhere the test cannot see. Knowledge-graph tests assert on absolute row
    counts, so they clear their own tables instead.

    Deleting nodes cascades to edges, mentions, aliases and cluster members, so
    only the two roots and the standalone state table need naming here.
    """
    from primnox2.knowledge import live as _live

    def _clear():
        with db.tx() as c:
            c.execute("DELETE FROM knowledge_nodes")
            c.execute("DELETE FROM graph_clusters")
            c.execute("DELETE FROM graph_chunk_state")
        _live.drop_all()

    _clear()
    yield
    _clear()


class EventRecorder:
    """Collects everything on the bus, with helpers the assertions read well with."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._sid = bus.subscribe(self.events.append)

    def stop(self) -> None:
        bus.unsubscribe(self._sid)

    def kinds(self, turn_id: str | None = None) -> list[str]:
        return [e["kind"] for e in self.for_turn(turn_id)]

    def for_turn(self, turn_id: str | None) -> list[dict]:
        if turn_id is None:
            return list(self.events)
        return [e for e in self.events if e.get("turn_id") == turn_id]

    def of_kind(self, kind: str, turn_id: str | None = None) -> list[dict]:
        return [e for e in self.for_turn(turn_id) if e["kind"] == kind]

    def text(self, turn_id: str | None = None) -> str:
        return "".join(e["payload"]["text"] for e in self.of_kind("token", turn_id))

    def statuses(self, turn_id: str | None = None) -> list[str]:
        return [e["payload"]["status"] for e in self.of_kind("turn.status", turn_id)]


@pytest.fixture
def events():
    rec = EventRecorder()
    yield rec
    rec.stop()


@pytest.fixture
def conversation():
    return turns.create_conversation("Verification")["id"]


@pytest.fixture
def scripted(monkeypatch):
    """Replace the model with a fixed script, so a test asserts on the runtime
    rather than on a provider's mood."""

    def install(*replies: str, chunk: int = 7, delay: float = 0.0):
        state = {"n": 0}

        def fake_stream(messages, usage=None):
            reply = replies[min(state["n"], len(replies) - 1)]
            state["n"] += 1
            # Report plausible usage the way a real provider does, so the
            # accumulation path is exercised rather than skipped in tests.
            if usage is not None:
                usage["input_tokens"] = sum(len(m["content"]) for m in messages) // 4
                usage["output_tokens"] = len(reply) // 4
                usage["model"] = "scripted"
            for i in range(0, len(reply), chunk):
                if delay:
                    time.sleep(delay)
                yield reply[i:i + chunk]

        monkeypatch.setattr(gateway, "stream_completion", fake_stream)
        return state

    return install


def run_turn(conversation_id: str, text: str, *, asset_ids: tuple[str, ...] = ()) -> str:
    """Create a turn and enqueue its reply, exactly as the HTTP layer does."""
    from primnox2.assets import service as assets

    turn = turns.create_turn(conversation_id, text)
    for aid in asset_ids:
        assets.attach(turn["turn_id"], aid)
    scheduler_module.enqueue(turn["turn_id"], "chat.reply",
                             {"conversation_id": conversation_id, "text": text})
    return turn["turn_id"]


def wait_for_turn(turn_id: str, timeout: float = 60.0) -> str:
    """Block until the turn reaches a terminal status. Returns that status.

    Asks the runtime rather than the table: an incognito turn has no row, and
    reading one directly waits forever for a status that will never appear.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = turns.status_of(turn_id)
        if status in turns.TERMINAL:
            return status
        time.sleep(0.05)
    raise AssertionError(
        f"turn {turn_id} never terminated (stuck in {turns.status_of(turn_id) or 'missing'})")


def wait_until(predicate, timeout: float = 20.0, what: str = "condition") -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture(scope="session")
def sandbox_ready():
    """Ensure an execution backend exists, or skip the tests that need one.

    Provisioning is slow on a cold machine, so it happens once per session.
    """
    from primnox2.sandbox import supervisor

    backend = supervisor.available_backend()
    if backend is None:
        pytest.skip("no sandbox backend available and unsandboxed execution not permitted")
    return backend
