import time

import pytest

from file_organizer.config import LARGE_FILE_THRESHOLD, OLD_FILE_DAYS
from file_organizer.services.suggestions import _fmt, _folder_clause, run_suggestions


# ── _fmt ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("b,expected", [
    (0,              "0.0 B"),
    (1,              "1.0 B"),
    (1023,           "1023.0 B"),
    (1024,           "1.0 KB"),
    (1025,           "1.0 KB"),
    (1023 * 1024,    "1023.0 KB"),
    (1024 * 1024,    "1.0 MB"),
    (1024 ** 3,      "1.0 GB"),
    (1024 ** 4,      "1.0 TB"),
    (1024 ** 5,      "1.0 PB"),
])
def test_fmt_boundaries(b, expected):
    assert _fmt(b) == expected


# ── _folder_clause ────────────────────────────────────────────────────────────

def test_folder_clause_none_returns_empty():
    clause, params = _folder_clause(None)
    assert clause == ""
    assert params == []


def test_folder_clause_with_id_returns_clause():
    clause, params = _folder_clause(42)
    assert clause == " AND folder_id = ?"
    assert params == [42]


def test_folder_clause_zero_is_not_none():
    clause, params = _folder_clause(0)
    assert clause == " AND folder_id = ?"
    assert params == [0]


# ── run_suggestions — large files ─────────────────────────────────────────────

def test_run_suggestions_empty_db(db):
    assert run_suggestions(db) == []


def test_large_file_exactly_at_threshold(db, insert_file):
    insert_file("big.bin", ext=".bin", size=LARGE_FILE_THRESHOLD)
    suggestions = run_suggestions(db)
    large = [s for s in suggestions if s.category == "large"]
    assert len(large) == 1


def test_large_file_one_byte_below_threshold(db, insert_file):
    insert_file("almost.bin", ext=".bin", size=LARGE_FILE_THRESHOLD - 1)
    suggestions = run_suggestions(db)
    assert not any(s.category == "large" for s in suggestions)


def test_large_file_excludes_junk(db, insert_file):
    insert_file("junk.tmp", ext=".tmp", size=LARGE_FILE_THRESHOLD + 1,
                is_junk=1, junk_reason="temp")
    suggestions = run_suggestions(db)
    assert not any(s.category == "large" for s in suggestions)


def test_large_file_potential_bytes_correct(db, insert_file):
    insert_file("huge.bin", ext=".bin", size=LARGE_FILE_THRESHOLD + 500)
    large = [s for s in run_suggestions(db) if s.category == "large"]
    assert large[0].potential_bytes == LARGE_FILE_THRESHOLD + 500


# ── run_suggestions — old files ───────────────────────────────────────────────

def test_old_file_366_days_included(db, insert_file):
    old_mtime = time.time() - (OLD_FILE_DAYS + 1) * 86400
    insert_file("ancient.doc", ext=".doc", mtime=old_mtime)
    old = [s for s in run_suggestions(db) if s.category == "old"]
    assert len(old) == 1


def test_old_file_364_days_excluded(db, insert_file):
    recent_mtime = time.time() - (OLD_FILE_DAYS - 1) * 86400
    insert_file("recent.doc", ext=".doc", mtime=recent_mtime)
    old = [s for s in run_suggestions(db) if s.category == "old"]
    assert len(old) == 0


def test_old_file_detail_contains_days(db, insert_file):
    old_mtime = time.time() - (OLD_FILE_DAYS + 50) * 86400
    insert_file("old.txt", ext=".txt", mtime=old_mtime)
    old = [s for s in run_suggestions(db) if s.category == "old"]
    assert "days" in old[0].detail


def test_old_files_limited_to_100(db, folder_id):
    old_mtime = time.time() - (OLD_FILE_DAYS + 10) * 86400
    now = time.time()
    db.executemany(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        [
            (folder_id, f"/watched/old_{i}.txt", f"old_{i}.txt", ".txt",
             100, old_mtime, now, now)
            for i in range(150)
        ],
    )
    db.commit()

    old = [s for s in run_suggestions(db) if s.category == "old"]
    assert len(old) == 100


# ── run_suggestions — junk files ─────────────────────────────────────────────

def test_junk_files_returned(db, insert_file):
    insert_file("Thumbs.db", ext="", is_junk=1, junk_reason="system file")
    junk = [s for s in run_suggestions(db) if s.category == "junk"]
    assert len(junk) == 1
    assert "system file" in junk[0].detail


def test_junk_excluded_from_large_category(db, insert_file):
    insert_file("big_junk.tmp", ext=".tmp", size=LARGE_FILE_THRESHOLD + 1,
                is_junk=1, junk_reason="temp")
    suggestions = run_suggestions(db)
    assert not any(s.category == "large" for s in suggestions)
    assert any(s.category == "junk" for s in suggestions)


# ── run_suggestions — misplaced files ────────────────────────────────────────

def test_misplaced_jpg_not_in_images_path(db, insert_file):
    insert_file("photo.jpg", ext=".jpg", path="/downloads/photo.jpg")
    misplaced = [s for s in run_suggestions(db) if s.category == "misplaced"]
    assert len(misplaced) == 1
    assert "Images" in misplaced[0].detail


def test_jpg_in_images_path_not_flagged(db, insert_file):
    insert_file("photo.jpg", ext=".jpg", path="/downloads/images/photo.jpg")
    misplaced = [s for s in run_suggestions(db) if s.category == "misplaced"]
    assert len(misplaced) == 0


def test_unknown_ext_not_flagged_as_misplaced(db, insert_file):
    insert_file("data.xyz", ext=".xyz", path="/downloads/data.xyz")
    misplaced = [s for s in run_suggestions(db) if s.category == "misplaced"]
    assert len(misplaced) == 0


def test_misplaced_potential_bytes_is_zero(db, insert_file):
    insert_file("song.mp3", ext=".mp3", path="/downloads/song.mp3", size=5_000_000)
    misplaced = [s for s in run_suggestions(db) if s.category == "misplaced"]
    assert misplaced[0].potential_bytes == 0


# ── run_suggestions — clears and stores ──────────────────────────────────────

def test_run_suggestions_clears_old_suggestions(db, insert_file):
    insert_file("big.bin", ext=".bin", size=LARGE_FILE_THRESHOLD + 1)
    run_suggestions(db)
    run_suggestions(db)

    count = db.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0]
    assert count == 1


def test_run_suggestions_inserts_to_db(db, insert_file):
    insert_file("big.bin", ext=".bin", size=LARGE_FILE_THRESHOLD + 1)
    suggestions = run_suggestions(db)

    rows = db.execute("SELECT * FROM suggestions").fetchall()
    assert len(rows) == len(suggestions)


# ── folder scoping ────────────────────────────────────────────────────────────

def test_run_suggestions_folder_id_filter(db, folder_id):
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
        (folder_id, "/watched/big.bin", "big.bin", ".bin",
         LARGE_FILE_THRESHOLD + 1, now, now, now),
    )
    db.execute(
        """INSERT INTO files (folder_id, path, name, extension, size_bytes, mtime,
           is_junk, created_at, updated_at) VALUES (?,?,?,?,?,?,0,?,?)""",
        (other_id, "/other/big.bin", "big.bin", ".bin",
         LARGE_FILE_THRESHOLD + 1, now, now, now),
    )
    db.commit()

    suggestions = run_suggestions(db, folder_id=folder_id)
    paths = [s.path for s in suggestions if s.path]

    assert all("/watched/" in p for p in paths)
    assert not any("/other/" in p for p in paths)
