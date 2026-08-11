"""Regression tests for a real production incident this session: a forceful
process kill during local_vault's _secure_delete() (in-place overwrite before
unlink) left memory.db as a malformed SQLite file, and the app hard-crashed
on every subsequent startup with no recovery path. Two independent fixes:

1. local_vault.lock_vault() now verifies the .vault blob it just wrote
   actually decrypts back to the source data BEFORE touching the plaintext —
   so a bad write can no longer be followed by destroying the only good copy.
2. memory.get_db() now recovers automatically instead of crashing: if the
   vault exists, decrypt it back over the corrupted file; otherwise move the
   corrupted file aside (never delete) and start fresh.
"""
import sqlite3

import pytest

import local_vault
import memory


TEST_KEY = b"\x01" * 32  # any 32 bytes works as an AES-256-GCM key for tests


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "memory.db"
    monkeypatch.setattr(memory, "DB_PATH", p)
    memory.init_db()
    memory.add_memory("a real memory before any vault operation")
    memory._reset_db_connection()
    return p


class TestLockVaultVerifiesBeforeDeleting:
    def test_deletes_plaintext_when_vault_write_verifies(self, db_path):
        local_vault.lock_vault(db_path, key=TEST_KEY)
        assert not db_path.exists()
        assert local_vault.vault_path(db_path).exists()

    def test_leaves_plaintext_when_roundtrip_raises(self, db_path, monkeypatch):
        monkeypatch.setattr(local_vault, "_decrypt_bytes", lambda blob, key: (_ for _ in ()).throw(ValueError("corrupt")))
        local_vault.lock_vault(db_path, key=TEST_KEY)
        assert db_path.exists()  # plaintext survives — never deleted on unverified write

    def test_leaves_plaintext_when_roundtrip_data_mismatches(self, db_path, monkeypatch):
        monkeypatch.setattr(local_vault, "_decrypt_bytes", lambda blob, key: b"not the original data")
        local_vault.lock_vault(db_path, key=TEST_KEY)
        assert db_path.exists()


class TestMemoryAutoRecovery:
    def test_recovers_from_vault_when_plaintext_is_corrupted(self, db_path, monkeypatch):
        local_vault.lock_vault(db_path, key=TEST_KEY)  # plaintext deleted, .vault written
        # Recreate a *corrupted* plaintext file (simulating an interrupted
        # write) alongside the still-good .vault file.
        db_path.write_bytes(b"not a sqlite file at all")
        monkeypatch.setattr(local_vault, "_keychain_load", lambda: TEST_KEY)

        conn = memory.get_db()
        assert isinstance(conn, sqlite3.Connection)
        rows = conn.execute("SELECT text FROM memories").fetchall()
        assert [r["text"] for r in rows] == ["a real memory before any vault operation"]

    def test_moves_corrupted_db_aside_when_no_vault_exists(self, db_path):
        db_path.write_bytes(b"not a sqlite file at all")  # no .vault for this path

        # init_db() is what actually runs at startup (creates schema on the
        # recovered/fresh connection) — get_db() alone only proves the
        # connection recovers, not that the app is usable afterward.
        memory.init_db()
        conn = memory.get_db()
        assert isinstance(conn, sqlite3.Connection)
        # Fresh, usable DB — the old bytes are preserved off to the side, not deleted.
        assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0
        corrupted = list(db_path.parent.glob(f"{db_path.name}.corrupted-*"))
        assert len(corrupted) == 1
        assert corrupted[0].read_bytes() == b"not a sqlite file at all"
