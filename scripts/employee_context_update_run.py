#!/usr/bin/env python3
import os, json, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import urllib.parse
import requests

WORKSPACE_GID = "1208695572000101"
BASE = "/root/.openclaw/workspace"
ALIASES_PATH = os.path.join(BASE, "team/_aliases.json")
TEAM_DIR = os.path.join(BASE, "team")
MEMORY_DIR = os.path.join(BASE, "memory")

WITA = timezone(timedelta(hours=8))
now_utc = datetime.now(timezone.utc)
now_wita = now_utc.astimezone(WITA)
date_wita = now_wita.date().isoformat()  # YYYY-MM-DD

yesterday_iso = (now_utc - timedelta(days=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
next_week_date = (now_wita.date() + timedelta(days=7)).isoformat()  # YYYY-MM-DD

def load_aliases():
    with open(ALIASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def asana_headers():
    tok = os.environ.get("ASANA_TOKEN")
    if not tok:
        raise SystemExit("ASANA_TOKEN not set")
    return {"Authorization": f"Bearer {tok}"}

def asana_get(url, params=None):
    r = requests.get(url, headers=asana_headers(), params=params, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Asana GET {url} failed: {r.status_code} {r.text[:300]}")
    return r.json()

def get_asana_users_map():
    url = "https://app.asana.com/api/1.0/users"
    data = asana_get(url, params={"workspace": WORKSPACE_GID, "opt_fields": "name,email,gid", "limit": 100})
    users = data.get("data", [])
    # paginate
    while data.get("next_page") and data["next_page"].get("uri"):
        data = asana_get(data["next_page"]["uri"])
        users.extend(data.get("data", []))
    by_email = {}
    by_name = {}
    for u in users:
        if u.get("email"):
            by_email[u["email"].strip().lower()] = u
        if u.get("name"):
            by_name[u["name"].strip().lower()] = u
    return by_email, by_name

def search_tasks(assignee_gid, extra_params):
    url = f"https://app.asana.com/api/1.0/workspaces/{WORKSPACE_GID}/tasks/search"
    params = {
        "assignee.any": assignee_gid,
        "opt_fields": "name,completed_at,due_on,projects.name",
        "is_subtask": "false",
    }
    params.update(extra_params)
    data = asana_get(url, params=params)
    tasks = data.get("data", [])
    # paginate using offset if present
    while data.get("next_page") and data["next_page"].get("offset"):
        params["offset"] = data["next_page"]["offset"]
        data = asana_get(url, params=params)
        tasks.extend(data.get("data", []))
    return tasks

def normalize_projects(task):
    projs = task.get("projects") or []
    if not projs:
        return ["No Project"]
    names = [p.get("name") for p in projs if p.get("name")]
    return names or ["No Project"]

def fmt_due(due_on, today):
    if not due_on:
        return "no due date", False
    try:
        overdue = due_on < today
    except Exception:
        overdue = False
    if overdue:
        return f"**overdue** {due_on}", True
    return f"due {due_on}", False

def group_open_tasks(open_tasks):
    grouped = defaultdict(list)
    for t in open_tasks:
        due = t.get("due_on")
        for proj in normalize_projects(t):
            grouped[proj].append((t.get("name") or "(untitled)", due))
    # sort by due date then name
    for proj, items in grouped.items():
        items.sort(key=lambda x: (x[1] is None, x[1] or "9999-12-31", x[0].lower()))
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))

def replace_outstanding_section(profile_path, outstanding_md):
    with open(profile_path, "r", encoding="utf-8") as f:
        text = f.read()

    if "## Activity Log" not in text:
        raise RuntimeError(f"Profile missing '## Activity Log': {profile_path}")

    if "## Outstanding Asana Tasks" in text:
        pattern = re.compile(r"## Outstanding Asana Tasks\n.*?\n(?=## Activity Log)", re.S)
        if not pattern.search(text):
            # fallback: find header and slice
            idx = text.find("## Outstanding Asana Tasks")
            act = text.find("## Activity Log")
            new_text = text[:idx] + outstanding_md + "\n" + text[act:]
        else:
            new_text = pattern.sub(outstanding_md + "\n", text)
    else:
        # insert before Activity Log
        act = text.find("## Activity Log")
        new_text = text[:act] + outstanding_md + "\n\n" + text[act:]

    if new_text != text:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(new_text)

def append_activity(profile_path, entry_md):
    with open(profile_path, "r", encoding="utf-8") as f:
        text = f.read()
    idx = text.find("## Activity Log")
    if idx == -1:
        raise RuntimeError(f"Profile missing '## Activity Log': {profile_path}")
    # append at end
    if not text.endswith("\n"):
        text += "\n"
    text += "\n" + entry_md.strip() + "\n"
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(text)

def gmail_search(email):
    cmd = [
        "bash", "-lc",
        f'GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search "newer_than:1d in:anywhere (from:{email} OR to:{email})" -a ops@houseofkairos.com'
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout

def parse_gog_search(output):
    """Parse gog gmail search output.

    Treat 'No results' as empty (no activity), per the job rules.
    """
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    cleaned = [ln for ln in lines if not ln.lower().startswith("warning")]
    if len(cleaned) == 1 and cleaned[0].lower() == "no results":
        return []
    return [ln for ln in cleaned if ln.lower() != "no results"]

def main():
    aliases = load_aliases()

    # WhatsApp parsing: skip if today's memory file doesn't exist (per instructions)
    memory_path = os.path.join(MEMORY_DIR, f"{date_wita}.md")
    whatsapp_available = os.path.exists(memory_path)

    by_email, by_name = get_asana_users_map()

    results = {}

    for slug, info in aliases.items():
        email = (info.get("email") or "").strip()
        asana_user = by_email.get(email.lower()) if email else None

        # Asana
        asana = {
            "matched": bool(asana_user),
            "user": asana_user,
            "completed": [],
            "due_soon": [],
            "open_all": [],
        }
        if asana_user:
            gid = asana_user["gid"]
            asana["completed"] = search_tasks(gid, {
                "completed_since": yesterday_iso,
                "completed": "true",
            })
            asana["due_soon"] = search_tasks(gid, {
                "due_on.before": next_week_date,
                "completed": "false",
            })
            asana["open_all"] = search_tasks(gid, {
                "completed": "false",
            })

        # Gmail
        gmail = {"queried": False, "items": []}
        if email.endswith("@houseofkairos.com"):
            gmail["queried"] = True
            rc, out = gmail_search(email)
            gmail["items"] = parse_gog_search(out)

        # WhatsApp
        whatsapp = {"available": whatsapp_available, "items": []}
        # (Skipped entirely per rules if file missing)

        results[slug] = {"info": info, "asana": asana, "gmail": gmail, "whatsapp": whatsapp}

    # Update Outstanding Asana Tasks section for those with Asana match
    today_wita = date_wita
    for slug, r in results.items():
        if not r["asana"]["matched"]:
            continue
        profile_path = os.path.join(TEAM_DIR, f"{slug}.md")
        open_tasks = r["asana"]["open_all"]
        grouped = group_open_tasks(open_tasks)

        lines = [
            "## Outstanding Asana Tasks",
            f"_Last updated: {today_wita}_",
            ""
        ]
        if not open_tasks:
            lines.append("(none)")
        else:
            today = today_wita
            for proj, items in grouped.items():
                lines.append(f"**{proj}**")
                for name, due in items:
                    due_str, _ = fmt_due(due, today)
                    lines.append(f"- [ ] {name} — {due_str}")
                lines.append("")
            if lines and lines[-1] == "":
                pass
        outstanding_md = "\n".join(lines).rstrip() + "\n"
        replace_outstanding_section(profile_path, outstanding_md)

    # Append activity log entries only if any activity found in sources (Asana/Gmail/WhatsApp)
    for slug, r in results.items():
        act_whatsapp = []  # none (skipped)
        act_asana_completed = []
        act_asana_due = []
        act_email = []

        if r["asana"]["matched"]:
            for t in r["asana"]["completed"]:
                proj = ", ".join(normalize_projects(t))
                act_asana_completed.append(f"- Completed: {t.get('name','(untitled)')} ({proj})")
            for t in r["asana"]["due_soon"]:
                proj = ", ".join(normalize_projects(t))
                due = t.get("due_on") or "(no due date)"
                act_asana_due.append(f"- Due soon: {t.get('name','(untitled)')} due {due} ({proj})")

        if r["gmail"]["queried"] and r["gmail"]["items"]:
            # include up to first 10 lines, one-line summaries (best effort)
            for ln in r["gmail"]["items"][:10]:
                act_email.append(f"- {ln}")

        if not (act_whatsapp or act_asana_completed or act_asana_due or act_email):
            continue

        entry = [
            f"### {date_wita}",
            "",
            "**WhatsApp:**",
        ]
        if act_whatsapp:
            entry.extend(act_whatsapp)
        else:
            entry.append("- (none)")
        entry.append("")
        entry.append("**Asana:**")
        if act_asana_completed:
            entry.extend(act_asana_completed)
        else:
            entry.append("- Completed: (none)")
        if act_asana_due:
            entry.extend(act_asana_due)
        else:
            entry.append("- Due soon: (none)")
        entry.append("")
        entry.append("**Email:**")
        if act_email:
            entry.extend(act_email)
        else:
            entry.append("- (none)")

        profile_path = os.path.join(TEAM_DIR, f"{slug}.md")
        append_activity(profile_path, "\n".join(entry))

    print(json.dumps({
        "date_wita": date_wita,
        "whatsapp_memory_exists": whatsapp_available,
        "yesterday_iso": yesterday_iso,
        "next_week_date": next_week_date,
        "employees": {
            slug: {
                "asana_matched": results[slug]["asana"]["matched"],
                "asana_completed": len(results[slug]["asana"]["completed"]),
                "asana_due_soon": len(results[slug]["asana"]["due_soon"]),
                "asana_open": len(results[slug]["asana"]["open_all"]),
                "gmail_items": len(results[slug]["gmail"]["items"]),
            } for slug in results
        }
    }, indent=2))

if __name__ == "__main__":
    main()
