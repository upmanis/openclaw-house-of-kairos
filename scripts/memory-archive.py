#!/usr/bin/env python3
"""
Memory Archival & Compression Script

Two jobs:
1. Weekly digest — For files 8-30 days old, extract section headers into compact weekly summary
2. Monthly archive — For files older than 30 days, move to archive directory with index

Usage:
    python3 memory-archive.py [--dry-run] [--days-digest N] [--days-archive N]

Cron (Sundays 15:30 UTC / 23:30 WITA):
    30 15 * * 0 cd /Users/ai/openclaw/workspace && python3 scripts/memory-archive.py >> /tmp/memory-archive.log 2>&1
"""

import argparse
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Archive and digest daily memory files")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen without moving or writing files",
    )
    parser.add_argument(
        "--days-digest", type=int, default=8,
        help="Start digesting files older than N days (default: 8)",
    )
    parser.add_argument(
        "--days-archive", type=int, default=30,
        help="Archive files older than N days (default: 30)",
    )
    return parser.parse_args()


def get_memory_dir():
    """Resolve memory/ relative to this script's parent (the workspace root)."""
    return Path(__file__).resolve().parent.parent / "memory"


DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def parse_date_from_filename(name):
    m = DATE_RE.match(name)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    return None


def extract_headers(filepath):
    """Return list of ### header texts from a daily memory file."""
    headers = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("### "):
                headers.append(stripped[4:].strip())
    return headers


def iso_week_range(year, week):
    """Monday–Sunday date range for an ISO week number."""
    jan4 = datetime(year, 1, 4).date()
    week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
    monday = week1_monday + timedelta(weeks=week - 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


# ── Weekly digest ─────────────────────────────────────────────────────────────

def build_weekly_digests(files_by_week, memory_dir, dry_run):
    weekly_dir = memory_dir / "weekly"

    for (year, week), entries in sorted(files_by_week.items()):
        week_file = weekly_dir / f"{year}-W{week:02d}.md"

        if week_file.exists():
            print(f"  SKIP (exists): {week_file.name}")
            continue

        monday, sunday = iso_week_range(year, week)
        lines = [f"# Week {week} — {monday.isoformat()} to {sunday.isoformat()}\n"]

        for file_date, filepath in sorted(entries):
            headers = extract_headers(filepath)
            lines.append(f"\n## {file_date.isoformat()}")
            if headers:
                for h in headers:
                    lines.append(f"- {h}")
            else:
                lines.append("- (no sections found)")

        content = "\n".join(lines) + "\n"

        if dry_run:
            print(f"  WOULD CREATE: weekly/{week_file.name}  ({len(entries)} days)")
        else:
            weekly_dir.mkdir(parents=True, exist_ok=True)
            week_file.write_text(content, encoding="utf-8")
            print(f"  CREATED: {week_file.name}  ({len(entries)} days)")


# ── Monthly archive ───────────────────────────────────────────────────────────

def archive_files(to_archive, memory_dir, dry_run):
    archive_dir = memory_dir / "archive"
    index_updates = {}  # month_str -> [filename, ...]

    for file_date, filepath in sorted(to_archive):
        month_str = file_date.strftime("%Y-%m")
        month_dir = archive_dir / month_str
        dest = month_dir / filepath.name

        if dest.exists():
            print(f"  SKIP (already archived): {filepath.name}")
            continue

        index_updates.setdefault(month_str, []).append(filepath.name)

        if dry_run:
            print(f"  WOULD MOVE: {filepath.name} -> archive/{month_str}/")
        else:
            month_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(filepath), str(dest))
            print(f"  MOVED: {filepath.name} -> archive/{month_str}/")

    # Update index files
    for month_str, filenames in index_updates.items():
        index_file = archive_dir / month_str / "index.md"

        if dry_run:
            print(f"  WOULD UPDATE INDEX: archive/{month_str}/index.md  (+{len(filenames)} entries)")
            continue

        existing_lines = []
        if index_file.exists():
            existing_lines = index_file.read_text(encoding="utf-8").splitlines()

        if not existing_lines:
            existing_lines = [f"# Archive — {month_str}", ""]

        existing_set = set(existing_lines)
        for fname in sorted(filenames):
            entry = f"- {fname}"
            if entry not in existing_set:
                existing_lines.append(entry)

        index_file.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")
        print(f"  UPDATED INDEX: archive/{month_str}/index.md  (+{len(filenames)} entries)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    today = datetime.now().date()
    memory_dir = get_memory_dir()

    if not memory_dir.exists():
        print(f"ERROR: Memory directory not found: {memory_dir}")
        return 1

    print(f"Memory archive — {today.isoformat()}")
    print(f"  Memory dir:  {memory_dir}")
    print(f"  Digest:      >{args.days_digest} days old")
    print(f"  Archive:     >{args.days_archive} days old")
    if args.dry_run:
        print("  Mode:        DRY RUN")
    print()

    # Collect daily files (only top-level YYYY-MM-DD.md)
    daily_files = []
    for entry in memory_dir.iterdir():
        if entry.is_file():
            d = parse_date_from_filename(entry.name)
            if d:
                daily_files.append((d, entry))

    daily_files.sort()

    if not daily_files:
        print("No daily memory files found.")
        return 0

    # Categorise by age
    to_archive = []
    digest_by_week = {}

    for file_date, filepath in daily_files:
        age = (today - file_date).days

        if age > args.days_archive:
            to_archive.append((file_date, filepath))
        elif age > args.days_digest:
            year, week, _ = file_date.isocalendar()
            digest_by_week.setdefault((year, week), []).append((file_date, filepath))

    # 1. Archive old files
    if to_archive:
        print(f"ARCHIVE ({len(to_archive)} files older than {args.days_archive} days):")
        archive_files(to_archive, memory_dir, args.dry_run)
    else:
        print(f"No files to archive (none older than {args.days_archive} days).")

    print()

    # 2. Weekly digest
    if digest_by_week:
        total = sum(len(v) for v in digest_by_week.values())
        print(f"DIGEST ({total} files across {len(digest_by_week)} weeks, {args.days_digest}–{args.days_archive} days old):")
        build_weekly_digests(digest_by_week, memory_dir, args.dry_run)
    else:
        print(f"No files to digest (none {args.days_digest}–{args.days_archive} days old).")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
