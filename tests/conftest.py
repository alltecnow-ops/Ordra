import io
import sqlite3
import time
from pathlib import Path

import pytest
from rich.console import Console

SCHEMA_PATH = Path(__file__).parent.parent / "file_organizer" / "db" / "schema.sql"


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def folder_id(db):
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES (?, ?)",
        ("/watched", time.time()),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM watched_folders WHERE path = '/watched'"
    ).fetchone()["id"]


@pytest.fixture()
def console():
    return Console(file=io.StringIO(), width=120)


@pytest.fixture()
def insert_file(db, folder_id):
    now = time.time()

    def _insert(
        name: str,
        ext: str = ".txt",
        size: int = 1000,
        mtime: float | None = None,
        sha256: str | None = None,
        is_junk: int = 0,
        junk_reason: str | None = None,
        path: str | None = None,
        folder: int | None = None,
    ) -> int:
        path = path or f"/watched/{name}"
        fid = folder if folder is not None else folder_id
        db.execute(
            """INSERT INTO files
               (folder_id, path, name, extension, size_bytes, mtime,
                sha256, is_junk, junk_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fid, path, name, ext, size,
             mtime if mtime is not None else now,
             sha256, is_junk, junk_reason, now, now),
        )
        db.commit()
        return db.execute(
            "SELECT id FROM files WHERE path = ?", (path,)
        ).fetchone()["id"]

    return _insert


@pytest.fixture()
def build_duplicate_groups(db):
    def _rebuild():
        db.execute("DELETE FROM duplicate_groups")
        db.execute(
            """INSERT INTO duplicate_groups (sha256, file_count, total_size, wasted)
               SELECT sha256, COUNT(*), COUNT(*) * MAX(size_bytes),
                      (COUNT(*) - 1) * MAX(size_bytes)
               FROM files WHERE sha256 IS NOT NULL
               GROUP BY sha256 HAVING COUNT(*) > 1"""
        )
        db.execute(
            """INSERT INTO duplicate_members (group_id, file_id)
               SELECT dg.id, f.id FROM duplicate_groups dg
               JOIN files f ON f.sha256 = dg.sha256"""
        )
        db.commit()

    return _rebuild
