import hashlib
import time
from unittest.mock import patch

import pytest

from file_organizer.services.hasher import _hash_file, _rebuild_duplicate_groups, hash_unprocessed


# ── _hash_file ────────────────────────────────────────────────────────────────

def test_hash_file_known_content(tmp_path):
    content = b"hello world"
    f = tmp_path / "file.bin"
    f.write_bytes(content)

    result = _hash_file(str(f))

    assert result == hashlib.sha256(content).hexdigest()


def test_hash_file_empty_file(tmp_path):
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")

    result = _hash_file(str(f))

    assert result == hashlib.sha256(b"").hexdigest()


def test_hash_file_nonexistent_returns_none(tmp_path):
    result = _hash_file(str(tmp_path / "missing.bin"))
    assert result is None


def test_hash_file_os_error_returns_none(tmp_path):
    f = tmp_path / "file.bin"
    f.write_bytes(b"data")

    with patch("builtins.open", side_effect=OSError("permission denied")):
        result = _hash_file(str(f))

    assert result is None


def test_hash_file_two_identical_files_match(tmp_path):
    content = b"identical content"
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(content)
    b.write_bytes(content)

    assert _hash_file(str(a)) == _hash_file(str(b))


def test_hash_file_different_content_different_hash(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"hello")
    b.write_bytes(b"world")

    assert _hash_file(str(a)) != _hash_file(str(b))


def test_hash_file_large_file_hashed_correctly(tmp_path):
    content = b"x" * (65536 * 3 + 1000)
    f = tmp_path / "large.bin"
    f.write_bytes(content)

    result = _hash_file(str(f))

    assert result == hashlib.sha256(content).hexdigest()


# ── _rebuild_duplicate_groups ─────────────────────────────────────────────────

def test_rebuild_duplicate_groups_empty_db(db):
    _rebuild_duplicate_groups(db)
    assert db.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0] == 0


def test_rebuild_duplicate_groups_creates_group(db, folder_id, insert_file):
    insert_file("a.bin", sha256="abc", size=1000)
    insert_file("b.bin", sha256="abc", size=1000, path="/watched/b.bin")

    _rebuild_duplicate_groups(db)

    row = db.execute("SELECT * FROM duplicate_groups WHERE sha256='abc'").fetchone()
    assert row is not None
    assert row["file_count"] == 2
    assert row["wasted"] == 1000


def test_rebuild_duplicate_groups_three_files_wasted(db, folder_id, insert_file):
    for name in ("a.bin", "b.bin", "c.bin"):
        insert_file(name, sha256="xyz", size=500, path=f"/watched/{name}")

    _rebuild_duplicate_groups(db)

    row = db.execute("SELECT * FROM duplicate_groups WHERE sha256='xyz'").fetchone()
    assert row["file_count"] == 3
    assert row["wasted"] == 1000


def test_rebuild_duplicate_groups_unique_sha_not_grouped(db, folder_id, insert_file):
    insert_file("solo.bin", sha256="unique_sha")

    _rebuild_duplicate_groups(db)

    assert db.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0] == 0


def test_rebuild_duplicate_groups_null_sha_excluded(db, folder_id, insert_file):
    insert_file("a.bin")
    insert_file("b.bin", path="/watched/b.bin")

    _rebuild_duplicate_groups(db)

    assert db.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0] == 0


def test_rebuild_duplicate_groups_clears_old_data(db, folder_id, insert_file):
    db.execute(
        "INSERT INTO duplicate_groups (sha256, file_count, total_size, wasted) VALUES ('stale', 5, 5000, 4000)"
    )
    db.commit()

    _rebuild_duplicate_groups(db)

    stale = db.execute("SELECT * FROM duplicate_groups WHERE sha256='stale'").fetchone()
    assert stale is None


def test_rebuild_duplicate_groups_members_inserted(db, folder_id, insert_file):
    id1 = insert_file("a.bin", sha256="m_sha", size=100)
    id2 = insert_file("b.bin", sha256="m_sha", size=100, path="/watched/b.bin")

    _rebuild_duplicate_groups(db)

    gid = db.execute("SELECT id FROM duplicate_groups WHERE sha256='m_sha'").fetchone()["id"]
    member_ids = {
        r["file_id"]
        for r in db.execute("SELECT file_id FROM duplicate_members WHERE group_id=?", (gid,))
    }
    assert member_ids == {id1, id2}


# ── hash_unprocessed ──────────────────────────────────────────────────────────

def test_hash_unprocessed_no_candidates_returns_zero(db, folder_id, console):
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/solo.txt", "solo.txt", ".txt", 999, now, now, now),
    )
    db.commit()

    result = hash_unprocessed(db, console)

    assert result.hashed == 0
    assert result.skipped_unique == 1


def test_hash_unprocessed_hashes_same_size_files(db, folder_id, tmp_path, console):
    now = time.time()
    for i in range(2):
        f = tmp_path / f"f{i}.bin"
        f.write_bytes(b"x" * 100)
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
            (folder_id, str(f), f"f{i}.bin", ".bin", 100, now, now, now),
        )
    db.commit()

    result = hash_unprocessed(db, console)

    assert result.hashed == 2
    assert result.skipped_unique == 0


def test_hash_unprocessed_creates_duplicate_group(db, folder_id, tmp_path, console):
    now = time.time()
    content = b"same content"
    for i in range(2):
        f = tmp_path / f"dup{i}.bin"
        f.write_bytes(content)
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
            (folder_id, str(f), f"dup{i}.bin", ".bin", len(content), now, now, now),
        )
    db.commit()

    hash_unprocessed(db, console)

    groups = db.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0]
    assert groups == 1


def test_hash_unprocessed_skips_junk(db, folder_id, tmp_path, console):
    now = time.time()
    for i in range(2):
        f = tmp_path / f"f{i}.tmp"
        f.write_bytes(b"z" * 50)
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)""",
            (folder_id, str(f), f"f{i}.tmp", ".tmp", 50, now, now, now),
        )
    db.commit()

    result = hash_unprocessed(db, console)

    assert result.hashed == 0


def test_hash_unprocessed_skips_already_hashed(db, folder_id, tmp_path, console):
    now = time.time()
    for i in range(2):
        f = tmp_path / f"hashed{i}.bin"
        f.write_bytes(b"a" * 200)
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
            (folder_id, str(f), f"hashed{i}.bin", ".bin", 200, now, "existhash", now, now),
        )
    db.commit()

    result = hash_unprocessed(db, console)

    assert result.hashed == 0


def test_hash_unprocessed_updates_sha256_in_db(db, folder_id, tmp_path, console):
    now = time.time()
    for i in range(2):
        f = tmp_path / f"g{i}.bin"
        f.write_bytes(b"q" * 50)
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
            (folder_id, str(f), f"g{i}.bin", ".bin", 50, now, now, now),
        )
    db.commit()

    hash_unprocessed(db, console)

    rows = db.execute("SELECT sha256 FROM files WHERE sha256 IS NOT NULL").fetchall()
    assert len(rows) == 2


def test_hash_unprocessed_returns_elapsed(db, folder_id, console):
    result = hash_unprocessed(db, console)
    assert result.elapsed >= 0
