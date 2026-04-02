import time as _time
from pathlib import Path

from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

from file_organizer.services.duplicates import DuplicateGroup, SpaceSummary
from file_organizer.services.scanner import ScanResult
from file_organizer.services.suggestions import Suggestion
from file_organizer.services.sorter import SortAction


# ── Helpers ────────────────────────────────────────────────────────────────

def fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b //= 1024
    return f"{b:.1f} PB"


def _health_score(summary: SpaceSummary) -> int:
    if summary.total_size_bytes == 0:
        return 100
    waste_ratio = summary.reclaimable_bytes / summary.total_size_bytes
    score = max(0, int(100 - (waste_ratio * 120)))
    return min(100, score)


def _score_color(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def _score_label(score: int) -> str:
    if score >= 80:
        return "CLEAN"
    if score >= 60:
        return "GOOD"
    if score >= 40:
        return "NEEDS ATTENTION"
    return "CRITICAL"


def _bar(filled: int, total: int = 20, color: str = "cyan") -> Text:
    f = min(filled, total)
    bar = Text()
    bar.append("\u2588" * f, style=f"bold {color}")
    bar.append("\u2591" * (total - f), style="dim")
    return bar


def _ordra_header(console: Console, subtitle: str = "", folders: list[str] | None = None) -> None:
    console.print()
    title = Text("[*] ORDRA", style="bold cyan")
    if subtitle:
        title.append(f"  |  {subtitle}", style="dim white")
    console.print(Align.center(title))
    console.print(Align.center(Rule(style="dim cyan")))

    if folders:
        home = str(Path.home())
        short = [f.replace(home, "~") for f in folders]
        folder_text = Text(justify="center")
        folder_text.append("Folder: " if len(short) == 1 else "Folders: ", style="dim")
        folder_text.append("  |  ".join(short), style="bold white")
        console.print(Align.center(folder_text))

    console.print()


# ── Scan Result ────────────────────────────────────────────────────────────

def render_scan_result(result: ScanResult, console: Console, folders: list[str] | None = None) -> None:
    _ordra_header(console, "Scan Complete", folders)

    cols = Columns([
        _stat_cell("NEW", str(result.new), "green"),
        _stat_cell("UPDATED", str(result.updated), "yellow"),
        _stat_cell("REMOVED", str(result.deleted), "red"),
        _stat_cell("UNCHANGED", str(result.skipped), "dim"),
        _stat_cell("TOTAL", str(result.total), "cyan"),
        _stat_cell("TIME", f"{result.elapsed:.2f}s", "white"),
    ], equal=True, expand=True)

    console.print(Panel(cols, border_style="cyan", padding=(1, 2)))
    console.print()


def _stat_cell(label: str, value: str, color: str) -> Panel:
    content = Text(justify="center")
    content.append(f"{value}\n", style=f"bold {color}")
    content.append(label, style="dim")
    return Panel(content, border_style="dim", padding=(0, 1))


# ── Storage Stats ──────────────────────────────────────────────────────────

def render_stats(summary: SpaceSummary, console: Console, folders: list[str] | None = None) -> None:
    _ordra_header(console, "Storage Analysis", folders)

    score = _health_score(summary)
    sc = _score_color(score)
    sl = _score_label(score)

    # Top stats row
    info = Text(justify="center")
    info.append(f"{summary.total_files:,}", style="bold white")
    info.append(" files   ·   ", style="dim")
    info.append(fmt_bytes(summary.total_size_bytes), style="bold white")
    info.append(" on disk", style="dim")
    console.print(Align.center(info))
    console.print()

    if summary.reclaimable_bytes > 0:
        # Big reclaim number
        reclaim = Text(justify="center")
        reclaim.append(fmt_bytes(summary.reclaimable_bytes), style=f"bold red")
        reclaim.append("  reclaimable right now", style="bold white")
        console.print(Align.center(Panel(reclaim, border_style="red", padding=(1, 4))))
        console.print()

    # Breakdown bars
    breakdown = Table.grid(padding=(0, 2))
    breakdown.add_column(justify="right", style="dim", width=14)
    breakdown.add_column(width=22)
    breakdown.add_column(justify="right", width=10)

    if summary.duplicate_wasted_bytes > 0:
        pct = summary.duplicate_wasted_bytes / max(summary.total_size_bytes, 1)
        filled = int(pct * 20)
        breakdown.add_row("Duplicates", _bar(filled, color="red"), f"[red]{fmt_bytes(summary.duplicate_wasted_bytes)}[/red]")

    if summary.junk_bytes > 0:
        pct = summary.junk_bytes / max(summary.total_size_bytes, 1)
        filled = max(1, int(pct * 20))
        breakdown.add_row("Junk files", _bar(filled, color="yellow"), f"[yellow]{fmt_bytes(summary.junk_bytes)}[/yellow]")

    if summary.total_size_bytes > 0:
        clean = summary.total_size_bytes - summary.reclaimable_bytes
        pct = clean / summary.total_size_bytes
        filled = int(pct * 20)
        breakdown.add_row("Clean files", _bar(filled, color="green"), f"[green]{fmt_bytes(clean)}[/green]")

    console.print(Panel(breakdown, title="[dim]Breakdown[/dim]", border_style="dim", padding=(1, 2)))
    console.print()

    # Health score
    score_bar = _bar(score // 5, color=sc)
    score_text = Text()
    score_text.append("Folder Health  ", style="dim")
    score_text.append(str(score), style=f"bold {sc}")
    score_text.append("/100  ", style="dim")
    score_text.append(sl, style=f"bold {sc}")
    console.print(Align.center(score_text))
    console.print()

    # Next action hint
    if summary.reclaimable_bytes > 0:
        hint = Text(justify="center")
        hint.append("→ Run  ", style="dim")
        hint.append("ordra dupes", style="bold cyan")
        hint.append("  and  ", style="dim")
        hint.append("ordra suggest", style="bold cyan")
        hint.append("  to see exactly what to delete", style="dim")
        console.print(Align.center(hint))
        console.print()


# ── Duplicates ─────────────────────────────────────────────────────────────

def render_duplicates(groups: list[DuplicateGroup], console: Console, folders: list[str] | None = None) -> None:
    _ordra_header(console, "Duplicate Files", folders)

    if not groups:
        console.print(Align.center(Text("No duplicates found — your folder is clean.", style="green")))
        console.print()
        return

    total_waste = sum(g.wasted_bytes for g in groups)

    # Summary banner
    banner = Text(justify="center")
    banner.append(fmt_bytes(total_waste), style="bold red")
    banner.append(" wasted in ", style="white")
    banner.append(str(len(groups)), style="bold red")
    banner.append(" duplicate groups", style="white")
    console.print(Align.center(Panel(banner, border_style="red", padding=(0, 4))))
    console.print()

    for i, g in enumerate(groups, 1):
        waste_text = Text()
        waste_text.append(f"  #{i}  ", style="dim")
        waste_text.append(fmt_bytes(g.wasted_bytes), style="bold red")
        waste_text.append(f"  wasted  ·  {g.file_count} copies  ·  ", style="dim")
        waste_text.append(g.sha256, style="dim cyan")
        console.print(waste_text)

        for j, member in enumerate(g.members):
            prefix = "  \\-" if j == len(g.members) - 1 else "  +-"
            line = Text()
            line.append(prefix, style="dim")
            name = member.name
            parent = str(member.parent).replace(str(Path.home()), "~")
            line.append(name, style="bold white")
            line.append(f"  {parent}", style="dim")
            line.append(f"  {fmt_bytes(g.size_bytes)}", style="cyan")
            console.print(line)
        console.print()

    # Action hint
    hint = Text(justify="center")
    hint.append("Keep one copy of each group and delete the rest ", style="dim")
    hint.append(f"to free {fmt_bytes(total_waste)}", style="bold green")
    console.print(Align.center(hint))
    console.print()


# ── Suggestions ────────────────────────────────────────────────────────────

CATEGORY_CONFIG = {
    "large":     ("red",     "LARGE",     "Large files eating your space"),
    "old":       ("yellow",  "OLD",       "Files not touched in over a year"),
    "junk":      ("magenta", "JUNK",      "System junk and temp files"),
    "misplaced": ("blue",    "MISPLACED", "Files in the wrong folder"),
}


def render_suggestions(suggestions: list[Suggestion], console: Console, ai_stream=None, folders: list[str] | None = None) -> None:
    _ordra_header(console, "Smart Suggestions", folders)

    if not suggestions:
        console.print(Align.center(Text("Your folder looks clean — nothing to suggest!", style="green")))
        console.print()
        return

    total_savings = sum(s.potential_bytes for s in suggestions)
    count = len(suggestions)

    # Summary
    summary_text = Text(justify="center")
    summary_text.append(str(count), style="bold yellow")
    summary_text.append(" issues found  ·  up to ", style="white")
    summary_text.append(fmt_bytes(total_savings), style="bold red")
    summary_text.append(" recoverable", style="white")
    console.print(Align.center(Panel(summary_text, border_style="yellow", padding=(0, 4))))
    console.print()

    # Group by category
    by_cat: dict[str, list[Suggestion]] = {}
    for s in suggestions:
        by_cat.setdefault(s.category, []).append(s)

    for cat in ("large", "junk", "old", "misplaced"):
        items = by_cat.get(cat, [])
        if not items:
            continue
        color, label, desc = CATEGORY_CONFIG.get(cat, ("white", cat.upper(), ""))
        cat_savings = sum(s.potential_bytes for s in items)

        header = Text()
        header.append(f"  {label}", style=f"bold {color}")
        header.append(f"  ·  {len(items)} files", style="dim")
        if cat_savings > 0:
            header.append(f"  ·  {fmt_bytes(cat_savings)}", style=f"bold {color}")
        console.print(header)
        console.print(Text(f"  {desc}", style="dim"))

        t = Table.grid(padding=(0, 2))
        t.add_column(width=2)
        t.add_column(max_width=50, overflow="ellipsis")
        t.add_column(justify="right", width=10)

        for s in items[:8]:
            name = Path(s.path).name if s.path else "-"
            size_str = fmt_bytes(s.potential_bytes) if s.potential_bytes else ""
            t.add_row(
                Text(">", style=f"dim {color}"),
                Text(name, style="white"),
                Text(size_str, style=f"dim {color}"),
            )

        if len(items) > 8:
            t.add_row("", Text(f"... and {len(items)-8} more", style="dim"), "")

        console.print(t)
        console.print()

    # AI Insights section
    if ai_stream is not None:
        console.print(Rule("[bold cyan][*] AI Insights[/bold cyan]", style="dim cyan"))
        console.print()
        ai_text = Text()
        with Live(ai_text, console=console, refresh_per_second=12) as live:
            for chunk in ai_stream:
                ai_text.append(chunk, style="italic white")
                live.update(ai_text)
        console.print()
        console.print()


# ── Sort Plan ──────────────────────────────────────────────────────────────

def render_sort_plan(actions: list[SortAction], console: Console, folders: list[str] | None = None, execute_mode: bool = False) -> None:
    mode_label = "Sort Plan  ·  LIVE" if execute_mode else "Sort Plan  ·  DRY RUN"
    _ordra_header(console, mode_label, folders)

    if not execute_mode:
        console.print(Align.center(Text("No files will be moved — this is a preview only.", style="dim yellow")))
        console.print()

    if not actions:
        console.print(Align.center(Text("Nothing to sort.", style="green")))
        return

    by_cat: dict[str, list[SortAction]] = {}
    for a in actions:
        by_cat.setdefault(a.category, []).append(a)

    t = Table(box=box.ROUNDED, show_header=True, border_style="dim")
    t.add_column("Category", style="bold cyan", width=14)
    t.add_column("Files", justify="right", width=8)
    t.add_column("Example destination", style="dim", overflow="fold")

    for cat, items in sorted(by_cat.items()):
        dest = str(items[0].destination.parent).replace(str(Path.home()), "~")
        t.add_row(cat, str(len(items)), dest)

    console.print(t)
    console.print()

    summary = Text(justify="center")
    summary.append(str(len(actions)), style="bold cyan")
    summary.append(" files would be reorganized into ", style="dim")
    summary.append(str(len(by_cat)), style="bold cyan")
    summary.append(" category folders", style="dim")
    console.print(Align.center(summary))
    console.print()


# ── Folders ────────────────────────────────────────────────────────────────

def render_folders(rows: list, console: Console) -> None:
    _ordra_header(console, "Watched Folders")

    if not rows:
        console.print(Align.center(Text("No folders indexed yet.", style="dim")))
        console.print(Align.center(Text("Run: ordra scan <folder>", style="cyan")))
        console.print()
        return

    t = Table(box=box.ROUNDED, border_style="dim")
    t.add_column("#", style="dim", width=4)
    t.add_column("Path", style="cyan")
    t.add_column("Files", justify="right", width=8)
    t.add_column("Last Scan", width=18)

    for r in rows:
        last = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(r["last_scan"])) if r["last_scan"] else "Never"
        t.add_row(str(r["id"]), r["path"], str(r["file_count"]), last)

    console.print(t)
    console.print()
