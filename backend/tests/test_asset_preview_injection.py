"""Regression — the SQLite asset previewer must not let a crafted table name
in an uploaded .db file break out of its quoted identifier.

`primnox2.assets.preview._sqlite()` reads table names straight from
`sqlite_master` of whatever file a user (or a document they were sent)
uploads, then interpolated them into `SELECT * FROM "{table}"` with no
escaping. SQLite has no placeholder syntax for identifiers, only values, so a
table containing an embedded `"` closed that quote early.

Confirmed impact in THIS runtime (Python 3.11's `sqlite3.execute()` silently
truncates at the first `;` rather than running a second statement, and the
connection here is already opened read-only): a table name containing `"`
crashed the whole preview with an unhandled OperationalError — a DoS on a
single oddly-named table, not data exfiltration. The fix (doubling embedded
`"`, the SQL-standard identifier escape) is still worth having as
defense-in-depth against a future change to a different DB-API, a switch to
`executescript()`, or a write-mode connection removing today's incidental
protections — but it was not a demonstrated arbitrary-SQL-execution exploit
here, and should not be described as one.
"""
from __future__ import annotations

import sqlite3

from primnox2.assets import preview


def test_normal_table_previews_correctly(tmp_path):
    db_path = tmp_path / "normal.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE people (name TEXT, age INT)")
    conn.execute("INSERT INTO people VALUES ('Ada', 30)")
    conn.commit()
    conn.close()

    result = preview._sqlite(db_path)
    assert result["sheets"][0]["name"] == "people"
    assert result["sheets"][0]["rows"] == [["Ada", "30"]]


def test_table_name_with_embedded_quote_cannot_break_out_of_the_identifier(tmp_path):
    """A table name shaped like an injection attempt must preview as a table
    with that literal (odd) name rather than crashing or altering the query.
    Before the fix this raised an unhandled OperationalError — the embedded
    `"` closed the identifier's quote early, and what followed became
    unparseable SQL rather than part of the table name."""
    db_path = tmp_path / "hostile.db"
    target = tmp_path / "should_never_be_created.db"
    evil_name = f"evil\"; ATTACH DATABASE '{target}' AS x; --"
    escaped_for_setup = evil_name.replace('"', '""')  # only for building the fixture

    conn = sqlite3.connect(db_path)
    conn.execute(f'CREATE TABLE "{escaped_for_setup}" (col TEXT)')
    conn.execute(f'INSERT INTO "{escaped_for_setup}" VALUES (\'safe\')')
    conn.commit()
    conn.close()

    result = preview._sqlite(db_path)

    assert result["sheets"][0]["name"] == evil_name
    assert result["sheets"][0]["rows"] == [["safe"]]
    assert not target.exists(), "the injected ATTACH DATABASE statement executed"
