"""memory.py now keeps a long-lived DB connection open per thread instead of
reconnecting on every call (see memory.get_db()). local_vault.py rewrites the
memory DB file in place during unlock/lock, so it has to explicitly drop that
cache afterwards or a thread's connection goes stale against the old file
content. This only tests the routing/invalidation logic, not real vault
crypto.
"""
from pathlib import Path

import local_vault
import memory


def test_invalidates_when_path_matches_memory_db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.db")
    memory.init_db()
    conn_before = memory.get_db()

    local_vault._invalidate_memory_connection_cache(tmp_path / "memory.db")

    assert memory.get_db() is not conn_before


def test_does_not_invalidate_for_an_unrelated_path(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.db")
    memory.init_db()
    conn_before = memory.get_db()

    local_vault._invalidate_memory_connection_cache(tmp_path / "some_other_file.db")

    assert memory.get_db() is conn_before


def test_never_raises_even_if_memory_import_or_comparison_fails(tmp_path):
    # Defensive: a vault operation on an unrelated db_path (or in a context
    # where memory.py somehow can't be imported) must never blow up the
    # vault operation itself.
    local_vault._invalidate_memory_connection_cache(Path("/nonexistent/path.db"))
