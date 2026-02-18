#!/usr/bin/env python3
"""Query Asana tasks for a project.

Usage:
    python3 asana-tasks.py <project_gid> [options]
    python3 asana-tasks.py search <query> [options]
    python3 asana-tasks.py task <task_gid>
    python3 asana-tasks.py projects

Options (list mode):
    --completed          Include completed tasks
    --assignee <name>    Filter by assignee name (partial match)
    --overdue            Only show overdue tasks
    --due-before <date>  Tasks due on or before YYYY-MM-DD
    --due-after <date>   Tasks due on or after YYYY-MM-DD
    --due-this-week      Tasks due within the current week (Mon-Sun)
    --due-next-week      Tasks due within next week
    --no-date            Only show tasks with no due date
    --sort <field>       Sort by: date (default), assignee, name
    --reverse            Reverse sort order
    --limit <n>          Max number of results
"""
import json, os, sys, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("ASANA_TOKEN", "")
WORKSPACE = "1208695572000101"
BASE = "https://app.asana.com/api/1.0"
WITA = timezone(timedelta(hours=8))


def today_wita():
    return datetime.now(WITA).strftime("%Y-%m-%d")


def week_range_wita(offset=0):
    """Return (monday, sunday) for current week + offset weeks."""
    now = datetime.now(WITA)
    monday = now - timedelta(days=now.weekday()) + timedelta(weeks=offset)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


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


def api_all_pages(path, params=None):
    """Fetch all pages of results."""
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


def parse_opts(args):
    opts = {
        "completed": False,
        "assignee": None,
        "overdue": False,
        "due_before": None,
        "due_after": None,
        "due_this_week": False,
        "due_next_week": False,
        "no_date": False,
        "sort": "date",
        "reverse": False,
        "limit": None,
    }
    i = 0
    positional = []
    while i < len(args):
        a = args[i]
        if a == "--completed":
            opts["completed"] = True
        elif a == "--overdue":
            opts["overdue"] = True
        elif a == "--due-this-week":
            opts["due_this_week"] = True
        elif a == "--due-next-week":
            opts["due_next_week"] = True
        elif a == "--no-date":
            opts["no_date"] = True
        elif a == "--reverse":
            opts["reverse"] = True
        elif a == "--assignee" and i + 1 < len(args):
            i += 1
            opts["assignee"] = args[i]
        elif a == "--due-before" and i + 1 < len(args):
            i += 1
            opts["due_before"] = args[i]
        elif a == "--due-after" and i + 1 < len(args):
            i += 1
            opts["due_after"] = args[i]
        elif a == "--sort" and i + 1 < len(args):
            i += 1
            opts["sort"] = args[i]
        elif a == "--limit" and i + 1 < len(args):
            i += 1
            opts["limit"] = int(args[i])
        elif not a.startswith("--"):
            positional.append(a)
        i += 1
    return positional, opts


def filter_tasks(data, opts):
    today = today_wita()

    if opts["assignee"]:
        af = opts["assignee"].lower()
        data = [t for t in data if af in ((t.get("assignee") or {}).get("name") or "").lower()]

    if opts["overdue"]:
        data = [t for t in data if t.get("due_on") and t["due_on"] < today]

    if opts["no_date"]:
        data = [t for t in data if not t.get("due_on")]

    if opts["due_before"]:
        data = [t for t in data if t.get("due_on") and t["due_on"] <= opts["due_before"]]

    if opts["due_after"]:
        data = [t for t in data if t.get("due_on") and t["due_on"] >= opts["due_after"]]

    if opts["due_this_week"]:
        mon, sun = week_range_wita(0)
        data = [t for t in data if t.get("due_on") and mon <= t["due_on"] <= sun]

    if opts["due_next_week"]:
        mon, sun = week_range_wita(1)
        data = [t for t in data if t.get("due_on") and mon <= t["due_on"] <= sun]

    return data


def sort_tasks(data, opts):
    sort_field = opts["sort"]
    if sort_field == "assignee":
        key = lambda t: ((t.get("assignee") or {}).get("name") or "zzz").lower()
    elif sort_field == "name":
        key = lambda t: (t.get("name") or "").lower()
    else:
        key = lambda t: t.get("due_on") or "9999-99-99"
    data.sort(key=key, reverse=opts["reverse"])
    return data


def print_tasks(data, opts, show_project=False):
    today = today_wita()
    if opts["limit"]:
        data = data[: opts["limit"]]
    if not data:
        print("(no tasks found)")
        return
    for t in data:
        due = t.get("due_on") or "no date"
        name = t.get("name", "?")
        assignee = (t.get("assignee") or {}).get("name", "unassigned")
        overdue = " **OVERDUE**" if due != "no date" and due < today else ""
        line = f"- {due} | {name} | {assignee}{overdue}"
        if show_project:
            projects = ", ".join(p.get("name", "") for p in (t.get("projects") or []))
            if projects:
                line += f" | {projects}"
        print(line)
    print(f"\n({len(data)} task{'s' if len(data) != 1 else ''})")


def list_tasks(project_gid, opts):
    params = {"project": project_gid, "opt_fields": "name,due_on,assignee.name,completed"}
    if not opts["completed"]:
        params["completed_since"] = "now"
    data = api_all_pages("tasks", params)
    data = filter_tasks(data, opts)
    data = sort_tasks(data, opts)
    print_tasks(data, opts)


def search_tasks(query, opts):
    params = {
        "text": query,
        "completed": "false",
        "opt_fields": "name,due_on,projects.name,assignee.name",
    }
    data = api(f"workspaces/{WORKSPACE}/tasks/search", params).get("data", [])
    data = filter_tasks(data, opts)
    data = sort_tasks(data, opts)
    print_tasks(data, opts, show_project=True)


def get_task(task_gid):
    data = api(
        f"tasks/{task_gid}",
        {"opt_fields": "name,due_on,notes,assignee.name,completed,projects.name,subtasks.name,subtasks.completed,subtasks.due_on,subtasks.assignee.name"},
    ).get("data", {})
    print(f"Task: {data.get('name')}")
    print(f"Due: {data.get('due_on') or 'no date'}")
    print(f"Assignee: {(data.get('assignee') or {}).get('name', 'unassigned')}")
    print(f"Completed: {data.get('completed')}")
    print(f"Projects: {', '.join(p.get('name', '') for p in (data.get('projects') or []))}")
    notes = data.get("notes", "")
    if notes:
        print(f"Notes: {notes[:500]}")
    subtasks = data.get("subtasks") or []
    if subtasks:
        print(f"\nSubtasks ({len(subtasks)}):")
        for s in subtasks:
            done = "x" if s.get("completed") else " "
            due = s.get("due_on") or "no date"
            assignee = (s.get("assignee") or {}).get("name", "")
            print(f"  [{done}] {s.get('name')} | {due} | {assignee}")


def list_projects():
    data = api_all_pages(
        f"workspaces/{WORKSPACE}/projects",
        {"opt_fields": "name,archived", "archived": "false"},
    )
    data.sort(key=lambda p: p.get("name", "").lower())
    for p in data:
        print(f"- {p.get('gid')} | {p.get('name')}")
    print(f"\n({len(data)} projects)")


if __name__ == "__main__":
    if not TOKEN:
        print("Error: ASANA_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if args[0] == "search":
        positional, opts = parse_opts(args[1:])
        search_tasks(" ".join(positional), opts)
    elif args[0] == "task" and len(args) > 1:
        get_task(args[1])
    elif args[0] == "projects":
        list_projects()
    else:
        positional, opts = parse_opts(args)
        if not positional:
            print("Error: project GID required", file=sys.stderr)
            sys.exit(1)
        list_tasks(positional[0], opts)
