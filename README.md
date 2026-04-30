# Ordra

**Instant clarity and control over your files — powered by AI.**

Ordra is a Python CLI tool that scans any folder or drive, surfaces what's wasting space, removes duplicates safely, organizes what remains, and lets you ask questions about your files in plain English — all in seconds.

> 🧹 Recovered **6 GB** from a Downloads folder in one command. Health score: **77 → 99/100.**  
> 📦 Successfully indexed **360,755 files · 503 GB** on a full D: drive scan.

---

## Features

| Command | What it does |
|--------|-------------|
| `ordra scan <path>` | Index any folder or full drive. Skips system directories automatically. |
| `ordra stats` | Health dashboard — score, space breakdown, reclaimable storage. |
| `ordra dupes` | Duplicate file groups detected via SHA256 hashing, sorted by wasted space. |
| `ordra suggest` | Smart recommendations + streaming Claude AI insights about your files. |
| `ordra clean` | Preview then safely delete duplicates and old installers → Recycle Bin only. |
| `ordra sort` | Dry-run preview of automatic reorganization into category subfolders. |
| `ordra sort --execute` | Actually move files. Confirms before acting. |
| `ordra chat "<question>"` | Ask anything about your indexed files in natural language. |
| `ordra folders` | List all indexed folders. |

**Scoping flags** available on every command:
- Default → most recently scanned folder
- `--folder <name>` → filter by partial name (e.g. `--folder downloads`)
- `--all` → combined view across all indexed folders

---

## Safety — Non-Negotiable

- ✅ **Never deletes permanently** — every deletion goes through `send2trash` → Windows Recycle Bin
- ✅ **System folder protection** — two independent layers in `config.py` prevent touching OS directories
- ✅ **Always confirms** before any destructive operation (unless `--yes` is passed)
- ✅ **Fully reversible** — restore anything from the Recycle Bin if needed

---

## AI Integration

Ordra integrates the **Anthropic Claude API** with streaming output for two features:

- **`ordra suggest`** — streams a personalized, real-time analysis of your actual file data
- **`ordra chat`** — answers any natural language question about your indexed files

This isn't generic advice. Claude reads your scan results and gives insights specific to *your* drive.

Requires an `ANTHROPIC_API_KEY` environment variable.

---

## Stack

| Layer | Technology |
|-------|-----------|
| CLI framework | [Typer](https://typer.tiangolo.com/) |
| Terminal UI | [Rich](https://github.com/Textualize/rich) |
| Database | SQLite (stdlib) |
| Hashing | SHA256 + ThreadPoolExecutor |
| Safe deletion | [send2trash](https://github.com/arsenetar/send2trash) |
| AI | Anthropic Claude API (`claude-opus-4-6`) |
| Desktop launcher | Python + Rich |

---

## Installation

**Requirements:** Python 3.10+ · Windows 11 (macOS/Linux support planned)

```bash
git clone https://github.com/alltecnow-ops/Ordra.git
cd Ordra
pip install -e .
```

Set your Anthropic API key (required for AI features):

```bash
# Windows — temporary
set ANTHROPIC_API_KEY=your_key_here

# Or add it permanently via System Environment Variables
```

Then run:

```bash
ordra scan "C:\Users\YourName\Downloads"
ordra stats
ordra suggest
ordra chat "What's taking up the most space?"
```

---

## Desktop Launcher

Double-click `Ordra.bat` on your desktop for a Rich interactive menu — no terminal knowledge required. It guides you through scanning, cleaning, and organizing with a friendly UI, and saves a session report automatically on exit.

---

## Project Structure

```
file_organizer/
├── cli.py                  # All Typer commands
├── config.py               # Single source of truth — all constants
├── db/
│   ├── connection.py       # SQLite singleton
│   └── schema.sql          # Tables: files, duplicates, suggestions, sort_plan
├── services/
│   ├── scanner.py          # Recursive folder indexing
│   ├── hasher.py           # SHA256 duplicate detection
│   ├── duplicates.py       # Duplicate grouping + space summaries
│   ├── suggestions.py      # Large / old / junk / misplaced file detection
│   ├── sorter.py           # Sort plan builder + executor
│   ├── cleaner.py          # Safe deletion planner + executor
│   └── ai.py               # Claude API streaming integration
└── display/
    └── tables.py           # All Rich terminal rendering
```

---

## Roadmap

**Phase 1 — Complete ✅**  
Core scan, stats, duplicates, suggestions, clean, sort, AI chat, desktop launcher, full-drive support, per-folder scoping.

**Phase 2 — Planned**
- Undo / restore for clean and sort operations
- Scheduled scans and watch mode
- Cross-drive duplicate detection
- Custom sort rules
- PDF / HTML report export
- GUI / web dashboard

**Phase 3 — Distribution**
- Windows `.exe` installer
- macOS / Linux support
- Public website

---

## License

MIT

---

*Built by [@alltecnow-ops](https://github.com/alltecnow-ops)*
