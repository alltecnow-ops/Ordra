import time
from pathlib import Path

import pytest

from file_organizer.services.sorter import (
    SortAction,
    _is_protected,
    _resolve_collision,
    build_sort_plan,
    execute_sort_plan,
)


# ── _is_protected ────────────────────────────────────────────────────────────

def test_sorter_is_protected_allows_normal():
    assert _is_protected(Path("/home/user/Downloads/file.zip")) is False


def test_sorter_is_protected_blocks_windows():
    assert _is_protected(Path("C:/Windows/System32/ntdll.dll")) is True


def test_sorter_is_protected_blocks_appdata():
    assert _is_protected(Path("C:/Users/user/AppData/Local/app.exe")) is True


def test_sorter_is_protected_blocks_git():
    assert _is_protected(Path("/home/user/project/.git/objects/abc")) is True


def test_sorter_is_protected_blocks_svn():
    assert _is_protected(Path("/repo/.svn/pristine/file")) is True


def test_sorter_is_protected_blocks_node_modules():
    assert _is_protected(Path("/app/node_modules/lib/index.js")) is True


def test_sorter_is_protected_case_insensitive():
    assert _is_protected(Path("C:/WINDOWS/System32")) is True


# ── _resolve_collision ────────────────────────────────────────────────────────

def test_resolve_collision_no_conflict():
    dest = Path("/out/Images/photo.jpg")
    result = _resolve_collision(dest, set())
    assert result == dest


def test_resolve_collision_one_conflict():
    dest = Path("/out/Images/photo.jpg")
    used = {dest.as_posix()}
    result = _resolve_collision(dest, used)
    assert result.name == "photo_1.jpg"
    assert result.parent == dest.parent


def test_resolve_collision_two_conflicts():
    dest = Path("/out/Images/photo.jpg")
    used = {dest.as_posix(), "/out/Images/photo_1.jpg"}
    result = _resolve_collision(dest, used)
    assert result.name == "photo_2.jpg"


def test_resolve_collision_preserves_extension():
    dest = Path("/out/Docs/archive.tar.gz")
    used = {dest.as_posix()}
    result = _resolve_collision(dest, used)
    assert result.suffix == ".gz"
    assert result.name == "archive.tar_1.gz"


def test_resolve_collision_no_extension():
    dest = Path("/out/Other/README")
    used = {dest.as_posix()}
    result = _resolve_collision(dest, used)
    assert result.name == "README_1"


@pytest.mark.parametrize("n", [1, 3, 5])
def test_resolve_collision_sequential_numbering(n):
    dest = Path("/out/Images/photo.jpg")
    used = {dest.as_posix()}
    for i in range(1, n):
        used.add(f"/out/Images/photo_{i}.jpg")
    result = _resolve_collision(dest, used)
    assert result.name == f"photo_{n}.jpg"


# ── build_sort_plan ───────────────────────────────────────────────────────────

def test_build_sort_plan_empty_db(db, tmp_path):
    actions = build_sort_plan(db, tmp_path / "out")
    assert actions == []


@pytest.mark.parametrize("ext,expected_cat", [
    (".jpg",  "Images"),
    (".mp4",  "Videos"),
    (".mp3",  "Audio"),
    (".pdf",  "Documents"),
    (".zip",  "Archives"),
    (".py",   "Code"),
    (".exe",  "Installers"),
    (".ttf",  "Fonts"),
    (".csv",  "Data"),
])
def test_build_sort_plan_extension_to_category(db, folder_id, ext, expected_cat, tmp_path):
    name = f"file{ext}"
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, f"/watched/{name}", name, ext, 1000, time.time(), time.time(), time.time()),
    )
    db.commit()

    actions = build_sort_plan(db, tmp_path / "out", folder_id)

    assert len(actions) == 1
    assert actions[0].category == expected_cat


def test_build_sort_plan_unknown_ext_goes_to_other(db, folder_id, tmp_path):
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/weird.xyz", "weird.xyz", ".xyz", 1000, time.time(), time.time(), time.time()),
    )
    db.commit()

    actions = build_sort_plan(db, tmp_path / "out", folder_id)

    assert len(actions) == 1
    assert actions[0].category == "Other"


def test_build_sort_plan_junk_files_excluded(db, folder_id, tmp_path):
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)""",
        (folder_id, "/watched/file.tmp", "file.tmp", ".tmp", 100, time.time(), time.time(), time.time()),
    )
    db.commit()

    actions = build_sort_plan(db, tmp_path / "out", folder_id)

    assert actions == []


def test_build_sort_plan_skips_protected_source(db, folder_id, tmp_path):
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, "C:/Windows/file.jpg", "file.jpg", ".jpg", 1000, time.time(), time.time(), time.time()),
    )
    db.commit()

    actions = build_sort_plan(db, tmp_path / "out", folder_id)

    assert actions == []


def test_build_sort_plan_skips_already_sorted(db, folder_id, tmp_path):
    base_out = tmp_path / "out"
    already_sorted = str(base_out / "Images" / "photo.jpg")
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, already_sorted, "photo.jpg", ".jpg", 1000, time.time(), time.time(), time.time()),
    )
    db.commit()

    actions = build_sort_plan(db, base_out, folder_id)

    assert actions == []


def test_build_sort_plan_resolves_name_collision(db, folder_id, tmp_path):
    now = time.time()
    for i in range(2):
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
            (folder_id, f"/watched/dir{i}/photo.jpg", "photo.jpg", ".jpg", 1000, now, now, now),
        )
    db.commit()

    actions = build_sort_plan(db, tmp_path / "out", folder_id)

    dest_names = {a.destination.name for a in actions}
    assert len(dest_names) == 2


def test_build_sort_plan_writes_sort_plan_table(db, folder_id, tmp_path):
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/doc.pdf", "doc.pdf", ".pdf", 1000, time.time(), time.time(), time.time()),
    )
    db.commit()

    build_sort_plan(db, tmp_path / "out", folder_id)

    rows = db.execute("SELECT * FROM sort_plan").fetchall()
    assert len(rows) == 1
    assert rows[0]["category"] == "Documents"


def test_build_sort_plan_clears_old_sort_plan(db, folder_id, tmp_path):
    now = time.time()
    db.execute(
        "INSERT INTO sort_plan (source_path, destination_path, category, created_at) VALUES (?,?,?,?)",
        ("/stale/path", "/stale/dest", "Old", now),
    )
    db.commit()

    build_sort_plan(db, tmp_path / "out", folder_id)

    rows = db.execute("SELECT * FROM sort_plan WHERE source_path='/stale/path'").fetchall()
    assert len(rows) == 0


def test_build_sort_plan_folder_id_filter(db, folder_id, tmp_path):
    now = time.time()
    db.execute(
        "INSERT INTO watched_folders (path, added_at) VALUES ('/other', ?)", (now,)
    )
    db.commit()
    other_id = db.execute(
        "SELECT id FROM watched_folders WHERE path='/other'"
    ).fetchone()["id"]

    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, "/watched/img.jpg", "img.jpg", ".jpg", 1000, now, now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (other_id, "/other/img.jpg", "img.jpg", ".jpg", 1000, now, now, now),
    )
    db.commit()

    actions = build_sort_plan(db, tmp_path / "out", folder_id)

    assert len(actions) == 1
    assert "/watched/" in actions[0].source.as_posix()


# ── execute_sort_plan ─────────────────────────────────────────────────────────

def test_execute_sort_plan_empty_actions(db):
    moved, errors = execute_sort_plan([], db)
    assert moved == 0
    assert errors == []


def test_execute_sort_plan_moves_file(db, folder_id, tmp_path):
    src = tmp_path / "src" / "photo.jpg"
    src.parent.mkdir()
    src.write_bytes(b"JPEG")
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(src), "photo.jpg", ".jpg", 4, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    dest = tmp_path / "out" / "Images" / "photo.jpg"
    action = SortAction(file_id=file_id, source=src, destination=dest, category="Images")

    moved, errors = execute_sort_plan([action], db)

    assert moved == 1
    assert errors == []
    assert dest.exists()
    assert not src.exists()


def test_execute_sort_plan_updates_db_path(db, folder_id, tmp_path):
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"PDF")
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(src), "doc.pdf", ".pdf", 3, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    dest = tmp_path / "out" / "Documents" / "doc.pdf"
    action = SortAction(file_id=file_id, source=src, destination=dest, category="Documents")
    execute_sort_plan([action], db)

    row = db.execute("SELECT path, name FROM files WHERE id=?", (file_id,)).fetchone()
    assert row["path"] == dest.as_posix()
    assert row["name"] == "doc.pdf"


def test_execute_sort_plan_creates_parent_dirs(db, folder_id, tmp_path):
    src = tmp_path / "file.txt"
    src.write_bytes(b"text")
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(src), "file.txt", ".txt", 4, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    deep_dest = tmp_path / "a" / "b" / "c" / "file.txt"
    action = SortAction(file_id=file_id, source=src, destination=deep_dest, category="Other")
    moved, errors = execute_sort_plan([action], db)

    assert moved == 1
    assert deep_dest.exists()


def test_execute_sort_plan_missing_source_is_error(db, folder_id, tmp_path):
    ghost = tmp_path / "ghost.jpg"
    now = time.time()
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (folder_id, str(ghost), "ghost.jpg", ".jpg", 100, now, now, now),
    )
    db.commit()
    file_id = db.execute("SELECT id FROM files").fetchone()["id"]

    dest = tmp_path / "out" / "Images" / "ghost.jpg"
    action = SortAction(file_id=file_id, source=ghost, destination=dest, category="Images")
    moved, errors = execute_sort_plan([action], db)

    assert moved == 0
    assert len(errors) == 1
    assert "source not found" in errors[0]


def test_execute_sort_plan_multiple_files(db, folder_id, tmp_path):
    now = time.time()
    actions = []
    for i in range(3):
        src = tmp_path / f"file{i}.jpg"
        src.write_bytes(b"x")
        db.execute(
            """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
               is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
            (folder_id, str(src), f"file{i}.jpg", ".jpg", 1, now, now, now),
        )
        db.commit()
        file_id = db.execute("SELECT id FROM files WHERE path=?", (str(src),)).fetchone()["id"]
        dest = tmp_path / "out" / "Images" / f"file{i}.jpg"
        actions.append(SortAction(file_id=file_id, source=src, destination=dest, category="Images"))

    moved, errors = execute_sort_plan(actions, db)

    assert moved == 3
    assert errors == []
