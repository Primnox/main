"""Security regressions for the sandbox boundary.

Every test here corresponds to something that was measured FAILING against
the real AppContainer backend during a sandbox audit, not to a hypothetical.
They are deliberately behavioural — they run real code in the real sandbox
and assert on what the OS actually permitted — because the previous versions
of these claims were true in the docstrings and false on the machine.
"""
from __future__ import annotations

import threading
import time

import pytest

from primnox2.sandbox import manager, permissions


def run(code: str, **manifest_kw):
    return manager.execute(
        code=code, runtime="python",
        manifest=permissions.manifest_for("python", permissions.SAFE, **manifest_kw),
    )


def test_execution_cannot_read_another_executions_workspace(sandbox_ready):
    """Was broken: every session directory inherited one full-access ACE from
    the shared sandbox root, and all executions share a single AppContainer
    SID — so session B listed the root, read A's file, and wrote into A's
    directory. workspace.py claimed "nothing leaks between them"; it did."""
    a = manager.execute(
        code='open("secret.txt", "w").write("SESSION-A-PRIVATE")\nprint("ok")',
        runtime="python",
        manifest=permissions.manifest_for("python", permissions.SAFE),
        keep_workspace=True,
    )
    assert a["ok"], f"setup execution failed: {a.get('error')}"

    b = run(r'''
import os, glob
parent = os.path.abspath(os.path.join(os.getcwd(), ".."))
try:
    siblings = os.listdir(parent)
    print("LISTED:", len(siblings))
except Exception as e:
    print("LIST BLOCKED:", type(e).__name__)
    siblings = []
for hit in glob.glob(os.path.join(parent, "*", "secret.txt")):
    try:
        print("READ:", open(hit).read())
    except Exception as e:
        print("READ BLOCKED:", type(e).__name__)
''')
    out = b["stdout"]
    assert "SESSION-A-PRIVATE" not in out, \
        f"one execution read another's private file:\n{out}"
    assert "LIST BLOCKED" in out, \
        f"the shared sandbox root should not be enumerable:\n{out}"


def test_execution_cannot_write_outside_its_own_workspace(sandbox_ready):
    """Was broken one level up: `../escaped.txt` landed in the shared sandbox
    root, because that root was granted full access with (OI)(CI)."""
    r = run(r'''
for rel in ["../escaped.txt", "../../escaped.txt"]:
    try:
        open(rel, "w").write("ESCAPED")
        print("WROTE", rel)
    except Exception as e:
        print("BLOCKED", rel, type(e).__name__)
''')
    assert "WROTE" not in r["stdout"], \
        f"an execution wrote outside its workspace:\n{r['stdout']}"


def test_cancelling_a_sandboxed_execution_stops_it_promptly(sandbox_ready):
    """Was broken: supervisor.run() accepted `should_cancel` but only passed
    it to the UNSANDBOXED path, and the AppContainer path used a single
    blocking wait. Measured: cancel at t=3s on a 45s run returned at t=45s,
    so "Stop" did nothing for the whole default 300s timeout."""
    flag = {"stop": False}
    threading.Thread(
        target=lambda: (time.sleep(2), flag.__setitem__("stop", True)),
        daemon=True,
    ).start()

    started = time.time()
    r = manager.execute(
        code="import time\nprint('running', flush=True)\ntime.sleep(40)",
        runtime="python",
        manifest=permissions.manifest_for("python", permissions.SAFE, timeout_s=40),
        should_cancel=lambda: flag["stop"],
    )
    elapsed = time.time() - started

    assert elapsed < 15, f"cancellation ignored — ran {elapsed:.0f}s of a 40s execution"
    assert r["code"] == "cancelled_by_user", \
        f"expected cancelled_by_user, got {r['code']!r}"


def test_disk_limit_is_enforced_even_when_written_in_one_burst(sandbox_ready):
    """`disk_mb` was validated, stored with the execution record, and then
    never applied to anything: 40MB written against a declared 16MB.

    A burst that finishes between polls cannot be killed mid-write, so the
    limit is enforced in two parts — kill sustained growth, and fail the
    execution afterwards if it ended over. This covers the harder half."""
    r = run('''
with open("fill.bin", "wb") as f:
    for _ in range(40):
        f.write(b"A" * 1024 * 1024)
print("wrote 40MB")
''', disk_mb=16)

    assert not r["ok"], "an execution 2.5x over its declared disk limit was reported as success"
    assert r["code"] == "disk_limit_exceeded", f"expected disk_limit_exceeded, got {r['code']!r}"


def test_disk_limit_does_not_fail_an_execution_within_its_budget(sandbox_ready):
    """The other half of the above: no false positives, or every document
    workflow that writes a normal-sized file starts failing."""
    r = run('''
with open("small.bin", "wb") as f:
    f.write(b"A" * 1024 * 1024 * 4)
print("wrote 4MB")
''', disk_mb=64)
    assert r["ok"], f"a 4MB write against a 64MB limit failed: {r.get('error')}"


def test_network_is_refused_on_the_offline_tier(sandbox_ready):
    """The safe tier promises no network. Zero capabilities means the OS
    refuses the socket outright rather than a firewall dropping packets."""
    r = run('''
import socket
try:
    socket.create_connection(("8.8.8.8", 53), timeout=4).close()
    print("CONNECTED")
except Exception as e:
    print("BLOCKED:", type(e).__name__)
''')
    assert "CONNECTED" not in r["stdout"], f"offline tier reached the network:\n{r['stdout']}"


def test_provider_credentials_are_not_visible_to_sandboxed_code(monkeypatch, sandbox_ready):
    """The parent process holds real provider keys in its environment. A
    prompt-injected script reading os.environ must not find them."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-TEST-MUST-NOT-LEAK")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-TEST-MUST-NOT-LEAK")

    r = run('''
import os
print("LEAKED:", [k for k in os.environ if "KEY" in k.upper() or "TOKEN" in k.upper()])
print("VALUES:", [v for v in os.environ.values() if "MUST-NOT-LEAK" in v])
''')
    assert "MUST-NOT-LEAK" not in r["stdout"], \
        f"provider credentials leaked into the sandbox:\n{r['stdout']}"


def test_fork_bomb_is_capped_by_the_job_object(sandbox_ready):
    r = run('''
import subprocess, sys
spawned = 0
procs = []
for _ in range(200):
    try:
        procs.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"]))
        spawned += 1
    except Exception:
        break
print("SPAWNED:", spawned)
for p in procs:
    try: p.kill()
    except Exception: pass
''')
    spawned = int(r["stdout"].split("SPAWNED:")[1].split()[0])
    assert spawned < 200, "the active-process limit did not cap a fork bomb"
