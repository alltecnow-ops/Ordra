import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from file_organizer.config import JUNK_NAMES, JUNK_EXTENSIONS, JUNK_PREFIXES, SCAN_SKIP_DIRS


@dataclass
class ScanResult:
    new: int
    updated: int
    deleted: int
    skipped: int
    total: int
    elapsed: float


def scan_folder(folder: Path, conn: sqlite3.Connection, console: Console) -> ScanResult:
    started = time.time()
    folder = folder.resolve()

    # Upsert watched folder
    conn.execute(
        "INSERT OR IGNORE INTO watched_folders (path, added_at) VALUES (?, ?)",
        (folder.as_posix(), time.time()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM watched_folders WHERE path = ?", (folder.as_posix(),)
    ).fetchone()
    folder_id = row["id"]

    # Load existing records for incremental check
    existing = {
        r["path"]: (r["id"], r["mtime"], r["size_bytes"])
        for r in conn.execute(
            "SELECT id, path, mtime, size_bytes FROM files WHERE folder_id = ?",
            (folder_id,),
        )
    }

    new_count = updated = skipped = 0
    seen_paths: set[str] = set()
    batch_insert = []
    batch_update = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Scanning[/bold blue] {task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(folder.name, total=None)

        for root, dirs, files in os.walk(str(folder), topdown=True):
            # Skip system directories in-place so os.walk won't descend into them
            dirs[:] = [d for d in dirs if d.lower() not in SCAN_SKIP_DIRS]

            root_path = Path(root)
            for fname in files:
                path = root_path / fname
                if not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue

                path_str = path.as_posix()
                seen_paths.add(path_str)
                mtime = stat.st_mtime
                size = stat.st_size
                is_junk, reason = _classify_junk(path)
                now = time.time()

                if path_str in existing:
                    eid, emtime, esize = existing[path_str]
                    if emtime == mtime and esize == size:
                        skipped += 1
                    else:
                        batch_update.append((mtime, size, is_junk, reason, now, eid))
                        updated += 1
                else:
                    batch_insert.append((
                        folder_id, path_str, path.name,
                        path.suffix.lower(), size, mtime,
                        is_junk, reason, now, now,
                    ))
                    new_count += 1

                progress.advance(task)

    if batch_insert:
        conn.executemany(
            """INSERT OR IGNORE INTO files
               (folder_id, path, name, extension, size_bytes, mtime,
                is_junk, junk_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            batch_insert,
        )

    if batch_update:
        conn.executemany(
            """UPDATE files SET mtime=?, size_bytes=?, is_junk=?, junk_reason=?,
               sha256=NULL, hashed_at=NULL, updated_at=? WHERE id=?""",
            batch_update,
        )

    # Remove deleted files
    all_db_paths = set(existing.keys())
    removed_paths = all_db_paths - seen_paths
    deleted = len(removed_paths)
    if removed_paths:
        conn.executemany(
            "DELETE FROM files WHERE path = ?",
            [(p,) for p in removed_paths],
        )

    conn.execute(
        "UPDATE watched_folders SET last_scan = ? WHERE id = ?",
        (time.time(), folder_id),
    )
    conn.commit()

    total = new_count + updated + skipped
    return ScanResult(new_count, updated, deleted, skipped, total, time.time() - started)


def _classify_junk(path: Path) -> tuple[bool, str | None]:
    name = path.name
    ext = path.suffix.lower()

    if name in JUNK_NAMES:
        return True, "system file"
    if ext in JUNK_EXTENSIONS:
        return True, f"{ext} file"
    for prefix in JUNK_PREFIXES:
        if name.startswith(prefix):
            return True, "temp office file"
    return False, None
