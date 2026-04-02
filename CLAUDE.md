# Ordra — Claude Code Project

## Vision

Ordra is a CLI tool that gives anyone instant clarity and control over their files — across any folder, drive, or device. Most people live with chaotic Downloads folders, duplicate files wasting gigabytes, and no idea what's taking up space. Ordra fixes that in seconds: scan any folder, see exactly what's there, delete the waste, and organize what remains — all from a single tool, with AI that explains and guides.

**Goal:** become the default first step whenever someone gets a new device, inherits a cluttered drive, or simply wants their digital life in order. Simple enough for anyone, powerful enough for every scenario.

**Core values — never compromise these:**
- Simplicity first. No feature that adds confusion.
- Flawless execution. Every operation must be safe and reversible.
- Never delete permanently — always `send2trash`.
- Never touch system folders — enforced by two independent layers in `config.py`.

---

## Environment

- **OS:** Windows 11
- **Python:** `C:/Users/Alltecnow/AppData/Local/Python/pythoncore-3.14-64/python.exe`
- **Ordra executable:** `C:/Users/Alltecnow/AppData/Local/Python/pythoncore-3.14-64/Scripts/ordra.exe`
- **Short alias:** `ordra` (via `C:/Users/Alltecnow/.local/bin/ordra.bat`)
- **Project root:** `C:/Users/Alltecnow/file-organizer/`
- **Database:** `~/.ordra/index.db` (SQLite)
- **Session reports:** `~/.ordra/reports/ordra_YYYY-MM-DD_HHMMSS.txt` (last 5 kept)
- **Desktop launcher:** `C:/Users/Alltecnow/Desktop/Ordra.bat` → calls `ordra_launcher.py`

**After any code change, reinstall:**
```bash
"C:/Users/Alltecnow/AppData/Local/Python/pythoncore-3.14-64/python.exe" -m pip install -e .
```
Then verify with `ordra stats` before marking done.

---

## Stack

| Layer | Technology |
|-------|-----------|
| CLI framework | Typer |
| Terminal UI | Rich (`Console(legacy_windows=False)`) |
| Database | SQLite via `sqlite3` stdlib |
| Hashing | SHA256, ThreadPoolExecutor |
| Safe deletion | `send2trash` → Recycle Bin |
| AI insights | Anthropic Claude API (`claude-opus-4-6`) |
| Desktop launcher | Python + Rich (`ordra_launcher.py`) |

---

## Project Structure

```
C:/Users/Alltecnow/file-organizer/
  pyproject.toml              # Package: ordra, entry point cli:app
  ordra_launcher.py           # Desktop launcher — Rich interactive menu
  CLAUDE.md                   # This file
  file_organizer/
    cli.py                    # All Typer commands
    config.py                 # Single source of truth for all constants
    db/
      connection.py           # get_db() singleton, auto-applies schema
      schema.sql              # Tables: watched_folders, files, duplicate_groups,
                              #         duplicate_members, suggestions, sort_plan
    services/
      scanner.py              # scan_folder() — os.walk, skip system dirs, junk classify
      hasher.py               # hash_unprocessed() — SHA256, size pre-filter, ThreadPool
      duplicates.py           # get_duplicate_groups(), get_space_summary()
      suggestions.py          # run_suggestions() — large / old / junk / misplaced
      sorter.py               # build_sort_plan(), execute_sort_plan()
      cleaner.py              # plan_dupe_deletions(), plan_old_installer_deletions(),
                              #   execute_deletions()
      ai.py                   # stream_insights(), stream_chat() — Claude API streaming
    display/
      tables.py               # All Rich rendering: header, stats, dupes, suggestions,
                              #   sort plan, folders
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `ordra scan <path>` | Index a folder or full drive. Skips system dirs automatically. |
| `ordra stats` | Health dashboard — score, breakdown, reclaimable space. |
| `ordra dupes` | Duplicate file groups sorted by wasted space. |
| `ordra suggest` | Smart recommendations + streaming AI insights. |
| `ordra clean` | Preview + delete dupes and old installers (Recycle Bin). |
| `ordra sort` | Dry-run preview of reorganization into category subfolders. |
| `ordra sort --execute` | Actually move files. Confirms before acting. |
| `ordra folders` | List all indexed folders. |
| `ordra chat "<question>"` | Natural language chat about indexed files. |

**Folder scoping — all commands support:**
- Default → most recently scanned folder
- `--folder <name>` → partial name match (e.g. `--folder downloads`)
- `--all` → combined view across all indexed folders

---

## Key Architectural Decisions

- **Per-folder scoping** — `watched_folders` table; all service functions accept `folder_id: int | None`
- **Two-layer safety** — `SCAN_SKIP_DIRS` prevents indexing; `PROTECTED_PATH_SEGMENTS` prevents move/delete even if somehow indexed
- **Fresh session model** — `ordra_launcher.py` clears the DB on every launch; session report auto-saved on exit
- **Streaming AI** — `client.messages.stream()` for live token-by-token output
- **Windows Unicode** — `Console(legacy_windows=False)` + `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
- **In-place sort** — `ordra sort --execute` organizes files into subfolders within the scanned folder itself, not an external directory

---

## Safety Rules — Never Break These

1. **Never bypass `SCAN_SKIP_DIRS`** — defined in `config.py`, applied in `scanner.py` via `dirs[:] = [...]`
2. **Never bypass `PROTECTED_PATH_SEGMENTS`** — checked in `sorter.py` and `cleaner.py` via `_is_protected()` before any write
3. **Never use `os.remove` or `shutil.rmtree`** — always `send2trash.send2trash()`
4. **Always confirm before destructive operations** — `clean` and `sort --execute` prompt unless `--yes` is passed
5. **`config.py` is the single source of truth** — no hardcoded paths, thresholds, or skip lists anywhere else
6. **Do not refactor Phase 1** unless fixing a confirmed bug reported by the user

---

## AI Integration

- **Model:** `claude-opus-4-6`
- **Requires:** `ANTHROPIC_API_KEY` environment variable
- `stream_insights()` — called by `ordra suggest`; streams a personalized analysis of scan results
- `stream_chat()` — called by `ordra chat`; answers natural language questions about indexed files

---

## Desktop Launcher (`ordra_launcher.py`)

A standalone Rich-based interactive menu. Invoked by `Ordra.bat` on the desktop.

**Behavior:**
- Clears the database on launch (fresh session every time)
- Smart scan input — understands "documents", "drive D", "downloads", pasted paths
- Tracks all actions in a `Session` object
- On exit: saves a `.txt` session report to `~/.ordra/reports/`, keeps last 5

**Session report location:** `C:/Users/Alltecnow/.ordra/reports/`

---

## ✅ Phase 1 — COMPLETE

Everything below was built and is working in production.

### What was built

| Feature | Status |
|---------|--------|
| `ordra scan` — recursive folder indexing | ✅ |
| `ordra stats` — health score, space breakdown | ✅ |
| `ordra dupes` — SHA256 duplicate detection | ✅ |
| `ordra suggest` — large / old / junk / misplaced files | ✅ |
| `ordra clean` — safe deletion to Recycle Bin | ✅ |
| `ordra sort` — dry-run reorganization preview | ✅ |
| `ordra sort --execute` — in-place file organization | ✅ |
| `ordra chat` — AI natural language Q&A | ✅ |
| `ordra suggest` — streaming Claude AI insights | ✅ |
| Per-folder default + `--folder` + `--all` flags | ✅ |
| Full drive scan (`C:\`, `D:\`) | ✅ |
| Two-layer system folder protection | ✅ |
| Windows Unicode rendering fix | ✅ |
| `ordra` available from any terminal (PATH + .bat) | ✅ |
| Desktop launcher with Rich interactive menu | ✅ |
| Smart scan input (natural language path resolver) | ✅ |
| Fresh session model + auto session reports | ✅ |

### Real-world results
- Ran `ordra clean` on Downloads → freed **6 GB**, health score went from **77 → 99/100**
- D: drive scan: **360,755 files · 503 GB** indexed successfully

---

## 🔲 Phase 2 — Planned

Do not implement Phase 2 features unless the user explicitly requests them.

| Feature | Description |
|---------|-------------|
| Scheduled scans | Run automatically in the background on a schedule |
| Watch mode | Detect new files in real-time as they arrive |
| Undo / restore | Reverse a `clean` or `sort --execute` operation |
| Cross-drive duplicates | Find the same file across two different drives |
| Custom sort rules | User-defined categories and extension mappings |
| Export reports | PDF or HTML formatted session reports |
| GUI / web dashboard | Visual interface instead of terminal |
| Windows installer | Proper `.exe` installer for distribution |
| macOS / Linux support | Full cross-platform compatibility |

---

## 🔲 Phase 3 — Distribution

| Feature | Description |
|---------|-------------|
| Windows installer (.exe) | One-click install for non-technical users |
| Auto-update mechanism | Pull new versions silently |
| Subscription AI tier | Premium Claude-powered features |
| Website + landing page | Public-facing product |