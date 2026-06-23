"""Ordra TUI — interactive terminal interface built with Textual."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)
from textual import on, work


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b //= 1024
    return f"{b:.1f} PB"


def _score(total: int, reclaimable: int) -> int:
    if total == 0:
        return 100
    return max(0, min(100, int(100 - (reclaimable / total) * 120)))


def _score_color(s: int) -> str:
    return "green" if s >= 80 else "yellow" if s >= 50 else "red"


def _score_label(s: int) -> str:
    if s >= 80: return "CLEAN"
    if s >= 60: return "GOOD"
    if s >= 40: return "NEEDS ATTENTION"
    return "CRITICAL"


# ── CSS ───────────────────────────────────────────────────────────────────────

APP_CSS = """
Screen {
    background: #0d1117;
}

Header {
    background: #161b22;
    color: #58a6ff;
    text-style: bold;
    height: 1;
}

Footer {
    background: #161b22;
    color: #8b949e;
    height: 1;
}

TabbedContent ContentTabs {
    background: #161b22;
    color: #8b949e;
    height: 2;
}

TabbedContent Tab {
    background: #161b22;
    color: #8b949e;
    padding: 0 2;
}

TabbedContent Tab.-active {
    color: #58a6ff;
    background: #0d1117;
    text-style: bold;
    border-bottom: none;
}

TabPane {
    background: #0d1117;
    padding: 1 2;
}

.section-title {
    color: #58a6ff;
    text-style: bold;
    width: 1fr;
    padding: 0 0 1 0;
}

.stat-card {
    border: round #30363d;
    padding: 1 2;
    width: 1fr;
    height: 6;
    content-align: center middle;
    text-align: center;
    margin-right: 1;
    background: #161b22;
}

#dash-health {
    border: round #238636;
    padding: 1 2;
    text-align: center;
    content-align: center middle;
    height: 5;
    margin-bottom: 1;
    background: #0f2a14;
}

#dash-stats-row {
    height: 6;
    margin-bottom: 1;
}

#dash-extra-row {
    height: 6;
    margin-bottom: 1;
}

.btn-row {
    height: 3;
    margin-top: 1;
    align: left middle;
}

Button {
    margin-right: 1;
    border: none;
}

Button:hover {
    border: none;
}

Button.btn-primary {
    background: #1f6feb;
    color: white;
}

Button.btn-danger {
    background: #da3633;
    color: white;
}

#scan-input-row {
    height: 3;
    margin-bottom: 1;
}

#scan-path-input {
    width: 1fr;
    margin-right: 1;
    background: #161b22;
    border: tall #30363d;
    color: white;
}

#scan-path-input:focus {
    border: tall #58a6ff;
}

#scan-msg {
    height: auto;
    margin: 1 0;
    color: #8b949e;
}

#dupes-table {
    height: 14;
    background: #0d1117;
    border: round #30363d;
}

#dupes-detail {
    border: round #30363d;
    padding: 1 2;
    height: 10;
    margin: 1 0;
    background: #161b22;
    color: #e6edf3;
}

DataTable {
    background: #0d1117;
    border: round #30363d;
}

DataTable > .datatable--header {
    background: #161b22;
    color: #58a6ff;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1f6feb;
    color: white;
}

DataTable > .datatable--even-row {
    background: #0d1117;
}

DataTable > .datatable--odd-row {
    background: #161b22;
}

#suggest-summary {
    margin: 0 0 1 0;
    color: #8b949e;
    height: auto;
}

#chat-history {
    height: 1fr;
    border: round #30363d;
    padding: 1 2;
    margin-bottom: 1;
    background: #161b22;
    scrollbar-color: #30363d;
}

#chat-streaming {
    height: auto;
    min-height: 2;
    border: round #1f6feb;
    padding: 0 2;
    margin-bottom: 1;
    background: #0c1929;
}

#chat-input-row {
    height: 3;
}

#chat-input {
    width: 1fr;
    margin-right: 1;
    background: #161b22;
    border: tall #30363d;
    color: white;
}

#chat-input:focus {
    border: tall #58a6ff;
}

Label {
    color: #e6edf3;
}

Input {
    background: #161b22;
    border: tall #30363d;
    color: white;
}

Input:focus {
    border: tall #58a6ff;
}
"""


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardPane(TabPane):

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="dash-health")
            with Horizontal(id="dash-stats-row"):
                yield Static("", id="dash-files", classes="stat-card")
                yield Static("", id="dash-size", classes="stat-card")
                yield Static("", id="dash-reclaim", classes="stat-card")
            with Horizontal(id="dash-extra-row"):
                yield Static("", id="dash-dupes", classes="stat-card")
                yield Static("", id="dash-junk", classes="stat-card")
            with Horizontal(classes="btn-row"):
                yield Button("Scan Folder", id="dash-scan-btn", variant="primary")
                yield Button("View Duplicates", id="dash-dupes-btn", variant="default")
                yield Button("Suggestions", id="dash-suggest-btn", variant="default")
                yield Button("Chat with AI", id="dash-chat-btn", variant="default")

    def on_mount(self) -> None:
        self.refresh_stats()

    def refresh_stats(self) -> None:
        try:
            from file_organizer.db.connection import get_db
            from file_organizer.services.duplicates import get_space_summary, get_duplicate_groups
            db = get_db()
            s = get_space_summary(db)

            if s.total_files == 0:
                self.query_one("#dash-health", Static).update(
                    "[dim]No files indexed yet.[/dim]\n"
                    "[cyan]→ Click  Scan Folder  to get started[/cyan]"
                )
                for wid in ("#dash-files", "#dash-size", "#dash-reclaim", "#dash-dupes", "#dash-junk"):
                    self.query_one(wid, Static).update("[dim]—[/dim]")
                return

            sc = _score(s.total_size_bytes, s.reclaimable_bytes)
            color = _score_color(sc)
            label = _score_label(sc)
            bar = "█" * (sc // 5) + "░" * (20 - sc // 5)

            self.query_one("#dash-health", Static).update(
                f"  [bold {color}]{sc}[/bold {color}] [dim]/ 100  ·[/dim]  "
                f"[bold {color}]{label}[/bold {color}]\n"
                f"  [{color}]{bar}[/{color}]"
            )
            self.query_one("#dash-files", Static).update(
                f"[bold white]{s.total_files:,}[/bold white]\n[dim]files[/dim]"
            )
            self.query_one("#dash-size", Static).update(
                f"[bold white]{_fmt(s.total_size_bytes)}[/bold white]\n[dim]on disk[/dim]"
            )
            self.query_one("#dash-reclaim", Static).update(
                f"[bold red]{_fmt(s.reclaimable_bytes)}[/bold red]\n[dim]reclaimable[/dim]"
            )
            groups = get_duplicate_groups(db)
            self.query_one("#dash-dupes", Static).update(
                f"[bold yellow]{len(groups)}[/bold yellow] [dim]dup groups[/dim]\n"
                f"[dim]{_fmt(s.duplicate_wasted_bytes)} wasted[/dim]"
            )
            self.query_one("#dash-junk", Static).update(
                f"[bold magenta]{_fmt(s.junk_bytes)}[/bold magenta]\n[dim]junk files[/dim]"
            )
        except Exception:
            self.query_one("#dash-health", Static).update(
                "[dim]Ready. Scan a folder to begin.[/dim]"
            )

    @on(Button.Pressed, "#dash-scan-btn")
    def go_scan(self) -> None:
        self.app.query_one(TabbedContent).active = "tab-scan"

    @on(Button.Pressed, "#dash-dupes-btn")
    def go_dupes(self) -> None:
        self.app.query_one(TabbedContent).active = "tab-dupes"

    @on(Button.Pressed, "#dash-suggest-btn")
    def go_suggest(self) -> None:
        self.app.query_one(TabbedContent).active = "tab-suggest"

    @on(Button.Pressed, "#dash-chat-btn")
    def go_chat(self) -> None:
        self.app.query_one(TabbedContent).active = "tab-chat"


# ── Scan ──────────────────────────────────────────────────────────────────────

class ScanPane(TabPane):

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Scan a Folder", classes="section-title")
            with Horizontal(id="scan-input-row"):
                yield Input(
                    placeholder="Enter path — e.g. ~/Downloads  or  /home/user/Documents",
                    id="scan-path-input",
                )
                yield Button("Scan", id="scan-btn", variant="primary")
            yield Static("", id="scan-msg")

    @on(Input.Submitted, "#scan-path-input")
    def submit_on_enter(self) -> None:
        self._start_scan()

    @on(Button.Pressed, "#scan-btn")
    def submit_on_click(self) -> None:
        self._start_scan()

    def _start_scan(self) -> None:
        raw = self.query_one("#scan-path-input", Input).value.strip()
        if not raw:
            return
        raw = raw.replace("~", str(Path.home()))
        p = Path(raw)
        if not p.exists() or not p.is_dir():
            self.query_one("#scan-msg", Static).update(
                f"[red]Error:[/red] '{raw}' is not a valid directory."
            )
            return
        self.query_one("#scan-btn", Button).disabled = True
        self.query_one("#scan-msg", Static).update(
            "[bold cyan]Scanning...[/bold cyan]  "
            "[dim]This may take a few minutes for large folders.[/dim]"
        )
        self._run_scan(str(p))

    @work(thread=True)
    def _run_scan(self, path: str) -> None:
        import io
        from rich.console import Console as RichConsole
        from file_organizer.db.connection import get_connection
        from file_organizer.services import scanner, hasher

        db = get_connection()
        console = RichConsole(file=io.StringIO(), highlight=False)
        result = scanner.scan_folder(Path(path), db, console)
        hash_result = hasher.hash_unprocessed(db, console)

        def done() -> None:
            self.query_one("#scan-msg", Static).update(
                f"[bold green]Scan complete[/bold green]\n\n"
                f"  [green]+{result.new}[/green] new   "
                f"[yellow]~{result.updated}[/yellow] updated   "
                f"[red]-{result.deleted}[/red] removed   "
                f"[dim]{result.skipped} unchanged[/dim]\n\n"
                f"  [bold]{result.total:,}[/bold] total files   "
                f"[cyan]{hash_result.hashed}[/cyan] hashed   "
                f"[dim]{result.elapsed:.1f}s[/dim]\n\n"
                f"  [dim cyan]→ Switch to Dashboard to see your health score[/dim cyan]"
            )
            self.query_one("#scan-btn", Button).disabled = False
            try:
                self.app.query_one(DashboardPane).refresh_stats()
            except Exception:
                pass

        self.app.call_from_thread(done)


# ── Duplicates ────────────────────────────────────────────────────────────────

class DupesPane(TabPane):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._groups: list = []
        self._selected: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(classes="btn-row"):
                yield Label("Duplicate Files", classes="section-title")
                yield Button("Refresh", id="dupes-refresh-btn", variant="default")
            yield DataTable(id="dupes-table", zebra_stripes=True, cursor_type="row")
            yield Static("", id="dupes-detail")
            with Horizontal(classes="btn-row"):
                yield Button(
                    "Delete Duplicates  (keep first copy)",
                    id="dupes-delete-btn",
                    variant="error",
                    disabled=True,
                )

    def on_mount(self) -> None:
        t = self.query_one("#dupes-table", DataTable)
        t.add_column("  #", width=5)
        t.add_column("Copies", width=7)
        t.add_column("Wasted", width=12)
        t.add_column("Example filename", width=46)
        self._load()

    def _load(self) -> None:
        try:
            from file_organizer.db.connection import get_db
            from file_organizer.services.duplicates import get_duplicate_groups
            db = get_db()
            self._groups = get_duplicate_groups(db)
            t = self.query_one("#dupes-table", DataTable)
            t.clear()
            detail = self.query_one("#dupes-detail", Static)

            if not self._groups:
                detail.update("[green]No duplicates found — your files are clean![/green]")
                return

            total_waste = sum(g.wasted_bytes for g in self._groups)
            detail.update(
                f"[bold red]{len(self._groups)}[/bold red] duplicate groups  ·  "
                f"[bold]{_fmt(total_waste)}[/bold] wasted  ·  "
                f"[dim]click a row to see group members[/dim]"
            )
            for i, g in enumerate(self._groups, 1):
                name = g.members[0].name if g.members else "?"
                t.add_row(f"#{i}", str(g.file_count), _fmt(g.wasted_bytes), name, key=str(i - 1))
        except Exception as e:
            self.query_one("#dupes-detail", Static).update(f"[red]{e}[/red]")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            idx = int(str(event.row_key.value))
            self._selected = idx
            g = self._groups[idx]
            home = str(Path.home())
            lines = [
                f"[bold]Group #{idx + 1}[/bold]  ·  "
                f"{g.file_count} copies  ·  "
                f"[red]{_fmt(g.wasted_bytes)}[/red] wasted\n"
            ]
            for j, m in enumerate(g.members):
                parent = str(m.parent).replace(home, "~")
                connector = "└─" if j == len(g.members) - 1 else "├─"
                keep = "  [dim green]← keep[/dim green]" if j == 0 else ""
                lines.append(
                    f"  {connector} [bold white]{m.name}[/bold white]  "
                    f"[dim]{parent}[/dim]  "
                    f"[cyan]{_fmt(g.size_bytes)}[/cyan]{keep}"
                )
            self.query_one("#dupes-detail", Static).update("\n".join(lines))
            self.query_one("#dupes-delete-btn", Button).disabled = False
        except Exception:
            pass

    @on(Button.Pressed, "#dupes-refresh-btn")
    def refresh(self) -> None:
        self._selected = None
        self.query_one("#dupes-delete-btn", Button).disabled = True
        self._load()

    @on(Button.Pressed, "#dupes-delete-btn")
    def delete_selected(self) -> None:
        if self._selected is None:
            return
        try:
            from file_organizer.db.connection import get_db
            from file_organizer.services.cleaner import plan_dupe_deletions, execute_deletions
            db = get_db()
            g = self._groups[self._selected]
            all_items = plan_dupe_deletions(db)
            member_paths = {m for m in g.members}
            to_delete = [item for item in all_items if item.path in member_paths]
            if not to_delete:
                self.query_one("#dupes-detail", Static).update(
                    "[yellow]No candidates found for this group (all copies may already be gone).[/yellow]"
                )
                return
            deleted, freed, errors = execute_deletions(to_delete, db)
            msg = (
                f"[bold green]Deleted {deleted} file(s)  ·  freed {_fmt(freed)}[/bold green]"
            )
            if errors:
                msg += f"\n[yellow]{len(errors)} error(s): {errors[0]}[/yellow]"
            self.query_one("#dupes-detail", Static).update(msg)
            self._selected = None
            self.query_one("#dupes-delete-btn", Button).disabled = True
            self._load()
            try:
                self.app.query_one(DashboardPane).refresh_stats()
            except Exception:
                pass
        except Exception as e:
            self.query_one("#dupes-detail", Static).update(f"[red]Error: {e}[/red]")


# ── Suggestions ───────────────────────────────────────────────────────────────

class SuggestionsPane(TabPane):

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(classes="btn-row"):
                yield Label("Smart Suggestions", classes="section-title")
                yield Button("Analyze", id="suggest-run-btn", variant="primary")
            yield Static("", id="suggest-summary")
            with TabbedContent(initial="tab-s-large"):
                with TabPane("Large Files", id="tab-s-large"):
                    yield DataTable(id="tbl-large", zebra_stripes=True, cursor_type="row")
                with TabPane("Old Files", id="tab-s-old"):
                    yield DataTable(id="tbl-old", zebra_stripes=True, cursor_type="row")
                with TabPane("Junk", id="tab-s-junk"):
                    yield DataTable(id="tbl-junk", zebra_stripes=True, cursor_type="row")
                with TabPane("Misplaced", id="tab-s-mis"):
                    yield DataTable(id="tbl-mis", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        for tbl_id in ("large", "old", "junk", "mis"):
            t = self.query_one(f"#tbl-{tbl_id}", DataTable)
            t.add_column("Filename", width=38)
            t.add_column("Size", width=12)
            t.add_column("Detail", width=32)

    @on(Button.Pressed, "#suggest-run-btn")
    def run_analysis(self) -> None:
        try:
            from file_organizer.db.connection import get_db
            from file_organizer.services.suggestions import run_suggestions
            db = get_db()
            results = run_suggestions(db)
            for tbl_id in ("large", "old", "junk", "mis"):
                self.query_one(f"#tbl-{tbl_id}", DataTable).clear()
            counts: dict[str, int] = {}
            total_bytes = 0
            cat_map = {"large": "large", "old": "old", "junk": "junk", "misplaced": "mis"}
            for s in results:
                tbl_id = cat_map.get(s.category)
                if not tbl_id:
                    continue
                t = self.query_one(f"#tbl-{tbl_id}", DataTable)
                name = Path(s.path).name if s.path else "-"
                size = _fmt(s.potential_bytes) if s.potential_bytes else "-"
                t.add_row(name, size, s.detail)
                counts[s.category] = counts.get(s.category, 0) + 1
                total_bytes += s.potential_bytes
            self.query_one("#suggest-summary", Static).update(
                f"[bold]{len(results)}[/bold] suggestions  ·  "
                f"up to [bold red]{_fmt(total_bytes)}[/bold red] recoverable  ·  "
                f"[red]{counts.get('large', 0)} large[/red]  "
                f"[magenta]{counts.get('junk', 0)} junk[/magenta]  "
                f"[yellow]{counts.get('old', 0)} old[/yellow]  "
                f"[blue]{counts.get('misplaced', 0)} misplaced[/blue]"
            )
        except Exception as e:
            self.query_one("#suggest-summary", Static).update(f"[red]Error: {e}[/red]")


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatPane(TabPane):

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("AI Chat  ·  Ask anything about your files", classes="section-title")
            yield RichLog(id="chat-history", highlight=True, markup=True, wrap=True)
            yield Static("", id="chat-streaming")
            with Horizontal(id="chat-input-row"):
                yield Input(
                    placeholder="e.g.  What should I delete first?  ·  How much space can I free?",
                    id="chat-input",
                )
                yield Button("Ask", id="chat-ask-btn", variant="primary")

    def on_mount(self) -> None:
        log = self.query_one("#chat-history", RichLog)
        log.write("[bold cyan]◈  Ordra AI[/bold cyan]  [dim]— powered by Claude[/dim]")
        log.write(
            "[dim]Ask anything about your indexed files.[/dim]\n"
            "[dim]Examples:  'What are my biggest files?'  ·  "
            "'How do I free up 10 GB?'  ·  'Show me the oldest files'[/dim]"
        )
        log.write("")

    @on(Button.Pressed, "#chat-ask-btn")
    def ask(self) -> None:
        self._send()

    @on(Input.Submitted, "#chat-input")
    def ask_on_enter(self) -> None:
        self._send()

    def _send(self) -> None:
        inp = self.query_one("#chat-input", Input)
        question = inp.value.strip()
        if not question:
            return
        inp.value = ""
        log = self.query_one("#chat-history", RichLog)
        log.write(f"[bold cyan]You:[/bold cyan]  {question}")
        streaming = self.query_one("#chat-streaming", Static)
        streaming.update("[dim]Ordra:[/dim]  [italic dim]thinking...[/italic dim]")
        self.query_one("#chat-ask-btn", Button).disabled = True
        self._stream(question)

    @work(thread=True)
    def _stream(self, question: str) -> None:
        accumulated = ""
        streaming = self.query_one("#chat-streaming", Static)
        try:
            from file_organizer.db.connection import get_db
            from file_organizer.services.ai import stream_chat
            db = get_db()
            for chunk in stream_chat(db, question):
                accumulated += chunk
                self.app.call_from_thread(
                    streaming.update,
                    f"[dim]Ordra:[/dim]  {accumulated}",
                )
        except Exception as e:
            accumulated = f"Error: {e}"

        def finalize() -> None:
            log = self.query_one("#chat-history", RichLog)
            log.write(f"[dim]Ordra:[/dim]  {accumulated}")
            log.write("")
            streaming.update("")
            self.query_one("#chat-ask-btn", Button).disabled = False

        self.app.call_from_thread(finalize)


# ── App ───────────────────────────────────────────────────────────────────────

class OrdraApp(App):
    """◈ ORDRA — Interactive TUI file organizer."""

    TITLE = "◈  ORDRA  —  The world's smartest file organizer"
    CSS = APP_CSS
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("1", "go('tab-dashboard')", "Dashboard", show=False),
        Binding("2", "go('tab-scan')", "Scan", show=False),
        Binding("3", "go('tab-dupes')", "Duplicates", show=False),
        Binding("4", "go('tab-suggest')", "Suggestions", show=False),
        Binding("5", "go('tab-chat')", "Chat", show=False),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-dashboard"):
            yield DashboardPane("Dashboard", id="tab-dashboard")
            yield ScanPane("Scan", id="tab-scan")
            yield DupesPane("Duplicates", id="tab-dupes")
            yield SuggestionsPane("Suggestions", id="tab-suggest")
            yield ChatPane("Chat", id="tab-chat")
        yield Footer()

    def action_go(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_refresh(self) -> None:
        try:
            self.query_one(DashboardPane).refresh_stats()
        except Exception:
            pass


def main() -> None:
    try:
        from textual.app import App  # noqa: F401
    except ImportError:
        print("Textual is required for the TUI.")
        print("Install it with:  pip install 'ordra[tui]'")
        raise SystemExit(1)
    OrdraApp().run()


if __name__ == "__main__":
    main()
