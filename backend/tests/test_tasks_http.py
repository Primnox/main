"""Tasks over HTTP.

v2/task_state.py has been built, tested, and feeding the model's context since
it landed — and until now no route exposed it, so the UI could not show the work
the assistant believed it was in the middle of. These pin the read path and the
two mutations, and pin the things the routes deliberately do NOT add.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from primnox2.app import app
from v2 import task_state


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def task():
    record = task_state.start(goal="audit the provider fallback path",
                              constraints=["read-only"])
    return record["id"]


def test_open_tasks_are_listed(client, task):
    body = client.get("/tasks").json()
    assert task in [t["id"] for t in body["tasks"]]


def test_get_returns_the_shape_the_ui_renders(client, task):
    task_state.add_action(task, "enumerate routes")
    body = client.get(f"/tasks/{task}").json()

    # The prototype's TaskRecord. If these drift the panel renders blank rather
    # than failing loudly, so they are worth pinning by name.
    for key in ("id", "goal", "status", "constraints", "created_at", "updated_at",
                "latest_observation", "next_actions", "known", "actions"):
        assert key in body, f"missing {key}"

    assert body["actions"][0]["description"] == "enumerate routes"
    for key in ("id", "sequence", "description", "status", "started_at",
                "finished_at", "error", "detail"):
        assert key in body["actions"][0], f"action missing {key}"


def test_unknown_task_is_404(client):
    assert client.get("/tasks/task_nope").status_code == 404


def test_resume_is_not_read_as_a_task_id(client, task):
    """Route order matters: /tasks/resume must not match /tasks/{task_id}."""
    r = client.get("/tasks/resume")
    assert r.status_code == 200
    assert r.json()["task"] is not None


def test_retarget_changes_the_goal(client, task):
    r = client.post(f"/tasks/{task}/retarget", json={"goal": "just find the bug"})
    assert r.status_code == 200
    assert r.json()["goal"] == "just find the bug"


def test_retarget_rejects_an_empty_goal(client, task):
    assert client.post(f"/tasks/{task}/retarget", json={"goal": "   "}).status_code == 400


def test_finish_derives_an_honest_status(client, task):
    """A task with an unresolved action is not 'completed', and the module's
    refusal to say otherwise has to survive the trip through HTTP."""
    action = task_state.add_action(task, "resolve the inherited timeout")
    task_state.unknown_action(action["id"], "tool died mid-flight")

    refused = client.post(f"/tasks/{task}/finish", json={"status": "completed"})
    assert refused.status_code == 400

    derived = client.post(f"/tasks/{task}/finish", json={})
    assert derived.status_code == 200
    assert derived.json()["status"] == "partial"


def test_no_pause_route_exists(client, task):
    """`blocked` means work stopped for a reason outside the task, not that
    somebody asked it to wait. A pause route would imply a capability the
    module does not have."""
    assert client.post(f"/tasks/{task}/pause").status_code in (404, 405)
