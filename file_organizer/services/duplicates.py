import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DuplicateGroup:
    sha256: str
    file_count: int
    size_bytes: int
    wasted_bytes: int
    members: list[Path]


@dataclass
class SpaceSummary:
    total_files: int
    total_size_bytes: int
    duplicate_wasted_bytes: int
    junk_bytes: int
    reclaimable_bytes: int


def get_duplicate_groups(
    conn: sqlite3.Connection,
    min_size: int = 0,
    limit: int = 50,
    folder_id: int | None = None,
) -> list[DuplicateGroup]:
    if folder_id is not None:
        groups = conn.execute(
            """SELECT DISTINCT dg.id, dg.sha256, dg.file_count, dg.wasted,
                      dg.total_size / dg.file_count AS size_each
               FROM duplicate_groups dg
               JOIN duplicate_members dm ON dm.group_id = dg.id
               JOIN files f ON f.id = dm.file_id
               WHERE dg.wasted >= ? AND f.folder_id = ?
               ORDER BY dg.wasted DESC
               LIMIT ?""",
            (min_size, folder_id, limit),
        ).fetchall()
    else:
        groups = conn.execute(
            """SELECT dg.id, dg.sha256, dg.file_count, dg.wasted,
                      dg.total_size / dg.file_count AS size_each
               FROM duplicate_groups dg
               WHERE dg.wasted >= ?
               ORDER BY dg.wasted DESC
               LIMIT ?""",
            (min_size, limit),
        ).fetchall()

    result = []
    for g in groups:
        members_rows = conn.execute(
            """SELECT f.path FROM duplicate_members dm
               JOIN files f ON f.id = dm.file_id
               WHERE dm.group_id = ?""",
            (g["id"],),
        ).fetchall()
        result.append(
            DuplicateGroup(
                sha256=g["sha256"][:12] + "...",
                file_count=g["file_count"],
                size_bytes=g["size_each"],
                wasted_bytes=g["wasted"],
                members=[Path(r["path"]) for r in members_rows],
            )
        )
    return result


def get_space_summary(
    conn: sqlite3.Connection,
    folder_id: int | None = None,
) -> SpaceSummary:
    if folder_id is not None:
        total = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(size_bytes), 0) AS s FROM files WHERE folder_id = ?",
            (folder_id,),
        ).fetchone()
        dup_wasted = conn.execute(
            """SELECT COALESCE(SUM(dg.wasted), 0)
               FROM duplicate_groups dg
               WHERE EXISTS (
                   SELECT 1 FROM duplicate_members dm
                   JOIN files f ON f.id = dm.file_id
                   WHERE dm.group_id = dg.id AND f.folder_id = ?
               )""",
            (folder_id,),
        ).fetchone()[0]
        junk = conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) FROM files WHERE is_junk = 1 AND folder_id = ?",
            (folder_id,),
        ).fetchone()[0]
    else:
        total = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(size_bytes), 0) AS s FROM files"
        ).fetchone()
        dup_wasted = conn.execute(
            "SELECT COALESCE(SUM(wasted), 0) FROM duplicate_groups"
        ).fetchone()[0]
        junk = conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) FROM files WHERE is_junk = 1"
        ).fetchone()[0]

    return SpaceSummary(
        total_files=total["c"],
        total_size_bytes=total["s"],
        duplicate_wasted_bytes=dup_wasted,
        junk_bytes=junk,
        reclaimable_bytes=dup_wasted + junk,
    )
