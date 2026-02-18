#!/usr/bin/env python3
"""Query Asana tasks for a project. Used by the agent to avoid inline curl|python issues.

Usage:
    python3 asana-tasks.py <project_gid> [--completed] [--assignee <name>]
    python3 asana-tasks.py search <query>
    python3 asana-tasks.py task <task_gid>
"""
import json, os, sys, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("ASANA_TOKEN", "")
WORKSPACE = "1208695572000101"
BASE = "https://app.asana.com/api/1.0"

def api(path, params=None):
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)

def list_tasks(project_gid, completed=False, assignee_filter=None):
    params = {"project": project_gid, "opt_fields": "name,due_on,assignee.name,completed"}
    if not completed:
        params["completed_since"] = "now"
    data = api("tasks", params).get("data", [])
    if assignee_filter:
        af = assignee_filter.lower()
        data = [t for t in data if af in ((t.get("assignee") or {}).get("name") or "").lower()]
    data.sort(key=lambda t: t.get("due_on") or "9999-99-99")
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    for t in data:
        due = t.get("due_on") or "no date"
        name = t.get("name", "?")
        assignee = (t.get("assignee") or {}).get("name", "unassigned")
        overdue = " **OVERDUE**" if due != "no date" and due < today else ""
        print(f"- {due} | {name} | {assignee}{overdue}")

def search_tasks(query):
    params = {
        "text": query,
        "completed": "false",
        "opt_fields": "name,due_on,projects.name,assignee.name",
    }
    data = api(f"workspaces/{WORKSPACE}/tasks/search", params).get("data", [])
    data.sort(key=lambda t: t.get("due_on") or "9999-99-99")
    for t in data:
        due = t.get("due_on") or "no date"
        name = t.get("name", "?")
        assignee = (t.get("assignee") or {}).get("name", "unassigned")
        projects = ", ".join(p.get("name", "") for p in (t.get("projects") or []))
        print(f"- {due} | {name} | {assignee} | {projects}")

def get_task(task_gid):
    data = api(f"tasks/{task_gid}", {"opt_fields": "name,due_on,notes,assignee.name,completed,projects.name"}).get("data", {})
    print(f"Task: {data.get('name')}")
    print(f"Due: {data.get('due_on') or 'no date'}")
    print(f"Assignee: {(data.get('assignee') or {}).get('name', 'unassigned')}")
    print(f"Completed: {data.get('completed')}")
    print(f"Projects: {', '.join(p.get('name', '') for p in (data.get('projects') or []))}")
    notes = data.get("notes", "")
    if notes:
        print(f"Notes: {notes[:500]}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: ASANA_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    if args[0] == "search" and len(args) > 1:
        search_tasks(" ".join(args[1:]))
    elif args[0] == "task" and len(args) > 1:
        get_task(args[1])
    else:
        project_gid = args[0]
        completed = "--completed" in args
        assignee = None
        if "--assignee" in args:
            idx = args.index("--assignee")
            if idx + 1 < len(args):
                assignee = args[idx + 1]
        list_tasks(project_gid, completed=completed, assignee_filter=assignee)
