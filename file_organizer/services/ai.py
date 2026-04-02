import os
import sqlite3
import time
from typing import Iterator

from file_organizer.services.duplicates import get_space_summary, get_duplicate_groups
from file_organizer.services.suggestions import Suggestion


def _fmt(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b //= 1024
    return f"{b:.1f} PB"


def stream_insights(conn: sqlite3.Connection, suggestions: list[Suggestion]) -> Iterator[str]:
    """Stream AI-powered insights about the user's files using Claude."""
    try:
        import anthropic
    except ImportError:
        yield "Install anthropic to enable AI insights: pip install anthropic\n"
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        yield "Set ANTHROPIC_API_KEY environment variable to enable AI insights.\n"
        return

    summary = get_space_summary(conn)
    dup_groups = get_duplicate_groups(conn, limit=5)

    # Build rich context from real data
    top_dupes = []
    for g in dup_groups[:3]:
        names = [m.name for m in g.members[:2]]
        top_dupes.append(f"  - {' and '.join(names)} ({_fmt(g.wasted_bytes)} wasted)")

    large_files = [s for s in suggestions if s.category == "large"][:5]
    old_files = [s for s in suggestions if s.category == "old"][:3]
    junk_files = [s for s in suggestions if s.category == "junk"]

    context = f"""
File analysis results for the user's folder:

STORAGE OVERVIEW:
- Total files: {summary.total_files:,}
- Total size: {_fmt(summary.total_size_bytes)}
- Reclaimable space: {_fmt(summary.reclaimable_bytes)}
- Duplicate waste: {_fmt(summary.duplicate_wasted_bytes)}
- Junk files: {_fmt(summary.junk_bytes)}

TOP DUPLICATE GROUPS:
{chr(10).join(top_dupes) if top_dupes else '  None found'}

LARGE FILES (top {len(large_files)}):
{chr(10).join(f"  - {s.path} ({_fmt(s.potential_bytes)})" for s in large_files) if large_files else '  None found'}

OLD FILES (not modified in 1+ year, top {len(old_files)}):
{chr(10).join(f"  - {s.path}: {s.detail}" for s in old_files) if old_files else '  None found'}

JUNK FILES: {len(junk_files)} junk files ({_fmt(sum(s.potential_bytes for s in junk_files))})
""".strip()

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are Ordra's AI assistant — a smart, direct, and slightly witty file organization expert.

Here is the analysis of the user's folder:

{context}

Write a short (4-6 sentences) personalized insight report. Be direct and specific — reference actual filenames and sizes.
Tell them exactly what to do first for maximum impact. Make them feel in control and excited to clean up.
Do NOT use bullet points. Write in flowing, confident prose. Start with the biggest win.
End with one sentence that makes them feel like this tool is indispensable."""

    try:
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"AI insights unavailable: {e}\n"


def stream_chat(conn: sqlite3.Connection, question: str) -> Iterator[str]:
    """Answer natural language questions about the user's files."""
    try:
        import anthropic
    except ImportError:
        yield "Install anthropic: pip install anthropic\n"
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        yield "Set ANTHROPIC_API_KEY to use AI chat.\n"
        return

    summary = get_space_summary(conn)

    # Pull relevant file data based on question keywords
    rows = conn.execute(
        """SELECT path, name, extension, size_bytes, mtime, is_junk, sha256
           FROM files ORDER BY size_bytes DESC LIMIT 200"""
    ).fetchall()

    file_list = "\n".join(
        f"  {r['name']} ({_fmt(r['size_bytes'])}, ext={r['extension']}, "
        f"junk={bool(r['is_junk'])}, has_duplicate={bool(r['sha256'])})"
        for r in rows[:50]
    )

    context = f"""
Database summary:
- {summary.total_files:,} total files, {_fmt(summary.total_size_bytes)} total
- {_fmt(summary.duplicate_wasted_bytes)} wasted in duplicates
- {_fmt(summary.junk_bytes)} in junk files

Sample of files (largest first):
{file_list}
"""

    client = anthropic.Anthropic(api_key=api_key)

    try:
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=600,
            system=(
                "You are Ordra, an expert AI file organizer. Answer questions about the user's "
                "files based on the database context provided. Be specific, helpful, and concise. "
                "If asked about files you don't have data for, say so honestly."
            ),
            messages=[
                {"role": "user", "content": f"File database context:\n{context}\n\nQuestion: {question}"}
            ],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"Error: {e}\n"
