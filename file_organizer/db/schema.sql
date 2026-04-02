PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS watched_folders (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT    NOT NULL UNIQUE,
    added_at  REAL    NOT NULL,
    last_scan REAL
);

CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id   INTEGER NOT NULL REFERENCES watched_folders(id) ON DELETE CASCADE,
    path        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    extension   TEXT    NOT NULL,
    size_bytes  INTEGER NOT NULL,
    mtime       REAL    NOT NULL,
    sha256      TEXT,
    hashed_at   REAL,
    is_junk     INTEGER NOT NULL DEFAULT 0,
    junk_reason TEXT,
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256     TEXT    NOT NULL UNIQUE,
    file_count INTEGER NOT NULL,
    total_size INTEGER NOT NULL,
    wasted     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, file_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         INTEGER REFERENCES files(id) ON DELETE CASCADE,
    category        TEXT    NOT NULL,
    detail          TEXT,
    potential_bytes INTEGER,
    created_at      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS sort_plan (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id          INTEGER REFERENCES files(id) ON DELETE CASCADE,
    source_path      TEXT    NOT NULL,
    destination_path TEXT    NOT NULL,
    category         TEXT,
    created_at       REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_size   ON files(size_bytes);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);
CREATE INDEX IF NOT EXISTS idx_files_ext    ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_mtime  ON files(mtime);
CREATE INDEX IF NOT EXISTS idx_files_junk   ON files(is_junk);
