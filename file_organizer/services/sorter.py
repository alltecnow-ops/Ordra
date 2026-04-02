import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from file_organizer.config import SORT_RULES, PROTECTED_PATH_SEGMENTS


@dataclass
class SortAction:
    file_id: int
    source: Path
    destination: Path
    category: str


def build_sort_plan(
    conn: sqlite3.Connection,
    base_output_dir: Path,
    folder_id: int | None = None,
) -> list[SortAction]:
    ext_to_cat: dict[str, str] = {}
    for cat, exts in SORT_RULES.items():
        for ext in exts:
            ext_to_cat[ext] = cat

    if folder_id is not None:
        rows = conn.execute(
            "SELECT id, path, name, extension FROM files WHERE is_junk = 0 AND folder_id = ?",
            (folder_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, path, name, extension FROM files WHERE is_junk = 0"
        ).fetchall()

    conn.execute("DELETE FROM sort_plan")
    now = time.time()
    actions: list[SortAction] = []
    used_destinations: set[str] = set()

    for r in rows:
        source = Path(r["path"])

        # Layer 2 guard: never touch files inside protected paths
        if _is_protected(source):
            continue

        cat = ext_to_cat.get(r["extension"], "Other")
        dest_dir = base_output_dir / cat

        # Skip files already inside their correct category subfolder
        try:
            source.relative_to(dest_dir)
            continue  # already in the right place
        except ValueError:
            pass

        dest = _resolve_collision(dest_dir / r["name"], used_destinations)
        used_destinations.add(dest.as_posix())

        conn.execute(
            """INSERT INTO sort_plan (file_id, source_path, destination_path, category, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (r["id"], r["path"], dest.as_posix(), cat, now),
        )
        actions.append(SortAction(r["id"], source, dest, cat))

    conn.commit()
    return actions


def execute_sort_plan(
    actions: list[SortAction], conn: sqlite3.Connection
) -> tuple[int, list[str]]:
    """Move files according to the plan. Returns (moved_count, errors)."""
    moved = 0
    errors: list[str] = []

    for action in actions:
        try:
            if not action.source.exists():
                errors.append(f"{action.source.name}: source not found")
                continue
            action.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(action.source), str(action.destination))
            # Update path in DB
            conn.execute(
                "UPDATE files SET path = ?, name = ?, updated_at = ? WHERE id = ?",
                (action.destination.as_posix(), action.destination.name, time.time(), action.file_id),
            )
            moved += 1
        except Exception as e:
            errors.append(f"{action.source.name}: {e}")

    conn.commit()
    return moved, errors


def _is_protected(path: Path) -> bool:
    """Return True if any segment of the path matches a protected directory name."""
    parts = {p.lower() for p in path.parts}
    return bool(parts & PROTECTED_PATH_SEGMENTS)


def _resolve_collision(dest: Path, used: set[str]) -> Path:
    if dest.as_posix() not in used:
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if candidate.as_posix() not in used:
            return candidate
        i += 1
