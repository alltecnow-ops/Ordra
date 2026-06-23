import sqlite3
from pathlib import Path

import pytest

from file_organizer.db.connection import _apply_schema, get_connection


def test_get_connection_creates_all_tables():
    conn = get_connection(Path(":memory:"))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert "watched_folders" in tables
    assert "files" in tables
    assert "duplicate_groups" in tables
    assert "duplicate_members" in tables
    assert "suggestions" in tables
    assert "sort_plan" in tables


def test_get_connection_row_factory_set():
    conn = get_connection(Path(":memory:"))
    conn.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/test', 0.0)"
    )
    row = conn.execute("SELECT * FROM watched_folders").fetchone()
    conn.close()

    assert row["path"] == "/test"


def test_get_connection_foreign_keys_enforced():
    conn = get_connection(Path(":memory:"))
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO files
               (folder_id, path, name, extension, size_bytes, mtime,
                is_junk, created_at, updated_at)
               VALUES (999, '/bad', 'bad.txt', '.txt', 0, 0.0, 0, 0.0, 0.0)"""
        )
        conn.commit()
    conn.close()


def test_apply_schema_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _apply_schema(conn)
    _apply_schema(conn)

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert "files" in tables


def test_schema_creates_indexes():
    conn = get_connection(Path(":memory:"))
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    conn.close()

    assert "idx_files_size" in indexes
    assert "idx_files_sha256" in indexes
    assert "idx_files_ext" in indexes
