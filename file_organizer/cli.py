import sys

# Force UTF-8 output so Rich's Unicode box-drawing chars work on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.rule import Rule

from file_organizer.db.connection import get_db
from file_organizer.services import scanner, hasher, duplicates, suggestions, sorter, cleaner
from file_organizer.services import ai as ai_service
from file_organizer.display import tables

def _folders(db) -> list[str]:
    rows = db.execute("SELECT path FROM watched_folders ORDER BY added_at DESC").fetchall()
    return [r["path"] for r in rows]


def _active_folder(db, name: str | None = None) -> tuple[int | None, list[str]]:
    """Return (folder_id, [path]) for the target folder.

    - If `name` is given, match against known folders (partial, case-insensitive).
    - Otherwise, default to the most recently scanned folder.
    - Returns (None, []) when no folders have been scanned yet.
    """
    if name:
        escaped = name.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        row = db.execute(
            "SELECT id, path FROM watched_folders WHERE LOWER(path) LIKE ? ESCAPE '\\' ORDER BY last_scan DESC LIMIT 1",
            (f"%{escaped}%",),
        ).fetchone()
        if not row:
            return None, []
        return row["id"], [row["path"]]
    else:
        row = db.execute(
            "SELECT id, path FROM watched_folders ORDER BY last_scan DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None, []
        return row["id"], [row["path"]]


def _is_root_drive(path: Path) -> bool:
    """Return True if *path* is the root of a drive or filesystem.

    On Windows this catches C:\\ and D:\\; on Linux/macOS it catches /.
    Scanning a root drive is almost always unintentional and risks
    touching system directories if any safety guard is ever misconfigured.
    """
    resolved = path.resolve()
    # POSIX root
    if str(resolved) == "/":
        return True
    # Windows drive root: C:\\ has no parent other than itself
    if resolved == resolved.parent and resolved.drive:
        return True
    return False


app = typer.Typer(
    name="ordra",
    help="[bold cyan]Ordra[/bold cyan] — the world's smartest file organizer.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console(legacy_windows=False)


@app.command()
def scan(
    folder: Path = typer.Argument(..., help="Folder to scan and index"),
    no_hash: bool = typer.Option(False, "--no-hash", help="Skip duplicate detection (faster)"),
    force_rehash: bool = typer.Option(False, "--force-rehash", help="Re-hash all files from scratch"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for risky scans (e.g. drive root)"),
):
    """Scan a folder and index all files into the database."""
    if not folder.exists() or not folder.is_dir():
        console.print(f"[red]Error:[/red] '{folder}' is not a valid directory.")
        raise typer.Exit(1)

    if _is_root_drive(folder):
        console.print()
        console.print(
            "[bold yellow]  Warning:[/bold yellow] You are about to scan an entire drive root.\n"
            "  System directories will be skipped, but this scan may take a very long\n"
            "  time and index many files you don't intend to organize.\n"
            "  Consider scanning a specific folder (e.g. ~/Downloads) instead."
        )
        console.print()
        if not yes and not typer.confirm("  Scan the full drive root anyway?", default=False):
            console.print("\n[dim]Cancelled — nothing was scanned.[/dim]\n")
            raise typer.Exit()

    db = get_db()

    if force_rehash:
        db.execute("UPDATE files SET sha256 = NULL, hashed_at = NULL")
        db.commit()
        console.print("[yellow]Cleared all existing hashes.[/yellow]")

    result = scanner.scan_folder(folder, db, console)
    tables.render_scan_result(result, console, folders=_folders(db))

    if not no_hash:
        hash_result = hasher.hash_unprocessed(db, console)
        if hash_result.hashed > 0:
            status = Text()
            status.append(f"Hashed {hash_result.hashed} files", style="bold green")
            status.append(f"  ·  {hash_result.skipped_unique} skipped (unique sizes)", style="dim")
            console.print(Align.center(status))
            console.print()


@app.command()
def stats(
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Folder name to show (default: last scanned)"),
    all_folders: bool = typer.Option(False, "--all", "-a", help="Show combined stats for all indexed folders"),
):
    """Dashboard: total files, space usage, duplicates, junk, and health score."""
    db = get_db()
    if all_folders:
        folder_id, folder_paths = None, _folders(db)
    else:
        folder_id, folder_paths = _active_folder(db, folder)
        if not folder_paths:
            console.print("[yellow]No folders indexed yet. Run:[/yellow] ordra scan <folder>")
            raise typer.Exit()
    summary = duplicates.get_space_summary(db, folder_id=folder_id)
    tables.render_stats(summary, console, folders=folder_paths)


@app.command()
def dupes(
    min_size: int = typer.Option(0, "--min-size", help="Minimum wasted bytes to show"),
    limit: int = typer.Option(50, "--limit", help="Max duplicate groups to show"),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Folder name to show (default: last scanned)"),
    all_folders: bool = typer.Option(False, "--all", "-a", help="Show duplicates across all indexed folders"),
):
    """List all duplicate file groups with wasted space breakdown."""
    db = get_db()
    if all_folders:
        folder_id, folder_paths = None, _folders(db)
    else:
        folder_id, folder_paths = _active_folder(db, folder)
        if not folder_paths:
            console.print("[yellow]No folders indexed yet. Run:[/yellow] ordra scan <folder>")
            raise typer.Exit()
    groups = duplicates.get_duplicate_groups(db, min_size=min_size, limit=limit, folder_id=folder_id)
    tables.render_duplicates(groups, console, folders=folder_paths)


@app.command()
def suggest(
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter: large | old | junk | misplaced"
    ),
    no_ai: bool = typer.Option(False, "--no-ai", help="Skip AI insights"),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Folder name to show (default: last scanned)"),
    all_folders: bool = typer.Option(False, "--all", "-a", help="Show suggestions across all indexed folders"),
):
    """Smart suggestions + AI-powered insights about your files."""
    db = get_db()
    if all_folders:
        folder_id, folder_paths = None, _folders(db)
    else:
        folder_id, folder_paths = _active_folder(db, folder)
        if not folder_paths:
            console.print("[yellow]No folders indexed yet. Run:[/yellow] ordra scan <folder>")
            raise typer.Exit()
    results = suggestions.run_suggestions(db, folder_id=folder_id)
    if category:
        results = [s for s in results if s.category == category]

    ai_stream = None if no_ai else ai_service.stream_insights(db, results)
    tables.render_suggestions(results, console, ai_stream=ai_stream, folders=folder_paths)


@app.command()
def sort(
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Target directory (default: inside scanned folder)"
    ),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Folder name to organize (default: last scanned)"),
    all_folders: bool = typer.Option(False, "--all", "-a", help="Organize all indexed folders"),
    execute: bool = typer.Option(False, "--execute", "-e", help="Actually move files (default is dry run preview)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation when using --execute"),
):
    """Preview (or execute) reorganizing files into category subfolders."""
    db = get_db()
    if all_folders:
        folder_id, folder_paths = None, _folders(db)
    else:
        folder_id, folder_paths = _active_folder(db, folder)
        if not folder_paths:
            console.print("[yellow]No folders indexed yet. Run:[/yellow] ordra scan <folder>")
            raise typer.Exit()

    # Default: organize in-place inside the scanned folder
    if output_dir:
        base = output_dir
    elif folder_id is not None:
        base = Path(folder_paths[0])
    else:
        base = Path.home() / "Organized"

    actions = sorter.build_sort_plan(db, base, folder_id=folder_id)
    tables.render_sort_plan(actions, console, folders=folder_paths, execute_mode=execute)

    if not execute:
        console.print(Align.center(Text(
            "Run  ordra sort --execute  to apply these moves",
            style="dim cyan"
        )))
        console.print()
        return

    if not actions:
        return

    if not yes:
        confirm = typer.confirm("  Move these files?", default=False)
        if not confirm:
            console.print("\n[dim]Cancelled — nothing was moved.[/dim]\n")
            raise typer.Exit()

    console.print()
    with console.status("[bold cyan]Moving files...[/bold cyan]"):
        moved, errors = sorter.execute_sort_plan(actions, db)

    from rich.panel import Panel as _Panel
    result = Text(justify="center")
    result.append(str(moved), style="bold green")
    result.append(" files organized", style="dim")
    console.print()
    console.print(Align.center(_Panel(result, border_style="green", padding=(0, 4))))

    if errors:
        console.print(f"\n[yellow]  {len(errors)} errors:[/yellow]")
        for e in errors:
            console.print(f"  [dim red]> {e}[/dim red]")

    console.print()
    console.print(Align.center(Text("Run  ordra scan <folder>  to update the index", style="dim cyan")))
    console.print()


@app.command()
def folders():
    """List all folders currently tracked in the database."""
    db = get_db()
    rows = db.execute(
        """SELECT wf.id, wf.path, wf.last_scan,
                  COUNT(f.id) AS file_count
           FROM watched_folders wf
           LEFT JOIN files f ON f.folder_id = wf.id
           GROUP BY wf.id
           ORDER BY wf.added_at DESC"""
    ).fetchall()
    tables.render_folders(rows, console)


@app.command()
def clean(
    dupes: bool = typer.Option(True,  "--dupes/--no-dupes",      help="Include duplicate files"),
    installers: bool = typer.Option(True, "--installers/--no-installers", help="Include old installers"),
    days: int = typer.Option(180, "--days", help="Age threshold for installers (default 180 days)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Folder name to clean (default: last scanned)"),
    all_folders: bool = typer.Option(False, "--all", "-a", help="Clean across all indexed folders"),
):
    """Preview and delete duplicates + old installers. Files go to Recycle Bin."""
    from rich.table import Table
    from rich import box as rbox

    db = get_db()
    if all_folders:
        folder_id, folder_paths = None, _folders(db)
    else:
        folder_id, folder_paths = _active_folder(db, folder)
        if not folder_paths:
            console.print("[yellow]No folders indexed yet. Run:[/yellow] ordra scan <folder>")
            raise typer.Exit()
    items: list = []

    if dupes:
        dupe_items = cleaner.plan_dupe_deletions(db, folder_id=folder_id)
        items.extend(dupe_items)

    if installers:
        installer_items = cleaner.plan_old_installer_deletions(db, days=days, folder_id=folder_id)
        items.extend(installer_items)

    if not items:
        console.print("\n[green]Nothing to clean — already spotless.[/green]\n")
        raise typer.Exit()

    total_bytes = sum(i.size_bytes for i in items)

    # Preview table
    console.print()
    console.print(Rule("[bold cyan]◈  ORDRA  ·  Clean Preview[/bold cyan]", style="dim cyan"))
    console.print()

    dupe_list   = [i for i in items if "Duplicate" in i.reason]
    inst_list   = [i for i in items if "installer" in i.reason]

    if dupe_list:
        console.print(f"  [bold red]Duplicates[/bold red]  [dim]{len(dupe_list)} files[/dim]")
        t = Table.grid(padding=(0, 2))
        t.add_column(width=2)
        t.add_column(max_width=52, overflow="ellipsis")
        t.add_column(justify="right", width=10)
        for i in dupe_list:
            t.add_row("[dim red]>[/dim red]", i.path.name, f"[dim]{tables.fmt_bytes(i.size_bytes)}[/dim]")
        console.print(t)
        console.print()

    if inst_list:
        console.print(f"  [bold yellow]Old Installers[/bold yellow]  [dim]{len(inst_list)} files[/dim]")
        t = Table.grid(padding=(0, 2))
        t.add_column(width=2)
        t.add_column(max_width=52, overflow="ellipsis")
        t.add_column(justify="right", width=10)
        for i in inst_list:
            t.add_row("[dim yellow]>[/dim yellow]", i.path.name, f"[dim]{tables.fmt_bytes(i.size_bytes)}[/dim]")
        console.print(t)
        console.print()

    # Summary banner
    summary = Text(justify="center")
    summary.append(str(len(items)), style="bold red")
    summary.append(" files  |  ", style="dim")
    summary.append(tables.fmt_bytes(total_bytes), style="bold green")
    summary.append(" freed  |  ", style="dim")
    summary.append("sent to Recycle Bin (recoverable)", style="dim")
    console.print(Align.center(Panel(summary, border_style="yellow", padding=(0, 4))))
    console.print()

    # Confirm
    if not yes:
        confirm = typer.confirm("  Proceed?", default=False)
        if not confirm:
            console.print("\n[dim]Cancelled — nothing was deleted.[/dim]\n")
            raise typer.Exit()

    # Execute
    console.print()
    with console.status("[bold cyan]Moving files to Recycle Bin...[/bold cyan]"):
        deleted, freed, errors = cleaner.execute_deletions(items, db)

    # Result
    console.print()
    result = Text(justify="center")
    result.append(str(deleted), style="bold green")
    result.append(" files moved to Recycle Bin  |  ", style="dim")
    result.append(tables.fmt_bytes(freed), style="bold green")
    result.append(" freed", style="dim")
    console.print(Align.center(Panel(result, border_style="green", padding=(0, 4))))

    if errors:
        console.print(f"\n[yellow]  {len(errors)} errors:[/yellow]")
        for e in errors:
            console.print(f"  [dim red]> {e}[/dim red]")

    console.print()
    console.print(Align.center(Text("Run  ordra stats  to see your updated score", style="dim cyan")))
    console.print()


@app.command()
def chat(
    question: str = typer.Argument(..., help="Ask anything about your files"),
):
    """Ask Ordra's AI anything about your indexed files in plain English."""
    db = get_db()

    console.print()
    console.print(Rule("[bold cyan][*] Ordra AI[/bold cyan]", style="dim cyan"))
    console.print()
    console.print(f"[dim]You:[/dim] {question}")
    console.print()
    console.print("[dim]Ordra:[/dim] ", end="")

    for chunk in ai_service.stream_chat(db, question):
        console.print(chunk, end="")

    console.print()
    console.print()


@app.command()
def version():
    """Show the installed Ordra version and check PyPI for updates."""
    import json
    import urllib.request
    from importlib.metadata import version as _pkg_version, PackageNotFoundError

    try:
        current = _pkg_version("ordra")
    except PackageNotFoundError:
        current = "dev"

    console.print()
    console.print(f"  [bold cyan]◈  ORDRA[/bold cyan]  [dim]version[/dim]  [bold white]{current}[/bold white]")

    try:
        url = "https://pypi.org/pypi/ordra/json"
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
            data = json.loads(resp.read())
        latest = data["info"]["version"]
        if latest != current:
            console.print(f"  [yellow]Update available:[/yellow] {latest}  →  run [cyan]ordra update[/cyan]")
        else:
            console.print("  [green]You are on the latest version.[/green]")
    except Exception:
        console.print("  [dim](Could not reach PyPI to check for updates.)[/dim]")

    console.print()


@app.command()
def update():
    """Upgrade Ordra to the latest version from PyPI."""
    import subprocess
    import sys

    console.print()
    with console.status("[bold cyan]Checking for updates...[/bold cyan]"):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "ordra"],
            capture_output=True,
            text=True,
        )

    if result.returncode == 0:
        console.print("[bold green]Ordra updated successfully.[/bold green]")
        console.print("[dim]Restart your terminal for changes to take effect.[/dim]")
    else:
        console.print("[red]Update failed.[/red]")
        console.print(result.stderr.strip())
    console.print()


if __name__ == "__main__":
    app()
