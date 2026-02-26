#!/usr/bin/env python3
import json, os, re, subprocess, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKSPACE_GID = "1208695572000101"
ALIASES_PATH = Path("team/_aliases.json")
TEAM_DIR = Path("team")
MEMORY_DIR = Path("memory")

# Time: run is invoked with current UTC timestamp from environment if provided; otherwise use now.
# Cron message states: Sunday, Feb 22 2026 16:00 UTC.
# We'll compute WITA date from actual current time to be safe.
WITA = timezone(timedelta(hours=8))
now_utc = datetime.now(timezone.utc)
now_wita = now_utc.astimezone(WITA)
TODAY_WITA = now_wita.date()
TODAY_STR = TODAY_WITA.isoformat()

YESTERDAY_ISO = (now_utc - timedelta(days=1)).replace(microsecond=0).isoformat().replace('+00:00','Z')
NEXT_WEEK_DATE = (TODAY_WITA + timedelta(days=7)).isoformat()  # YYYY-MM-DD

ASANA_TOKEN = os.environ.get("ASANA_TOKEN")
if not ASANA_TOKEN:
    print("ERROR: ASANA_TOKEN not set", file=sys.stderr)
    sys.exit(2)


def run(cmd, env=None):
    """Run command, return stdout string."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\nSTDERR: {p.stderr.strip()}\nSTDOUT: {p.stdout.strip()}")
    return p.stdout


def curl_json(url):
    out = run([
        "curl", "-s",
        "-H", f"Authorization: Bearer {ASANA_TOKEN}",
        url
    ])
    return json.loads(out)


def load_aliases():
    return json.loads(ALIASES_PATH.read_text())


def asana_users_map():
    url = f"https://app.asana.com/api/1.0/users?workspace={WORKSPACE_GID}&opt_fields=name,email,gid"
    j = curl_json(url)
    email_to_gid = {}
    name_to_gid = {}
    for u in j.get("data", []):
        if u.get("email"):
            email_to_gid[u["email"].strip().lower()] = u.get("gid")
        if u.get("name"):
            name_to_gid[u["name"].strip().lower()] = u.get("gid")
    return email_to_gid, name_to_gid


def asana_search_tasks(assignee_gid, params):
    # params: dict of query params; returns list of tasks
    from urllib.parse import urlencode
    base = f"https://app.asana.com/api/1.0/workspaces/{WORKSPACE_GID}/tasks/search"
    q = urlencode(params, doseq=True)
    url = base + "?" + q
    j = curl_json(url)
    return j.get("data", [])


def normalize_projects(task):
    ps = task.get("projects") or []
    names = [p.get("name") for p in ps if p.get("name")]
    return names or ["No Project"]


def group_open_tasks(open_tasks):
    grouped = defaultdict(list)
    for t in open_tasks:
        name = t.get("name", "(unnamed)").strip()
        due = t.get("due_on")
        for proj in normalize_projects(t):
            grouped[proj].append((name, due))

    # sort projects alpha; tasks: overdue first, then due, then no due; then date/name.
    today = TODAY_WITA

    def task_sort(item):
        name, due = item
        if due:
            d = datetime.fromisoformat(due).date()
            overdue = d < today
            return (0 if overdue else 1, d, name.lower())
        return (2, datetime.max.date(), name.lower())

    for proj in grouped:
        grouped[proj].sort(key=task_sort)

    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


def format_outstanding_section(grouped):
    lines = [
        "## Outstanding Asana Tasks",
        f"_Last updated: {TODAY_STR}_",
        ""
    ]
    if not grouped:
        lines.append("(none)")
        lines.append("")
        return "\n".join(lines)

    today = TODAY_WITA
    for proj, tasks in grouped.items():
        lines.append(f"**{proj}**")
        for name, due in tasks:
            if due:
                d = datetime.fromisoformat(due).date()
                if d < today:
                    lines.append(f"- [ ] {name} — **overdue** {due}")
                else:
                    lines.append(f"- [ ] {name} — due {due}")
            else:
                lines.append(f"- [ ] {name} — no due date")
        lines.append("")

    return "\n".join(lines)


def replace_outstanding_section(md_text, new_section):
    # Ensure section placed between metadata and Activity Log.
    if "## Activity Log" not in md_text:
        # If malformed, append Activity Log header.
        md_text = md_text.rstrip() + "\n\n## Activity Log\n"

    if "## Outstanding Asana Tasks" in md_text:
        # replace from Outstanding header up to Activity Log
        pattern = re.compile(r"## Outstanding Asana Tasks[\s\S]*?(?=\n## Activity Log)")
        md_text2, n = pattern.subn(new_section.rstrip() + "\n\n", md_text)
        if n == 0:
            # fallback insert
            md_text2 = md_text.replace("## Activity Log", new_section.rstrip() + "\n\n## Activity Log")
        return md_text2
    else:
        return md_text.replace("## Activity Log", new_section.rstrip() + "\n\n## Activity Log")


def append_activity(md_text, block):
    # Append block at end under Activity Log. Never overwrite.
    if "## Activity Log" not in md_text:
        md_text = md_text.rstrip() + "\n\n## Activity Log\n"
    return md_text.rstrip() + "\n\n" + block.rstrip() + "\n"


def gmail_activity(email):
    # returns list of (other_party, subject, snippet)
    env = os.environ.copy()
    env["GOG_KEYRING_PASSWORD"] = "openclaw-hok-2026"
    query = f"newer_than:1d in:anywhere (from:{email} OR to:{email})"
    cmd = ["gog", "gmail", "search", query, "-a", "ops@houseofkairos.com"]
    out = run(cmd, env=env)
    # Parse: gog output format can vary; we'll extract messageId lines and basic fields if present.
    # We'll keep one-line summaries by reading each message id and pulling subject/from/to.
    ids = []
    for line in out.splitlines():
        m = re.search(r"\b([a-f0-9]{16,})\b", line)
        if m:
            ids.append(m.group(1))
    ids = list(dict.fromkeys(ids))

    items = []
    for mid in ids[:20]:
        g = run(["gog", "gmail", "get", mid, "-a", "ops@houseofkairos.com"], env=env)
        # very light parse
        subj = re.search(r"^Subject:\s*(.*)$", g, re.M)
        frm = re.search(r"^From:\s*(.*)$", g, re.M)
        to = re.search(r"^To:\s*(.*)$", g, re.M)
        snippet = re.search(r"^Snippet:\s*(.*)$", g, re.M)
        subject = (subj.group(1).strip() if subj else "(no subject)")
        from_s = (frm.group(1).strip() if frm else "")
        to_s = (to.group(1).strip() if to else "")
        sn = (snippet.group(1).strip() if snippet else "")
        # determine other party
        other = from_s if email.lower() not in from_s.lower() else to_s
        items.append((other, subject, sn))

    return items


def main():
    aliases = load_aliases()

    # WhatsApp parsing: skip if today's memory file does not exist.
    memory_path = MEMORY_DIR / f"{TODAY_STR}.md"
    whatsapp_activity = {}  # slug -> list of (group, summary)
    if memory_path.exists():
        mem = memory_path.read_text(errors='ignore')
        for slug, info in aliases.items():
            hits = []
            # match strategies
            patterns = []
            for a in info.get('aliases') or []:
                if a:
                    patterns.append(re.escape(a))
            if info.get('phone'):
                patterns.append(re.escape(info['phone']))
            if info.get('whatsapp_name'):
                patterns.append(re.escape(info['whatsapp_name']))
            if not patterns:
                continue
            rx = re.compile(r"(" + "|".join(patterns) + r")", re.I)
            if rx.search(mem):
                # crude: gather surrounding WhatsApp blocks
                for m in rx.finditer(mem):
                    start = mem.rfind("### WhatsApp", 0, m.start())
                    if start == -1:
                        start = max(0, m.start()-200)
                    end = mem.find("### WhatsApp", m.end())
                    if end == -1:
                        end = min(len(mem), m.end()+400)
                    snippet = mem[start:end].strip()
                    # group name line
                    gname = "WhatsApp"
                    firstline = snippet.splitlines()[0] if snippet.splitlines() else "WhatsApp"
                    m2 = re.match(r"###\s*WhatsApp\s*—\s*([^—]+?)\s*—", firstline)
                    if m2:
                        gname = m2.group(1).strip()
                    # one-line summary
                    s1 = " ".join([ln.strip('- ').strip() for ln in snippet.splitlines()[1:4] if ln.strip()])
                    s1 = re.sub(r"\s+", " ", s1)[:200]
                    hits.append((gname, s1 or "Mentioned in log"))
                whatsapp_activity[slug] = hits

    email_to_gid, _ = asana_users_map()

    asana_completed = {}
    asana_due_soon = {}
    asana_open_all = {}

    for slug, info in aliases.items():
        email = (info.get('email') or '').strip().lower()
        gid = email_to_gid.get(email)
        if not gid:
            continue

        # Completed last 24h
        completed = asana_search_tasks(gid, {
            "assignee.any": gid,
            "completed_since": YESTERDAY_ISO,
            "opt_fields": "name,completed_at,projects.name",
            "is_subtask": "false",
        })
        asana_completed[slug] = completed

        # Due within 7 days
        due_soon = asana_search_tasks(gid, {
            "assignee.any": gid,
            "due_on.before": NEXT_WEEK_DATE,
            "completed": "false",
            "opt_fields": "name,due_on,projects.name",
            "is_subtask": "false",
        })
        asana_due_soon[slug] = due_soon

        # All open
        open_all = asana_search_tasks(gid, {
            "assignee.any": gid,
            "completed": "false",
            "opt_fields": "name,due_on,projects.name",
            "is_subtask": "false",
        })
        asana_open_all[slug] = open_all

    gmail_items = {}
    for slug, info in aliases.items():
        email = (info.get('email') or '').strip().lower()
        if email.endswith('@houseofkairos.com'):
            try:
                gmail_items[slug] = gmail_activity(email)
            except Exception as e:
                gmail_items[slug] = [("(error)", f"Gmail query failed", str(e)[:120])]

    # Update profile files
    for slug, info in aliases.items():
        profile_path = TEAM_DIR / f"{slug}.md"
        if not profile_path.exists():
            continue
        md = profile_path.read_text(errors='ignore')

        # Step 5: Replace outstanding tasks section if Asana user exists.
        if slug in asana_open_all:
            grouped = group_open_tasks(asana_open_all.get(slug) or [])
            section = format_outstanding_section(grouped)
            md = replace_outstanding_section(md, section)

        # Step 6: Append activity if any across sources.
        wa = whatsapp_activity.get(slug) or []
        comp = asana_completed.get(slug) or []
        due = asana_due_soon.get(slug) or []
        ems = gmail_items.get(slug) or []

        has_activity = bool(wa or comp or due or ems)
        if has_activity:
            block_lines = [f"### {TODAY_STR}", ""]

            if wa:
                block_lines.append("**WhatsApp:**")
                for g, s in wa[:10]:
                    block_lines.append(f"- [{g}]: {s}")
                block_lines.append("")

            if comp or due:
                block_lines.append("**Asana:**")
                if comp:
                    for t in comp[:15]:
                        name = t.get('name','(unnamed)').strip()
                        proj = normalize_projects(t)[0]
                        block_lines.append(f"- Completed: {name} ({proj})")
                if due:
                    for t in due[:15]:
                        name = t.get('name','(unnamed)').strip()
                        due_on = t.get('due_on') or 'no due date'
                        proj = normalize_projects(t)[0]
                        block_lines.append(f"- Due soon: {name} due {due_on} ({proj})")
                block_lines.append("")

            if ems:
                block_lines.append("**Email:**")
                for other, subject, snip in ems[:10]:
                    other2 = other or "(unknown)"
                    sn = (snip or '').strip()
                    tail = (f" -- {sn}" if sn else "")
                    block_lines.append(f"- From/To {other2}: {subject}{tail}")
                block_lines.append("")

            md = append_activity(md, "\n".join(block_lines).rstrip())

        profile_path.write_text(md)


if __name__ == '__main__':
    main()
    print(f"OK employee-context-update {TODAY_STR} (WITA)")
