import hashlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn, TimeRemainingColumn

from file_organizer.config import HASH_WORKERS, HASH_CHUNK_SIZE


@dataclass
class HashResult:
    hashed: int
    skipped_unique: int
    elapsed: float


def hash_unprocessed(conn: sqlite3.Connection, console: Console) -> HashResult:
    started = time.time()

    # Size pre-filter: only hash files whose size appears more than once
    candidates = conn.execute(
        """SELECT id, path FROM files
           WHERE sha256 IS NULL AND is_junk = 0
             AND size_bytes > 0
             AND size_bytes IN (
               SELECT size_bytes FROM files
               WHERE sha256 IS NULL AND is_junk = 0
               GROUP BY size_bytes HAVING COUNT(*) > 1
             )"""
    ).fetchall()

    skipped_unique = conn.execute(
        """SELECT COUNT(*) FROM files
           WHERE sha256 IS NULL AND is_junk = 0
             AND size_bytes NOT IN (
               SELECT size_bytes FROM files
               WHERE sha256 IS NULL AND is_junk = 0
               GROUP BY size_bytes HAVING COUNT(*) > 1
             )"""
    ).fetchone()[0]

    if not candidates:
        return HashResult(0, skipped_unique, time.time() - started)

    results: list[tuple[str, int]] = []  # (sha256, file_id)

    with Progress(
        TextColumn("[bold green]Hashing[/bold green]"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("files", total=len(candidates))

        with ThreadPoolExecutor(max_workers=HASH_WORKERS) as executor:
            future_to_id = {
                executor.submit(_hash_file, row["path"]): row["id"]
                for row in candidates
            }
            for future in as_completed(future_to_id):
                file_id = future_to_id[future]
                digest = future.result()
                if digest:
                    results.append((digest, time.time(), file_id))
                progress.advance(task)

    if results:
        conn.executemany(
            "UPDATE files SET sha256 = ?, hashed_at = ? WHERE id = ?",
            results,
        )
        conn.commit()

    _rebuild_duplicate_groups(conn)
    return HashResult(len(results), skipped_unique, time.time() - started)


def _hash_file(path_str: str) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path_str, "rb") as f:
            while chunk := f.read(HASH_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _rebuild_duplicate_groups(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM duplicate_groups")
    conn.execute(
        """INSERT INTO duplicate_groups (sha256, file_count, total_size, wasted)
           SELECT sha256,
                  COUNT(*),
                  COUNT(*) * MAX(size_bytes),
                  (COUNT(*) - 1) * MAX(size_bytes)
           FROM files
           WHERE sha256 IS NOT NULL
           GROUP BY sha256
           HAVING COUNT(*) > 1"""
    )
    conn.execute(
        """INSERT INTO duplicate_members (group_id, file_id)
           SELECT dg.id, f.id
           FROM duplicate_groups dg
           JOIN files f ON f.sha256 = dg.sha256"""
    )
    conn.commit()
