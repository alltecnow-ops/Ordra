import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from file_organizer.config import LARGE_FILE_THRESHOLD, OLD_FILE_DAYS, SORT_RULES


@dataclass
class Suggestion:
    category: str
    detail: str
    potential_bytes: int
    path: str | None


def run_suggestions(
    conn: sqlite3.Connection,
    folder_id: int | None = None,
) -> list[Suggestion]:
    conn.execute("DELETE FROM suggestions")
    now = time.time()
    results: list[Suggestion] = []

    results += _large_files(conn, now, folder_id)
    results += _old_files(conn, now, folder_id)
    results += _junk_files(conn, now, folder_id)
    results += _misplaced_files(conn, now, folder_id)

    conn.commit()
    return results


def _folder_clause(folder_id: int | None) -> tuple[str, list]:
    if folder_id is not None:
        return " AND folder_id = ?", [folder_id]
    return "", []


def _large_files(conn, now, folder_id):
    fc, fv = _folder_clause(folder_id)
    rows = conn.execute(
        f"SELECT id, path, size_bytes FROM files WHERE size_bytes >= ? AND is_junk = 0{fc} ORDER BY size_bytes DESC",
        [LARGE_FILE_THRESHOLD] + fv,
    ).fetchall()
    out = []
    for r in rows:
        detail = f"Large file: {_fmt(r['size_bytes'])}"
        conn.execute(
            "INSERT INTO suggestions (file_id, category, detail, potential_bytes, created_at) VALUES (?, ?, ?, ?, ?)",
            (r["id"], "large", detail, r["size_bytes"], now),
        )
        out.append(Suggestion("large", detail, r["size_bytes"], r["path"]))
    return out


def _old_files(conn, now, folder_id):
    cutoff = now - OLD_FILE_DAYS * 86400
    fc, fv = _folder_clause(folder_id)
    rows = conn.execute(
        f"SELECT id, path, size_bytes, mtime FROM files WHERE mtime < ? AND is_junk = 0{fc} ORDER BY mtime ASC LIMIT 100",
        [cutoff] + fv,
    ).fetchall()
    out = []
    for r in rows:
        days = int((now - r["mtime"]) / 86400)
        detail = f"Not modified in {days} days"
        conn.execute(
            "INSERT INTO suggestions (file_id, category, detail, potential_bytes, created_at) VALUES (?, ?, ?, ?, ?)",
            (r["id"], "old", detail, r["size_bytes"], now),
        )
        out.append(Suggestion("old", detail, r["size_bytes"], r["path"]))
    return out


def _junk_files(conn, now, folder_id):
    fc, fv = _folder_clause(folder_id)
    rows = conn.execute(
        f"SELECT id, path, size_bytes, junk_reason FROM files WHERE is_junk = 1{fc} ORDER BY size_bytes DESC",
        fv,
    ).fetchall()
    out = []
    for r in rows:
        detail = f"Junk file ({r['junk_reason']})"
        conn.execute(
            "INSERT INTO suggestions (file_id, category, detail, potential_bytes, created_at) VALUES (?, ?, ?, ?, ?)",
            (r["id"], "junk", detail, r["size_bytes"], now),
        )
        out.append(Suggestion("junk", detail, r["size_bytes"], r["path"]))
    return out


def _misplaced_files(conn, now, folder_id):
    ext_to_cat: dict[str, str] = {}
    for cat, exts in SORT_RULES.items():
        for ext in exts:
            ext_to_cat[ext] = cat

    fc, fv = _folder_clause(folder_id)
    rows = conn.execute(
        f"SELECT id, path, extension, size_bytes FROM files WHERE is_junk = 0{fc}",
        fv,
    ).fetchall()
    out = []
    for r in rows:
        cat = ext_to_cat.get(r["extension"])
        if not cat:
            continue
        path_lower = r["path"].lower()
        if cat.lower() not in path_lower:
            detail = f"Belongs in {cat} folder"
            conn.execute(
                "INSERT INTO suggestions (file_id, category, detail, potential_bytes, created_at) VALUES (?, ?, ?, ?, ?)",
                (r["id"], "misplaced", detail, 0, now),
            )
            out.append(Suggestion("misplaced", detail, 0, r["path"]))
    return out


def _fmt(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b //= 1024
    return f"{b:.1f} PB"
