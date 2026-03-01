#!/usr/bin/env python3
import json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone

WORKSPACE = "/Users/ai/openclaw/workspace"
ALIASES_PATH = os.path.join(WORKSPACE, "team/_aliases.json")
TEAM_DIR = os.path.join(WORKSPACE, "team")
MEM_DIR = os.path.join(WORKSPACE, "memory")

TODAY = os.environ.get("TODAY")
YESTERDAY = os.environ.get("YESTERDAY")
if not TODAY or not YESTERDAY:
    raise SystemExit("TODAY/YESTERDAY env vars required")

# WITA day boundary expressed in UTC for last-24h window
start_utc = datetime.fromisoformat(YESTERDAY + "T16:00:00+00:00")
end_utc = start_utc + timedelta(days=1)

NEXT_WEEK = (datetime.fromisoformat(TODAY) + timedelta(days=7)).date().isoformat()


def sh(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, cwd=WORKSPACE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {cmd}\n{p.stderr}")
    return p.stdout


def load_aliases():
    with open(ALIASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def read_memory_blocks():
    mem_path = os.path.join(MEM_DIR, f"{TODAY}.md")
    if not os.path.exists(mem_path):
        return []
    text = open(mem_path, "r", encoding="utf-8").read()

    # Only parse the raw WhatsApp log area (before the Daily Summary section, which repeats logs)
    raw_text = text.split("# Daily Summary", 1)[0]

    # Identify WhatsApp blocks by headings like: ### WhatsApp — ...
    lines = raw_text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### WhatsApp — "):
            header = line
            j = i + 1
            while j < len(lines) and not lines[j].startswith("### WhatsApp — "):
                # Stop before non-WhatsApp sections that often follow (daily summary, emails, etc.)
                if lines[j].startswith("# Daily Summary"):
                    break
                j += 1
            body_lines = lines[i+1:j]
            block_text = "\n".join([header] + body_lines).rstrip() + "\n"
            blocks.append({"header": header, "body": "\n".join(body_lines).rstrip() + "\n", "text": block_text})
            i = j
        else:
            i += 1

    # Deduplicate identical blocks (daily summary repeats)
    seen = set()
    uniq = []
    for b in blocks:
        key = b["text"]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(b)
    return uniq


def block_group_and_time(header: str):
    # header example: "### WhatsApp — HoK | Front Office / Reception — 09:44 (WITA)"
    m = re.match(r"^### WhatsApp — (.*?) — (.*)$", header)
    if not m:
        return (header.replace("### WhatsApp — ", "WhatsApp"), "")
    group = m.group(1).strip()
    time = m.group(2).strip()
    return group, time


def compile_employee_whatsapp(aliases, blocks):
    emp_blocks = {slug: [] for slug in aliases.keys()}

    for slug, meta in aliases.items():
        patterns = []
        for a in meta.get("aliases") or []:
            if a:
                patterns.append(re.compile(re.escape(a), re.IGNORECASE))
        phone = meta.get("phone")
        if phone:
            patterns.append(re.compile(re.escape(phone), re.IGNORECASE))
        wn = meta.get("whatsapp_name")
        if wn:
            patterns.append(re.compile(re.escape(wn), re.IGNORECASE))

        if not patterns:
            continue

        for b in blocks:
            hay = b["text"]
            if any(p.search(hay) for p in patterns):
                emp_blocks[slug].append(b)

    return emp_blocks


def asana_get_users():
    out = sh('curl -s -H "Authorization: Bearer $ASANA_TOKEN" "https://app.asana.com/api/1.0/users?workspace=1208695572000101&opt_fields=name,email,gid"')
    data = json.loads(out)
    users = data.get("data", [])
    by_email = {}
    for u in users:
        email = (u.get("email") or "").lower()
        if email:
            by_email[email] = u
    return by_email


def asana_search(params: dict):
    # GET /workspaces/{gid}/tasks/search
    q = "&".join([f"{k}={subprocess.list2cmdline([str(v)])[1:-1].replace(' ', '%20')}" for k,v in params.items()])
    url = f"https://app.asana.com/api/1.0/workspaces/1208695572000101/tasks/search?{q}"
    out = sh(f'curl -s -H "Authorization: Bearer $ASANA_TOKEN" "{url}"')
    return json.loads(out).get("data", [])


def asana_for_user(user_gid: str):
    # Completed last 24h
    completed = asana_search({
        "assignee.any": user_gid,
        "completed": "true",
        "completed_at.after": start_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "completed_at.before": end_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "opt_fields": "name,completed_at,memberships.project.name"
    })
    # Verify 24h window
    verified = []
    for t in completed:
        ca = t.get("completed_at")
        if not ca:
            continue
        try:
            dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
        except Exception:
            continue
        if start_utc <= dt < end_utc:
            verified.append(t)

    due_soon = asana_search({
        "assignee.any": user_gid,
        "completed": "false",
        "due_on.before": NEXT_WEEK,
        "opt_fields": "name,due_on,memberships.project.name"
    })

    open_all = asana_search({
        "assignee.any": user_gid,
        "completed": "false",
        "opt_fields": "name,due_on,memberships.project.name"
    })

    return verified, due_soon, open_all


def gmail_for_email(email: str):
    # returns list of dicts {subject, from, to, snippet} where possible
    try:
        out = sh(f'GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search "newer_than:1d in:anywhere (from:{email} OR to:{email})" -a ops@houseofkairos.com')
    except Exception as e:
        return {"raw": f"(error: {e})", "items": []}

    lines = [l.rstrip() for l in out.splitlines() if l.strip()]
    # Heuristic parse: many gog outputs have columns; keep as raw lines.
    items = []
    for l in lines[:20]:
        items.append({"line": l})
    return {"raw": out, "items": items}


def task_project_name(t):
    memberships = t.get("memberships") or []
    if memberships and memberships[0].get("project") and memberships[0]["project"].get("name"):
        return memberships[0]["project"]["name"]
    return "No Project"


def build_outstanding_section(open_tasks):
    grouped = {}
    for t in open_tasks:
        proj = task_project_name(t)
        grouped.setdefault(proj, []).append(t)

    lines = []
    lines.append("## Outstanding Asana Tasks")
    lines.append(f"_Last updated: {TODAY}_")
    lines.append("")

    if not open_tasks:
        lines.append("(none)")
        lines.append("")
        return "\n".join(lines) + "\n"

    def sort_key(t):
        due = t.get("due_on") or "9999-12-31"
        return (due, t.get("name") or "")

    for proj in sorted(grouped.keys()):
        lines.append(f"**{proj}**")
        for t in sorted(grouped[proj], key=sort_key):
            name = (t.get("name") or "(unnamed)").strip()
            due = t.get("due_on")
            if due:
                if due < TODAY:
                    lines.append(f"- [ ] {name} — **overdue** {due}")
                else:
                    lines.append(f"- [ ] {name} — due {due}")
            else:
                lines.append(f"- [ ] {name} — no due date")
        lines.append("")

    return "\n".join(lines) + "\n"


def replace_outstanding_section(profile_text: str, new_section: str) -> str:
    # Replace content between '---' line and '## Activity Log'
    # Keep the horizontal rule and blank lines around consistent.
    m = re.search(r"\n---\n\n(.*?)\n## Activity Log\n", profile_text, flags=re.S)
    if not m:
        # fallback: replace between Outstanding header and Activity Log
        m2 = re.search(r"\n## Outstanding Asana Tasks\n(.*?)\n## Activity Log\n", profile_text, flags=re.S)
        if not m2:
            return profile_text
        return profile_text[:m2.start()] + "\n" + new_section + "\n\n## Activity Log\n" + profile_text[m2.end():]

    return profile_text[:m.start(1)] + new_section + "\n\n" + profile_text[m.end(1):]


def last_20_lines_has_today(profile_text: str) -> bool:
    tail = "\n".join(profile_text.splitlines()[-20:])
    return f"### {TODAY}" in tail


def format_activity_append(wh_blocks, completed, due_soon, gmail_items):
    lines = []
    lines.append(f"### {TODAY}")
    lines.append("")

    # WhatsApp
    lines.append("**WhatsApp:**")
    lines.append("")
    if not wh_blocks:
        lines.append("- (none)")
        lines.append("")
    else:
        for b in wh_blocks:
            group, time = block_group_and_time(b["header"])
            lines.append(f"#### {group} — {time}")
            # include ONLY bullet messages and other lines verbatim under this block
            body = b["body"].rstrip("\n")
            if body:
                lines.extend(body.splitlines())
            lines.append("")

    # Asana
    if completed or due_soon:
        lines.append("**Asana:**")
        if completed:
            for t in completed:
                proj = task_project_name(t)
                lines.append(f"- Completed: {t.get('name','').strip()} ({proj})")
        if due_soon:
            for t in due_soon:
                proj = task_project_name(t)
                due = t.get("due_on") or ""
                lines.append(f"- Due soon: {t.get('name','').strip()} due {due} ({proj})")
        lines.append("")

    # Email
    lines.append("**Email:**")
    if not gmail_items:
        lines.append("- (none)")
    else:
        for it in gmail_items[:10]:
            lines.append(f"- {it['line']}")
    lines.append("")

    return "\n".join(lines) + "\n"


def main():
    aliases = load_aliases()
    blocks = read_memory_blocks()
    emp_wh = compile_employee_whatsapp(aliases, blocks) if blocks else {slug: [] for slug in aliases.keys()}

    # Asana users
    asana_users_by_email = asana_get_users()

    results = {}
    for slug, meta in aliases.items():
        email = (meta.get("email") or "").strip()
        asana_user = asana_users_by_email.get(email.lower()) if email else None
        completed = due_soon = open_all = []
        if asana_user:
            try:
                completed, due_soon, open_all = asana_for_user(asana_user["gid"])
            except Exception:
                completed, due_soon, open_all = [], [], []

        gmail = {"items": []}
        if email.lower().endswith("@houseofkairos.com"):
            gmail = gmail_for_email(email)

        results[slug] = {
            "whatsapp": emp_wh.get(slug, []),
            "asana_match": bool(asana_user),
            "asana_completed": completed,
            "asana_due_soon": due_soon,
            "asana_open_all": open_all,
            "gmail_items": gmail.get("items", []),
        }

    changed = []

    for slug, r in results.items():
        profile_path = os.path.join(TEAM_DIR, f"{slug}.md")
        if not os.path.exists(profile_path):
            continue
        text = open(profile_path, "r", encoding="utf-8").read()

        # Step 5: replace outstanding section if Asana user match
        if r["asana_match"]:
            new_out = build_outstanding_section(r["asana_open_all"])
            new_text = replace_outstanding_section(text, new_out)
        else:
            new_text = text

        # Step 6: append if any activity from WhatsApp/Asana/Gmail
        any_activity = bool(r["whatsapp"]) or bool(r["asana_completed"]) or bool(r["asana_due_soon"]) or bool(r["gmail_items"])
        if any_activity and not last_20_lines_has_today(new_text):
            append = format_activity_append(r["whatsapp"], r["asana_completed"], r["asana_due_soon"], r["gmail_items"])
            if not new_text.endswith("\n"):
                new_text += "\n"
            new_text += append

        if new_text != text:
            with open(profile_path, "w", encoding="utf-8") as f:
                f.write(new_text)
            changed.append(slug)

    print("UPDATED:")
    for s in changed:
        print(s)


if __name__ == "__main__":
    main()
