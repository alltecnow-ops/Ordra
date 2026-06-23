import io
import time
from pathlib import Path

import pytest
from rich.console import Console

from file_organizer.config import JUNK_EXTENSIONS, JUNK_NAMES, JUNK_PREFIXES, SCAN_SKIP_DIRS
from file_organizer.services.scanner import ScanResult, _classify_junk, scan_folder


# ── _classify_junk ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expected_reason", [
    (".DS_Store",  "system file"),
    ("Thumbs.db",  "system file"),
    ("desktop.ini","system file"),
    (".localized", "system file"),
])
def test_classify_junk_by_exact_name(name, expected_reason):
    is_junk, reason = _classify_junk(Path(f"/any/{name}"))
    assert is_junk is True
    assert reason == expected_reason


@pytest.mark.parametrize("ext", sorted(JUNK_EXTENSIONS))
def test_classify_junk_by_extension(ext):
    is_junk, reason = _classify_junk(Path(f"/any/file{ext}"))
    assert is_junk is True
    assert ext in reason


@pytest.mark.parametrize("prefix", JUNK_PREFIXES)
def test_classify_junk_by_prefix(prefix):
    is_junk, reason = _classify_junk(Path(f"/any/{prefix}document.docx"))
    assert is_junk is True
    assert "temp" in reason.lower()


def test_classify_junk_normal_txt():
    is_junk, reason = _classify_junk(Path("/any/readme.txt"))
    assert is_junk is False
    assert reason is None


def test_classify_junk_normal_pdf():
    is_junk, reason = _classify_junk(Path("/any/report.pdf"))
    assert is_junk is False
    assert reason is None


def test_classify_junk_normal_jpg():
    is_junk, reason = _classify_junk(Path("/any/photo.jpg"))
    assert is_junk is False
    assert reason is None


def test_classify_junk_extension_case_insensitive():
    is_junk, reason = _classify_junk(Path("/any/file.TMP"))
    assert is_junk is True
    assert ".tmp" in reason


def test_classify_junk_returns_tuple():
    result = _classify_junk(Path("/any/file.txt"))
    assert isinstance(result, tuple)
    assert len(result) == 2


# ── scan_folder ───────────────────────────────────────────────────────────────

def _quiet_console():
    return Console(file=io.StringIO(), width=120)


def test_scan_folder_indexes_new_files(db, tmp_path):
    for name in ("a.txt", "b.jpg", "c.pdf"):
        (tmp_path / name).write_text("data")

    result = scan_folder(tmp_path, db, _quiet_console())

    assert isinstance(result, ScanResult)
    assert result.new == 3
    assert result.updated == 0
    assert result.deleted == 0
    assert result.total == 3


def test_scan_folder_marks_junk_files(db, tmp_path):
    (tmp_path / "Thumbs.db").write_bytes(b"")
    (tmp_path / "normal.txt").write_text("hello")

    scan_folder(tmp_path, db, _quiet_console())

    rows = {r["name"]: r for r in db.execute("SELECT name, is_junk, junk_reason FROM files")}
    assert rows["Thumbs.db"]["is_junk"] == 1
    assert rows["Thumbs.db"]["junk_reason"] == "system file"
    assert rows["normal.txt"]["is_junk"] == 0


def test_scan_folder_skips_scan_skip_dirs(db, tmp_path):
    skip_dir = tmp_path / "node_modules"
    skip_dir.mkdir()
    (skip_dir / "pkg.js").write_text("module")
    (tmp_path / "real.txt").write_text("real")

    scan_folder(tmp_path, db, _quiet_console())

    paths = [r["path"] for r in db.execute("SELECT path FROM files")]
    assert not any("node_modules" in p for p in paths)
    assert any("real.txt" in p for p in paths)


@pytest.mark.parametrize("skip_dir_name", sorted(SCAN_SKIP_DIRS)[:5])
def test_scan_folder_known_skip_dirs_not_indexed(db, tmp_path, skip_dir_name):
    d = tmp_path / skip_dir_name
    d.mkdir()
    (d / "file.txt").write_text("skip me")

    scan_folder(tmp_path, db, _quiet_console())

    paths = [r["path"] for r in db.execute("SELECT path FROM files")]
    assert not any(skip_dir_name in p for p in paths)


def test_scan_folder_incremental_unchanged_skipped(db, tmp_path):
    (tmp_path / "file.txt").write_text("hello")

    first = scan_folder(tmp_path, db, _quiet_console())
    assert first.new == 1

    second = scan_folder(tmp_path, db, _quiet_console())
    assert second.new == 0
    assert second.skipped == 1
    assert second.updated == 0


def test_scan_folder_incremental_detects_updated_file(db, tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("original")
    scan_folder(tmp_path, db, _quiet_console())

    f.write_bytes(b"x" * 9999)
    second = scan_folder(tmp_path, db, _quiet_console())

    assert second.updated == 1
    sha256_val = db.execute("SELECT sha256 FROM files WHERE name='file.txt'").fetchone()["sha256"]
    assert sha256_val is None


def test_scan_folder_incremental_detects_deleted_file(db, tmp_path):
    f = tmp_path / "will_delete.txt"
    f.write_text("bye")
    scan_folder(tmp_path, db, _quiet_console())

    f.unlink()
    second = scan_folder(tmp_path, db, _quiet_console())

    assert second.deleted == 1
    count = db.execute("SELECT COUNT(*) FROM files WHERE name='will_delete.txt'").fetchone()[0]
    assert count == 0


def test_scan_folder_updates_last_scan_timestamp(db, tmp_path):
    (tmp_path / "file.txt").write_text("x")
    before = time.time()
    scan_folder(tmp_path, db, _quiet_console())

    row = db.execute("SELECT last_scan FROM watched_folders").fetchone()
    assert row["last_scan"] is not None
    assert row["last_scan"] >= before


def test_scan_folder_empty_directory(db, tmp_path):
    result = scan_folder(tmp_path, db, _quiet_console())

    assert result.new == 0
    assert result.total == 0


def test_scan_folder_nested_subdirectories(db, tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (tmp_path / "root.txt").write_text("root")
    (tmp_path / "a" / "mid.txt").write_text("mid")
    (deep / "deep.txt").write_text("deep")

    result = scan_folder(tmp_path, db, _quiet_console())

    assert result.new == 3
