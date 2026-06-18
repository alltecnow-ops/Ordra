import time
from pathlib import Path

import pytest

from file_organizer.services.duplicates import (
    DuplicateGroup,
    SpaceSummary,
    get_duplicate_groups,
    get_space_summary,
)


def _make_group(db, sha256, size, count=2, folder_id=None):
    now = time.time()
    if folder_id is None:
        db.execute(
            "INSERT INTO watched_folders (path, added_at) VALUES (?, ?)",
            (f"/{sha256}_folder", now),
        )
        db.commit()
        folder_id = db.execute(
            "SELECT id FROM watched_folders WHERE path=?", (f"/{sha256}_folder",)
        ).fetchone()["id"]

    for i in range(count):
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
            (folder_id, f"/{sha256}_folder/file_{i}.bin",
             f"file_{i}.bin", ".bin", size, now, sha256, now, now),
        )
    db.commit()

    db.execute("DELETE FROM duplicate_groups WHERE sha256=?", (sha256,))
    db.execute(
        """INSERT INTO duplicate_groups (sha256, file_count, total_size, wasted)
           VALUES (?, ?, ?, ?)""",
        (sha256, count, count * size, (count - 1) * size),
    )
    db.commit()
    gid = db.execute(
        "SELECT id FROM duplicate_groups WHERE sha256=?", (sha256,)
    ).fetchone()["id"]
    for row in db.execute(
        "SELECT id FROM files WHERE sha256=?", (sha256,)
    ).fetchall():
        db.execute(
            "INSERT OR IGNORE INTO duplicate_members (group_id, file_id) VALUES (?,?)",
            (gid, row["id"]),
        )
    db.commit()
    return folder_id


# ── get_space_summary ─────────────────────────────────────────────────────────

def test_space_summary_empty_db(db):
    s = get_space_summary(db)
    assert s.total_files == 0
    assert s.total_size_bytes == 0
    assert s.duplicate_wasted_bytes == 0
    assert s.junk_bytes == 0
    assert s.reclaimable_bytes == 0


def test_space_summary_total_size(db, folder_id, insert_file):
    for i in range(3):
        insert_file(f"f{i}.txt", size=3000, path=f"/watched/f{i}.txt")

    s = get_space_summary(db)

    assert s.total_files == 3
    assert s.total_size_bytes == 9000


def test_space_summary_with_duplicates(db, folder_id, insert_file, build_duplicate_groups):
    insert_file("a.txt", sha256="abc", size=1000)
    insert_file("b.txt", sha256="abc", size=1000, path="/watched/b.txt")
    build_duplicate_groups()

    s = get_space_summary(db)

    assert s.duplicate_wasted_bytes == 1000
    assert s.reclaimable_bytes >= 1000


def test_space_summary_with_junk(db, insert_file):
    insert_file("Thumbs.db", size=500, is_junk=1, junk_reason="system file")

    s = get_space_summary(db)

    assert s.junk_bytes == 500
    assert s.reclaimable_bytes == 500


def test_space_summary_reclaimable_is_sum(db, folder_id, insert_file, build_duplicate_groups):
    insert_file("a.bin", sha256="x1", size=1000)
    insert_file("b.bin", sha256="x1", size=1000, path="/watched/b.bin")
    build_duplicate_groups()
    insert_file("junk.tmp", size=300, is_junk=1, junk_reason="tmp",
                path="/watched/junk.tmp")

    s = get_space_summary(db)

    assert s.reclaimable_bytes == s.duplicate_wasted_bytes + s.junk_bytes


def test_space_summary_folder_scope(db, folder_id, insert_file):
    now = time.time()
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/other', ?)", (now,)
    )
    db.commit()
    other_id = db.execute(
        "SELECT id FROM watched_folders WHERE path='/other'"
    ).fetchone()["id"]

    insert_file("mine.txt", size=5000)
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (other_id, "/other/theirs.txt", "theirs.txt", ".txt", 9000, now, now, now),
    )
    db.commit()

    s = get_space_summary(db, folder_id=folder_id)

    assert s.total_size_bytes == 5000
    assert s.total_files == 1


def test_space_summary_all_folders_when_none(db, folder_id, insert_file):
    now = time.time()
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/other', ?)", (now,)
    )
    db.commit()
    other_id = db.execute(
        "SELECT id FROM watched_folders WHERE path='/other'"
    ).fetchone()["id"]

    insert_file("mine.txt", size=1000)
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (other_id, "/other/file.txt", "file.txt", ".txt", 2000, now, now, now),
    )
    db.commit()

    s = get_space_summary(db, folder_id=None)

    assert s.total_size_bytes == 3000
    assert s.total_files == 2


# ── get_duplicate_groups ──────────────────────────────────────────────────────

def test_get_duplicate_groups_empty_db(db):
    assert get_duplicate_groups(db) == []


def test_get_duplicate_groups_returns_group(db):
    _make_group(db, "abc123abc123abc123", 1000, count=2)
    groups = get_duplicate_groups(db)
    assert len(groups) == 1
    assert isinstance(groups[0], DuplicateGroup)


def test_get_duplicate_groups_sha256_truncated(db):
    sha = "a" * 32
    _make_group(db, sha, 500)
    groups = get_duplicate_groups(db)
    assert groups[0].sha256.endswith("...")
    assert len(groups[0].sha256) == 15


def test_get_duplicate_groups_wasted_bytes(db):
    _make_group(db, "sha_waste", 2000, count=2)
    groups = get_duplicate_groups(db)
    assert groups[0].wasted_bytes == 2000


def test_get_duplicate_groups_three_files(db):
    _make_group(db, "sha_three", 1000, count=3)
    groups = get_duplicate_groups(db)
    assert groups[0].file_count == 3
    assert groups[0].wasted_bytes == 2000
    assert len(groups[0].members) == 3


def test_get_duplicate_groups_members_are_paths(db):
    _make_group(db, "sha_paths", 100)
    groups = get_duplicate_groups(db)
    for m in groups[0].members:
        assert isinstance(m, Path)


def test_get_duplicate_groups_min_size_filter(db):
    _make_group(db, "small_sha", 100)
    assert get_duplicate_groups(db, min_size=500) == []
    assert len(get_duplicate_groups(db, min_size=50)) == 1


def test_get_duplicate_groups_limit(db):
    for i in range(5):
        _make_group(db, f"sha_{i:032}", 1000)
    groups = get_duplicate_groups(db, limit=3)
    assert len(groups) == 3


def test_get_duplicate_groups_sorted_by_wasted_desc(db):
    _make_group(db, f"{'a' * 32}", 100)
    _make_group(db, f"{'b' * 32}", 1000)
    _make_group(db, f"{'c' * 32}", 500)

    groups = get_duplicate_groups(db)
    wasted = [g.wasted_bytes for g in groups]
    assert wasted == sorted(wasted, reverse=True)


def test_get_duplicate_groups_folder_scope(db):
    now = time.time()
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/f1', ?)", (now,)
    )
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/f2', ?)", (now,)
    )
    db.commit()
    f1 = db.execute("SELECT id FROM watched_folders WHERE path='/f1'").fetchone()["id"]
    f2 = db.execute("SELECT id FROM watched_folders WHERE path='/f2'").fetchone()["id"]

    _make_group(db, "sha_f1_f1f1f1f1f1f1f1", 500, folder_id=f1)
    _make_group(db, "sha_f2_f2f2f2f2f2f2f2", 500, folder_id=f2)

    groups_f1 = get_duplicate_groups(db, folder_id=f1)
    groups_f2 = get_duplicate_groups(db, folder_id=f2)

    assert len(groups_f1) == 1
    assert len(groups_f2) == 1
    assert groups_f1[0].sha256 != groups_f2[0].sha256
