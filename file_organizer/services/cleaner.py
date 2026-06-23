import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from file_organizer.config import PROTECTED_PATH_SEGMENTS

INSTALLER_EXTENSIONS = {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm"}

_PROTECTED_NFC = {unicodedata.normalize("NFC", p) for p in PROTECTED_PATH_SEGMENTS}


def _is_protected(path: Path) -> bool:
    """Return True if any segment of the path matches a protected directory name."""
    parts = {unicodedata.normalize("NFC", p.lower()) for p in path.parts}
    return bool(parts & _PROTECTED_NFC)
OLD_DAYS = 180  # files not touched in 6 months

# Pattern: filename (1).ext, filename (2).ext, filename-1.ext, filename_1.ext
_DUPE_SUFFIX = re.compile(r"^(.+?)[\s._-]\(?\d+\)?(\.[^.]+)?$")


@dataclass
class CleanItem:
    path: Path
    reason: str
    size_bytes: int
    file_id: int


def plan_dupe_deletions(
    conn: sqlite3.Connection,
    folder_id: int | None = None,
) -> list[CleanItem]:
    """For each duplicate group, pick the copy to DELETE and return it."""
    if folder_id is not None:
        groups = conn.execute(
            """SELECT DISTINCT dg.id, dg.sha256 FROM duplicate_groups dg
               JOIN duplicate_members dm ON dm.group_id = dg.id
               JOIN files f ON f.id = dm.file_id
               WHERE f.folder_id = ?""",
            (folder_id,),
        ).fetchall()
    else:
        groups = conn.execute(
            """SELECT dg.id, dg.sha256 FROM duplicate_groups dg"""
        ).fetchall()

    to_delete: list[CleanItem] = []

    for g in groups:
        members = conn.execute(
            """SELECT f.id, f.path, f.name, f.size_bytes, f.mtime
               FROM duplicate_members dm
               JOIN files f ON f.id = dm.file_id
               WHERE dm.group_id = ?
               ORDER BY f.mtime ASC""",
            (g["id"],),
        ).fetchall()

        if len(members) < 2:
            continue

        # Score each member — lower score = more likely to be the original
        def _score(row) -> int:
            name = row["name"]
            stem = Path(name).stem
            # Penalize (1), (2), -1, _1, _copy, _backup suffixes
            if re.search(r"[\s._-]\(?\d+\)?$", stem):
                return 10
            if any(x in stem.lower() for x in ("copy", "backup", "duplicate")):
                return 8
            return 0

        scored = sorted(members, key=_score)
        keeper = scored[0]  # lowest score = keep this one

        for m in scored[1:]:
            p = Path(m["path"])
            if _is_protected(p):
                continue
            to_delete.append(CleanItem(
                path=p,
                reason=f"Duplicate of {keeper['name']}",
                size_bytes=m["size_bytes"],
                file_id=m["id"],
            ))

    return to_delete


def plan_old_installer_deletions(
    conn: sqlite3.Connection,
    days: int = OLD_DAYS,
    folder_id: int | None = None,
) -> list[CleanItem]:
    """Return old installer files (exe/msi) not modified in `days` days."""
    cutoff = time.time() - days * 86400
    if folder_id is not None:
        rows = conn.execute(
            """SELECT id, path, name, extension, size_bytes, mtime
               FROM files
               WHERE mtime < ? AND is_junk = 0 AND folder_id = ?
               ORDER BY size_bytes DESC""",
            (cutoff, folder_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, path, name, extension, size_bytes, mtime
               FROM files
               WHERE mtime < ? AND is_junk = 0
               ORDER BY size_bytes DESC""",
            (cutoff,),
        ).fetchall()

    items: list[CleanItem] = []
    for r in rows:
        if r["extension"].lower() in INSTALLER_EXTENSIONS:
            p = Path(r["path"])
            if _is_protected(p):
                continue
            age_days = int((time.time() - r["mtime"]) / 86400)
            items.append(CleanItem(
                path=p,
                reason=f"Old installer — untouched for {age_days} days",
                size_bytes=r["size_bytes"],
                file_id=r["id"],
            ))

    return items


def execute_deletions(
    items: list[CleanItem], conn: sqlite3.Connection
) -> tuple[int, int, list[str]]:
    """Send files to Recycle Bin. Returns (deleted_count, bytes_freed, errors)."""
    from send2trash import send2trash

    deleted = 0
    freed = 0
    errors: list[str] = []
    deleted_ids: list[int] = []

    for item in items:
        try:
            if item.path.exists():
                send2trash(str(item.path))
                freed += item.size_bytes
                deleted += 1
                deleted_ids.append(item.file_id)
            else:
                # File already gone — clean up DB anyway
                deleted_ids.append(item.file_id)
        except Exception as e:
            errors.append(f"{item.path.name}: {e}")

    # Remove deleted files from database
    if deleted_ids:
        conn.executemany(
            "DELETE FROM files WHERE id = ?",
            [(fid,) for fid in deleted_ids],
        )
        # Rebuild duplicate groups
        conn.execute("DELETE FROM duplicate_groups")
        conn.execute(
            """INSERT INTO duplicate_groups (sha256, file_count, total_size, wasted)
               SELECT sha256, COUNT(*), COUNT(*) * MAX(size_bytes),
                      (COUNT(*) - 1) * MAX(size_bytes)
               FROM files WHERE sha256 IS NOT NULL
               GROUP BY sha256 HAVING COUNT(*) > 1"""
        )
        conn.execute(
            """INSERT INTO duplicate_members (group_id, file_id)
               SELECT dg.id, f.id FROM duplicate_groups dg
               JOIN files f ON f.sha256 = dg.sha256"""
        )
        conn.commit()

    return deleted, freed, errors
