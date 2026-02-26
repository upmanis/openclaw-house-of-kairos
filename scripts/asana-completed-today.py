#!/usr/bin/env python3
"""List Asana tasks completed today (WITA) for the configured HoK projects.

This is used by the End-of-Day Summary cron to avoid inline curl/python one-liners.

Output (markdown-ish):
- **[Project]:** Task name (assignee) — completed_at
"""

import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("ASANA_TOKEN")
if not TOKEN:
    print("Error: ASANA_TOKEN not set", file=sys.stderr)
    sys.exit(1)

BASE = "https://app.asana.com/api/1.0"
WITA = timezone(timedelta(hours=8))

# Projects from TOOLS.md (House of Kairos)
PROJECTS = [
    ("1208705090521783", "General Timeline"),
    ("1208771583102101", "CONSTRUCTION CHECKLIST"),
    ("1208771583102212", "F&B"),
    ("1208779826982626", "Recruitment"),
    ("1208814711748515", "CRM & Mobile App"),
    ("1208868712398357", "Marketing"),
    ("1209429425610210", "PA tasks"),
    ("1210285702711160", "Operations"),
    ("1210383979101819", "HR"),
    ("1211596101449010", "Marketing - Thumbcrumble"),
    ("1211820105476765", "Marketing - Janis Project"),
    ("1211845297723780", "Marketing - Merch"),
    ("1212602232370923", "Printed"),
    ("1213111337708211", "Marketing - Pre-sales campaign"),
    ("1213200794602805", "Architecture"),
]


def api(path: str, params: dict | None = None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"Error {e.code} calling {url}: {body}", file=sys.stderr)
        sys.exit(1)


def api_all_pages(path: str, params: dict | None = None):
    params = dict(params or {})
    params["limit"] = "100"
    all_data = []
    while True:
        result = api(path, params)
        all_data.extend(result.get("data", []))
        next_page = result.get("next_page")
        if not next_page or not next_page.get("offset"):
            break
        params["offset"] = next_page["offset"]
    return all_data


def today_wita_date() -> str:
    return datetime.now(WITA).strftime("%Y-%m-%d")


def midnight_wita_iso_utc() -> str:
    now_wita = datetime.now(WITA)
    midnight_wita = now_wita.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc = midnight_wita.astimezone(timezone.utc)
    # Asana accepts ISO timestamps; use Z
    return midnight_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def wita_date_from_completed_at(completed_at: str) -> str:
    # completed_at is ISO like 2026-02-25T...Z
    dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    return dt.astimezone(WITA).strftime("%Y-%m-%d")


def main():
    target_date = today_wita_date()
    completed_since = midnight_wita_iso_utc()

    by_project: dict[str, list[dict]] = {name: [] for _, name in PROJECTS}

    for gid, name in PROJECTS:
        params = {
            "project": gid,
            "completed_since": completed_since,
            "opt_fields": "name,completed,completed_at,assignee.name,projects.name",
        }
        tasks = api_all_pages("tasks", params)
        for t in tasks:
            if not t.get("completed"):
                continue
            ca = t.get("completed_at")
            if not ca:
                continue
            if wita_date_from_completed_at(ca) != target_date:
                continue
            by_project[name].append(t)

    any_found = False
    for project_name, tasks in by_project.items():
        if not tasks:
            continue
        any_found = True
        # Sort by completion time
        tasks.sort(key=lambda x: x.get("completed_at") or "")
        for t in tasks:
            assignee = (t.get("assignee") or {}).get("name") or "unassigned"
            ca = t.get("completed_at")
            print(f"- **[{project_name}]:** {t.get('name','?')} ({assignee}) — {ca}")

    if not any_found:
        print("(none)")


if __name__ == "__main__":
    main()
