import os
import sqlite3
import atexit
from pathlib import Path

from file_organizer.config import DB_PATH

_conn: sqlite3.Connection | None = None


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Restrict the data directory and DB file to owner-only on POSIX systems.
    # This prevents other users on a shared machine from reading file index data.
    try:
        os.chmod(db_path.parent, 0o700)
    except OSError:
        pass
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _apply_schema(conn)
    try:
        os.chmod(str(db_path), 0o600)
    except OSError:
        pass
    return conn


def _apply_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = get_connection()
        atexit.register(_conn.close)
    return _conn
