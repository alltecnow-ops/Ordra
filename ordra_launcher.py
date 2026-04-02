import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console
from rich.text import Text
from rich.align import Align
from rich.rule import Rule
from rich.prompt import Prompt
from rich.panel import Panel

ORDRA      = r"C:\Users\Alltecnow\AppData\Local\Python\pythoncore-3.14-64\Scripts\ordra.exe"
DB_PATH    = Path.home() / ".ordra" / "index.db"
REPORT_DIR = Path.home() / ".ordra" / "reports"
MAX_REPORTS = 5

console = Console(legacy_windows=False, width=100)


# ── Session tracking ──────────────────────────────────────────────────────────

class Session:
    def __init__(self):
        self.started = datetime.now()
        self.log: list[str] = []

    def record(self, entry: str):
        self.log.append(f"  {datetime.now().strftime('%H:%M:%S')}  {entry}")

session = Session()


# ── Core helpers ──────────────────────────────────────────────────────────────

def run(*args):
    subprocess.run([ORDRA] + list(args))


def fresh_start():
    """Delete the database so this session starts clean."""
    if DB_PATH.exists():
        DB_PATH.unlink()


def save_report():
    """Write a session report and keep only the last MAX_REPORTS files."""
    if not session.log:
        return

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = session.started.strftime("%Y-%m-%d_%H%M%S")
    report_path = REPORT_DIR / f"ordra_{timestamp}.txt"

    lines = [
        "ORDRA SESSION REPORT",
        "=" * 40,
        f"Date    : {session.started.strftime('%Y-%m-%d')}",
        f"Started : {session.started.strftime('%H:%M:%S')}",
        f"Ended   : {datetime.now().strftime('%H:%M:%S')}",
        "",
        "ACTIONS",
        "-" * 40,
    ] + session.log + [""]

    report_path.write_text("\n".join(lines), encoding="utf-8")

    # Prune oldest reports beyond MAX_REPORTS
    reports = sorted(REPORT_DIR.glob("ordra_*.txt"))
    for old in reports[:-MAX_REPORTS]:
        old.unlink()


def header():
    console.clear()
    console.print()
    console.print(Align.center(Text("O  R  D  R  A", style="bold cyan")))
    console.print(Align.center(Text("Your files. Under control.", style="dim white")))
    console.print(Align.center(Rule(style="dim cyan")))
    console.print()


def menu():
    items = [
        ("1", "Scan",          "index a folder or drive"),
        ("2", "Stats",         "health of last scanned folder"),
        ("3", "Duplicates",    "find wasted space"),
        ("4", "Suggestions",   "what to review and clean up"),
        ("5", "Clean",         "delete dupes + old installers"),
        ("6", "Organize",      "sort files into category folders"),
        ("7", "All folders",   "combined view across everything"),
        ("8", "Chat with AI",  "ask anything about your files"),
        ("0", "Exit",          ""),
    ]
    pad = " " * 30
    for key, name, desc in items:
        line = Text()
        line.append(f"{pad}  {key}  ", style="bold cyan")
        line.append(f"{name:<18}", style="bold white")
        line.append(desc, style="dim")
        console.print(line)

    console.print()
    console.print(Align.center(Rule(style="dim cyan")))
    console.print()


def pause():
    console.print()
    console.print(Align.center(Text("Press Enter to return to menu", style="dim cyan")))
    input()


# ── Smart scan resolver ───────────────────────────────────────────────────────

def resolve_scan_target() -> str | None:
    HOME = Path.home()
    KNOWN = {
        "documents": HOME / "Documents",
        "document":  HOME / "Documents",
        "downloads": HOME / "Downloads",
        "download":  HOME / "Downloads",
        "desktop":   HOME / "Desktop",
        "pictures":  HOME / "Pictures",
        "picture":   HOME / "Pictures",
        "photos":    HOME / "Pictures",
        "music":     HOME / "Music",
        "videos":    HOME / "Videos",
        "video":     HOME / "Videos",
    }

    def tip():
        console.print()
        console.print(Text("  Tip: to copy a folder path in Windows Explorer:", style="dim"))
        console.print(Text("  Hold Shift + Right-click the folder → 'Copy as path'", style="dim cyan"))
        console.print(Text("  Then paste it here with Ctrl+V", style="dim"))
        console.print()

    console.print()
    raw = Prompt.ask(
        "  [cyan]What would you like to scan?[/cyan]\n"
        "  [dim](e.g.  documents  /  drive D  /  paste a full path)[/dim]\n"
        "  [cyan]>[/cyan]"
    ).strip()
    if not raw:
        return None

    lower = raw.lower().replace("please", "").replace("scan", "").replace("my", "").strip()

    # Known folder names
    for keyword, path in KNOWN.items():
        if keyword in lower:
            if path.exists():
                console.print(Text(f"\n  Got it — scanning: {path}\n", style="dim white"))
                return str(path)

    # Drive letter patterns: "drive d", "d drive", "D:", bare "D"
    drive_match = re.search(
        r'\b([a-zA-Z])[\s:]*(drive|disk)?\b|\bdrive[\s:]+([a-zA-Z])\b', lower
    )
    if drive_match:
        letter = (drive_match.group(1) or drive_match.group(3) or "").upper()
        if letter:
            drive_path = Path(f"{letter}:\\")
            if drive_path.exists():
                if letter == "C":
                    console.print()
                    console.print(Text("  Drive C: is your system drive.", style="yellow"))
                    console.print(Text(
                        "  Ordra will skip Windows, Program Files and all system folders automatically.",
                        style="dim"
                    ))
                    confirm = Prompt.ask(
                        "\n  [cyan]Scan Drive C: now?[/cyan]", choices=["y", "n"], default="y"
                    )
                    if confirm != "y":
                        return None
                else:
                    console.print(Text(f"\n  Got it — scanning Drive {letter}:\\\n", style="dim white"))
                return str(drive_path)
            else:
                console.print(Text(f"\n  Drive {letter}: not found. Is it plugged in?\n", style="yellow"))
                return None

    # Looks like a pasted path
    if "\\" in raw or "/" in raw or (len(raw) >= 2 and raw[1] == ":"):
        path = Path(raw.strip('"').strip("'"))
        if path.exists():
            console.print(Text(f"\n  Got it — scanning: {path}\n", style="dim white"))
            return str(path)
        else:
            console.print(Text(f"\n  Path not found: {path}", style="red"))
            tip()
            return None

    # Unknown — guide the user
    console.print()
    console.print(Text("  Not sure which folder that is.", style="yellow"))
    tip()
    raw2 = Prompt.ask("  [cyan]Please paste the full folder path[/cyan]").strip().strip('"').strip("'")
    if not raw2:
        return None
    path = Path(raw2)
    if path.exists():
        return str(path)
    console.print(Text(f"\n  Path not found: {path}\n", style="red"))
    return None


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    fresh_start()

    while True:
        header()
        menu()

        choice = Prompt.ask(
            "  [bold cyan]Choose[/bold cyan]",
            choices=["0","1","2","3","4","5","6","7","8"],
            show_choices=False,
        )

        if choice == "0":
            save_report()
            console.clear()
            console.print()
            if session.log:
                console.print(Align.center(Text(
                    f"Session report saved to ~/.ordra/reports/", style="dim cyan"
                )))
            console.print(Align.center(Text("Stay organized.", style="bold cyan")))
            console.print()
            break

        elif choice == "1":
            folder = resolve_scan_target()
            if folder:
                console.print()
                run("scan", folder)
                session.record(f"Scanned: {folder}")
                pause()

        elif choice == "2":
            console.print()
            run("stats")
            session.record("Viewed stats")
            pause()

        elif choice == "3":
            console.print()
            run("dupes")
            session.record("Viewed duplicates")
            pause()

        elif choice == "4":
            console.print()
            run("suggest")
            session.record("Viewed suggestions")
            pause()

        elif choice == "5":
            console.print()
            run("clean")
            session.record("Ran clean (duplicates + old installers)")
            pause()

        elif choice == "6":
            console.print()
            run("sort")
            console.print()
            confirm = Prompt.ask(
                "  [cyan]Move files now?[/cyan]",
                choices=["y", "n"],
                default="n",
            )
            if confirm == "y":
                console.print()
                run("sort", "--execute", "--yes")
                session.record("Organized files into category folders")
            pause()

        elif choice == "7":
            console.print()
            run("stats", "--all")
            session.record("Viewed all-folder stats")
            pause()

        elif choice == "8":
            console.print()
            question = Prompt.ask("  [cyan]Ask anything about your files[/cyan]")
            console.print()
            run("chat", question)
            session.record(f"Chat: {question}")
            pause()


if __name__ == "__main__":
    main()