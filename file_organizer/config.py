import os
from pathlib import Path

DB_PATH = Path.home() / ".ordra" / "index.db"

# ── Layer 1: directories never descended into during scan ──────────────────
# Matched case-insensitively against each directory NAME (not full path).
SCAN_SKIP_DIRS: set[str] = {
    # Windows OS — touching these breaks the system
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "recovery", "boot",
    "perflogs", "msocache", "winsxs", "servicing", "efi", "winre",
    # User app data — configs/caches that belong to installed apps
    "appdata",
    # Development internals — huge and must never be reorganized
    "node_modules", "__pycache__", ".venv", "venv", ".tox",
    "site-packages", ".eggs", "dist-info", "egg-info",
    # Version control — moving files inside these corrupts repos
    ".git", ".svn", ".hg", ".bzr",
    # IDE / editor settings
    ".idea", ".vscode", ".vs",
    # Mobile device system dirs
    "android", "lost.dir", ".android_secure", ".trash-1000",
    # macOS system
    "private", "cores", ".spotlight-v100", ".fseventsd", ".trashes",
    "library", "system", "volumes",
    # Linux system
    "proc", "sys", "dev", "run",
    "etc", "bin", "sbin", "lib", "lib64", "usr", "var", "tmp", "opt", "root",
    # Credential and secret directories — never index or reorganize
    ".ssh", ".aws", ".kube", ".docker", ".gnupg",
}

# ── Layer 2: path segments that make a file untouchable ────────────────────
# Checked against the FULL lowercase path before any move or delete.
# This is a backstop — if a file somehow got indexed, it still won't be touched.
PROTECTED_PATH_SEGMENTS: set[str] = {
    # Windows
    "windows", "program files", "program files (x86)", "programdata",
    "system volume information", "$recycle.bin", "appdata",
    "winsxs", "servicing", "perflogs", "recovery", "efi", "winre",
    # Development / version control
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    "site-packages",
    # macOS
    "library", "system", "volumes", "private",
    # Linux
    "etc", "bin", "sbin", "lib", "lib64", "usr", "var",
    "proc", "sys", "dev", "run", "boot", "opt",
    # Credential and secret directories
    ".ssh", ".aws", ".kube", ".docker", ".gnupg",
}

HASH_WORKERS = min(8, os.cpu_count() or 4)
HASH_CHUNK_SIZE = 65536  # 64 KB

LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB
OLD_FILE_DAYS = 365

JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}
JUNK_EXTENSIONS = {".tmp", ".temp", ".bak", ".log", ".crdownload", ".part", ".cache"}
JUNK_PREFIXES = ("~$",)

SORT_RULES = {
    "Images":     {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                   ".webp", ".svg", ".heic", ".heif", ".raw", ".cr2", ".nef", ".arw"},
    "Videos":     {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm",
                   ".m4v", ".3gp", ".ogv", ".ts"},
    "Audio":      {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma",
                   ".opus", ".aiff"},
    "Documents":  {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                   ".txt", ".md", ".rtf", ".odt", ".ods", ".odp", ".epub"},
    "Archives":   {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Code":       {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c",
                   ".h", ".hpp", ".go", ".rs", ".php", ".rb", ".swift", ".kt",
                   ".sh", ".bat", ".ps1", ".json", ".yaml", ".yml", ".toml",
                   ".xml", ".sql"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage"},
    "Fonts":      {".ttf", ".otf", ".woff", ".woff2"},
    "Data":       {".csv", ".db", ".sqlite", ".sqlite3"},
}
