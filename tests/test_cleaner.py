import time
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.cleaner import (
    CleanItem,
    INSTALLER_EXTENSIONS,
    OLD_DAYS,
    _is_protected,
    execute_deletions,
    plan_dupe_deletions,
    plan_old_installer_deletions,
)


# ── _is_protected ────────────────────────────────────────────────────────────

def test_is_protected_allows_downloads():
    assert _is_protected(Path("/home/user/Downloads/photo.jpg")) is False


def test_is_protected_allows_documents():
    assert _is_protected(Path("/home/user/Documents/report.pdf")) is False


def test_is_protected_blocks_windows():
    assert _is_protected(Path("C:/Windows/System32/cmd.exe")) is True


def test_is_protected_blocks_appdata():
    assert _is_protected(Path("C:/Users/user/AppData/Roaming/x.exe")) is True


def test_is_protected_blocks_git():
    assert _is_protected(Path("/home/user/repo/.git/config")) is True


def test_is_protected_blocks_node_modules():
    assert _is_protected(Path("/app/node_modules/pkg/index.js")) is True


def test_is_protected_blocks_pycache():
    assert _is_protected(Path("/project/__pycache__/module.cpython.pyc")) is True


def test_is_protected_blocks_site_packages():
    assert _is_protected(Path("/usr/lib/python3/site-packages/pkg/mod.py")) is True


def test_is_protected_case_insensitive_appdata():
    assert _is_protected(Path("/home/user/APPDATA/file.txt")) is True


def test_is_protected_case_insensitive_windows():
    assert _is_protected(Path("C:/WINDOWS/System32")) is True


# ── plan_dupe_deletions ───────────────────────────────────────────────────────

def test_plan_dupe_deletions_empty_db(db):
    result = plan_dupe_deletions(db)
    assert result == []


def test_plan_dupe_deletions_no_duplicate_groups(db, insert_file):
    insert_file("a.txt", sha256="aaa")
    insert_file("b.txt", sha256="bbb")
    result = plan_dupe_deletions(db)
    assert result == []


def test_plan_dupe_deletions_keeps_original_deletes_numbered(db, insert_file, build_duplicate_groups):
    now = time.time()
    insert_file("report.pdf", ext=".pdf", sha256="sha1", mtime=now - 100)
    insert_file("report (1).pdf", ext=".pdf", sha256="sha1", mtime=now,
                path="/watched/report (1).pdf")
    build_duplicate_groups()

    items = plan_dupe_deletions(db)

    assert len(items) == 1
    assert items[0].path.name == "report (1).pdf"
    assert "report.pdf" in items[0].reason


def test_plan_dupe_deletions_keeps_original_deletes_underscore_num(db, insert_file, build_duplicate_groups):
    now = time.time()
    insert_file("photo.jpg", ext=".jpg", sha256="sha2", mtime=now - 100)
    insert_file("photo_1.jpg", ext=".jpg", sha256="sha2", mtime=now,
                path="/watched/photo_1.jpg")
    build_duplicate_groups()

    items = plan_dupe_deletions(db)

    assert len(items) == 1
    assert items[0].path.name == "photo_1.jpg"


def test_plan_dupe_deletions_keeps_original_deletes_copy_keyword(db, insert_file, build_duplicate_groups):
    now = time.time()
    insert_file("data.csv", ext=".csv", sha256="sha3", mtime=now - 100)
    insert_file("data copy.csv", ext=".csv", sha256="sha3", mtime=now,
                path="/watched/data copy.csv")
    build_duplicate_groups()

    items = plan_dupe_deletions(db)

    assert len(items) == 1
    assert items[0].path.name == "data copy.csv"


def test_plan_dupe_deletions_keeps_original_deletes_backup_keyword(db, insert_file, build_duplicate_groups):
    now = time.time()
    insert_file("file.txt", ext=".txt", sha256="sha4", mtime=now - 100)
    insert_file("file_backup.txt", ext=".txt", sha256="sha4", mtime=now,
                path="/watched/file_backup.txt")
    build_duplicate_groups()

    items = plan_dupe_deletions(db)

    assert len(items) == 1
    assert items[0].path.name == "file_backup.txt"


@pytest.mark.parametrize("dupe_name", [
    "photo (1).jpg",
    "photo (2).jpg",
    "photo_1.jpg",
    "photo-1.jpg",
    "photo copy.jpg",
    "photo_backup.jpg",
    "photo_duplicate.jpg",
])
def test_plan_dupe_penalized_names_are_deleted(db, folder_id, dupe_name, build_duplicate_groups):
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/photo.jpg", "photo.jpg", ".jpg", 500, now - 200,
         "dupsha", now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (folder_id, f"/watched/{dupe_name}", dupe_name, ".jpg", 500, now,
         "dupsha", now, now),
    )
    db.commit()
    build_duplicate_groups()

    items = plan_dupe_deletions(db)

    deleted_names = [item.path.name for item in items]
    assert dupe_name in deleted_names
    assert "photo.jpg" not in deleted_names


def test_plan_dupe_deletions_three_members_two_deleted(db, folder_id, build_duplicate_groups):
    now = time.time()
    for i, (name, dt) in enumerate([("doc.pdf", 200), ("doc copy.pdf", 100), ("doc (1).pdf", 0)]):
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
            (folder_id, f"/watched/{name}", name, ".pdf", 1000, now - dt,
             "trisha", now, now),
        )
    db.commit()
    build_duplicate_groups()

    items = plan_dupe_deletions(db)

    assert len(items) == 2
    deleted_names = {item.path.name for item in items}
    assert "doc copy.pdf" in deleted_names
    assert "doc (1).pdf" in deleted_names
    assert "doc.pdf" not in deleted_names


def test_plan_dupe_deletions_skips_protected_member(db, folder_id, build_duplicate_groups):
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/file.pdf", "file.pdf", ".pdf", 500, now - 100,
         "protsha", now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (folder_id, "C:/Windows/file.pdf", "file.pdf", ".pdf", 500, now,
         "protsha", now, now),
    )
    db.commit()
    build_duplicate_groups()

    items = plan_dupe_deletions(db)

    for item in items:
        assert "windows" not in item.path.as_posix().lower()


def test_plan_dupe_deletions_single_member_group_skipped(db, insert_file):
    insert_file("only.txt", sha256="lone")
    db.execute(
        "INSERT INTO duplicate_groups (sha256, file_count, total_size, wasted) VALUES ('lone', 1, 1000, 0)"
    )
    gid = db.execute("SELECT id FROM duplicate_groups").fetchone()["id"]
    fid = db.execute("SELECT id FROM files").fetchone()["id"]
    db.execute("INSERT INTO duplicate_members (group_id, file_id) VALUES (?, ?)", (gid, fid))
    db.commit()

    items = plan_dupe_deletions(db)

    assert items == []


def test_plan_dupe_deletions_folder_id_scope(db, folder_id, build_duplicate_groups):
    now = time.time()
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/other', ?)", (now,)
    )
    db.commit()
    other_fid = db.execute(
        "SELECT id FROM watched_folders WHERE path='/other'"
    ).fetchone()["id"]

    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/a.txt", "a.txt", ".txt", 100, now - 10, "s1", now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/a (1).txt", "a (1).txt", ".txt", 100, now, "s1", now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (other_fid, "/other/b.txt", "b.txt", ".txt", 100, now - 10, "s2", now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
        (other_fid, "/other/b (1).txt", "b (1).txt", ".txt", 100, now, "s2", now, now),
    )
    db.commit()
    build_duplicate_groups()

    items = plan_dupe_deletions(db, folder_id=folder_id)

    paths = [item.path.as_posix() for item in items]
    assert all("/watched/" in p for p in paths)
    assert not any("/other/" in p for p in paths)


# ── plan_old_installer_deletions ─────────────────────────────────────────────

def test_plan_old_installer_deletions_empty_db(db):
    assert plan_old_installer_deletions(db) == []


def test_plan_old_installer_deletions_finds_old_exe(db, insert_file):
    old_mtime = time.time() - (OLD_DAYS + 10) * 86400
    insert_file("setup.exe", ext=".exe", size=5_000_000, mtime=old_mtime)

    items = plan_old_installer_deletions(db)

    assert len(items) == 1
    assert items[0].path.name == "setup.exe"
    assert "days" in items[0].reason


def test_plan_old_installer_deletions_ignores_recent_exe(db, insert_file):
    recent_mtime = time.time() - 10 * 86400
    insert_file("setup.exe", ext=".exe", mtime=recent_mtime)

    assert plan_old_installer_deletions(db) == []


def test_plan_old_installer_deletions_ignores_non_installer_ext(db, insert_file):
    old_mtime = time.time() - (OLD_DAYS + 10) * 86400
    insert_file("readme.txt", ext=".txt", mtime=old_mtime)

    assert plan_old_installer_deletions(db) == []


def test_plan_old_installer_deletions_ignores_junk_files(db, insert_file):
    old_mtime = time.time() - (OLD_DAYS + 10) * 86400
    insert_file("setup.exe", ext=".exe", mtime=old_mtime, is_junk=1, junk_reason="junk")

    assert plan_old_installer_deletions(db) == []


def test_plan_old_installer_deletions_skips_protected(db, insert_file):
    old_mtime = time.time() - (OLD_DAYS + 10) * 86400
    insert_file("setup.msi", ext=".msi", mtime=old_mtime,
                path="C:/Windows/setup.msi")

    items = plan_old_installer_deletions(db)

    assert items == []


@pytest.mark.parametrize("ext", sorted(INSTALLER_EXTENSIONS))
def test_plan_old_installer_deletions_all_extensions(db, folder_id, ext):
    old_mtime = time.time() - (OLD_DAYS + 30) * 86400
    name = f"installer{ext}"
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, f"/watched/{name}", name, ext, 1000, old_mtime,
         time.time(), time.time()),
    )
    db.commit()

    items = plan_old_installer_deletions(db)

    assert len(items) == 1
    assert items[0].path.suffix == ext


def test_plan_old_installer_deletions_custom_days(db, folder_id):
    now = time.time()
    old_mtime = now - 100 * 86400
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/setup.exe", "setup.exe", ".exe", 1000, old_mtime,
         now, now),
    )
    db.commit()

    assert len(plan_old_installer_deletions(db, days=90)) == 1
    assert plan_old_installer_deletions(db, days=110) == []


def test_plan_old_installer_deletions_folder_scope(db, folder_id):
    now = time.time()
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/other', ?)", (now,)
    )
    db.commit()
    other_id = db.execute(
        "SELECT id FROM watched_folders WHERE path='/other'"
    ).fetchone()["id"]

    old_mtime = now - (OLD_DAYS + 20) * 86400

    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/setup.exe", "setup.exe", ".exe", 1000, old_mtime, now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (other_id, "/other/setup.exe", "setup.exe", ".exe", 1000, old_mtime, now, now),
    )
    db.commit()

    items = plan_old_installer_deletions(db, folder_id=folder_id)

    assert len(items) == 1
    assert "/watched/" in items[0].path.as_posix()


# ── execute_deletions ─────────────────────────────────────────────────────────

def test_execute_deletions_empty_list(db):
    deleted, freed, errors = execute_deletions([], db)
    assert deleted == 0
    assert freed == 0
    assert errors == []


def test_execute_deletions_calls_send2trash(db, folder_id, tmp_path):
    real_file = tmp_path / "dup.pdf"
    real_file.write_bytes(b"data")
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(real_file), "dup.pdf", ".pdf", 4, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    item = CleanItem(path=real_file, reason="Duplicate", size_bytes=4, file_id=file_id)

    with patch("send2trash.send2trash") as mock_trash:
        deleted, freed, errors = execute_deletions([item], db)

    mock_trash.assert_called_once_with(str(real_file))
    assert deleted == 1
    assert freed == 4
    assert errors == []


def test_execute_deletions_removes_file_from_db(db, folder_id, tmp_path):
    real_file = tmp_path / "junk.txt"
    real_file.write_bytes(b"x")
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(real_file), "junk.txt", ".txt", 1, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    item = CleanItem(path=real_file, reason="test", size_bytes=1, file_id=file_id)

    with patch("send2trash.send2trash"):
        execute_deletions([item], db)

    remaining = db.execute("SELECT * FROM files").fetchall()
    assert len(remaining) == 0


def test_execute_deletions_missing_file_still_cleans_db(db, folder_id, tmp_path):
    ghost = tmp_path / "ghost.txt"
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(ghost), "ghost.txt", ".txt", 100, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    item = CleanItem(path=ghost, reason="test", size_bytes=100, file_id=file_id)

    with patch("send2trash.send2trash") as mock_trash:
        deleted, freed, errors = execute_deletions([item], db)

    mock_trash.assert_not_called()
    assert deleted == 0
    assert freed == 0
    assert errors == []
    assert db.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0


def test_execute_deletions_handles_send2trash_error(db, folder_id, tmp_path):
    real_file = tmp_path / "locked.txt"
    real_file.write_bytes(b"locked")
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(real_file), "locked.txt", ".txt", 6, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    item = CleanItem(path=real_file, reason="test", size_bytes=6, file_id=file_id)

    with patch("send2trash.send2trash", side_effect=OSError("permission denied")):
        deleted, freed, errors = execute_deletions([item], db)

    assert deleted == 0
    assert freed == 0
    assert len(errors) == 1
    assert "permission denied" in errors[0]
    assert db.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1


def test_execute_deletions_rebuilds_duplicate_groups(db, folder_id, tmp_path):
    now = time.time()
    f1 = tmp_path / "orig.jpg"
    f1.write_bytes(b"img")
    f2 = tmp_path / "orig (1).jpg"
    f2.write_bytes(b"img")

    for path, name in [(f1, "orig.jpg"), (f2, "orig (1).jpg")]:
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               sha256, is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,?,0,?,?)""",
            (folder_id, str(path), name, ".jpg", 3, now, "imgsha", now, now),
        )
    db.commit()

    db.execute(
        "INSERT INTO duplicate_groups (sha256, file_count, total_size, wasted) VALUES ('imgsha', 2, 6, 3)"
    )
    gid = db.execute("SELECT id FROM duplicate_groups").fetchone()["id"]
    for row in db.execute("SELECT id FROM files"):
        db.execute("INSERT INTO duplicate_members (group_id, file_id) VALUES (?,?)", (gid, row["id"]))
    db.commit()

    dup_id = db.execute("SELECT id FROM files WHERE name='orig (1).jpg'").fetchone()["id"]
    item = CleanItem(path=f2, reason="Duplicate", size_bytes=3, file_id=dup_id)

    with patch("send2trash.send2trash"):
        execute_deletions([item], db)

    groups = db.execute("SELECT * FROM duplicate_groups").fetchall()
    assert len(groups) == 0
