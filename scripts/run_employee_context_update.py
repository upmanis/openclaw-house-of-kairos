#!/usr/bin/env python3
import json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone, date

WORKSPACE_GID = "1208695572000101"
ALIASES_PATH = "/Users/ai/openclaw/workspace/team/_aliases.json"
TEAM_DIR = "/Users/ai/openclaw/workspace/team"
MEMORY_DIR = "/Users/ai/openclaw/workspace/memory"

# Time handling
try:
    from zoneinfo import ZoneInfo
    WITA = ZoneInfo("Asia/Makassar")  # UTC+8
except Exception:
    WITA = timezone(timedelta(hours=8))

NOW_UTC = datetime(2026, 2, 20, 16, 0, 0, tzinfo=timezone.utc)  # per job prompt
NOW_WITA = NOW_UTC.astimezone(WITA)
TODAY_WITA_STR = NOW_WITA.date().isoformat()  # YYYY-MM-DD

COMPLETED_SINCE_ISO = (NOW_UTC - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
NEXT_WEEK_DATE = (NOW_WITA.date() + timedelta(days=7)).isoformat()  # due_on.before uses date


def sh(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {cmd}\nSTDERR: {p.stderr.strip()}")
    return p.stdout


ASANA_TOKEN = os.environ.get("ASANA_TOKEN")
if not ASANA_TOKEN:
    raise RuntimeError("ASANA_TOKEN not set in environment")

def asana_get_all(url: str):
    """Fetch all pages for an Asana GET endpoint that returns {data, next_page}."""
    out = []
    offset = None
    while True:
        u = url
        if offset:
            joiner = "&" if "?" in u else "?"
            u = f"{u}{joiner}offset={offset}"
        txt = sh(f"curl -s -H {json.dumps('Authorization: Bearer ' + ASANA_TOKEN)} {json.dumps(u)}")
        j = json.loads(txt or "{}")
        out.extend(j.get("data") or [])
        np = (j.get("next_page") or {})
        offset = np.get("offset")
        if not offset:
            break
    return out


def asana_users_map():
    url = f"https://app.asana.com/api/1.0/users?workspace={WORKSPACE_GID}&opt_fields=name,email,gid"
    users = asana_get_all(url)
    by_email = {}
    for u in users:
        em = (u.get("email") or "").strip().lower()
        if em:
            by_email[em] = u
    return by_email


def asana_tasks_search(assignee_gid: str, params: str):
    base = f"https://app.asana.com/api/1.0/workspaces/{WORKSPACE_GID}/tasks/search?assignee.any={assignee_gid}&{params}"
    return asana_get_all(base)


def group_tasks_by_project(tasks):
    grouped = {}
    for t in tasks:
        projects = t.get("projects") or []
        if not projects:
            grouped.setdefault("No Project", []).append(t)
        else:
            for p in projects:
                grouped.setdefault(p.get("name") or "(unnamed project)", []).append(t)
    # sort tasks within each project by due_on then name
    def key(t):
        d = t.get("due_on")
        return (d or "9999-12-31", (t.get("name") or ""))
    for k in list(grouped.keys()):
        grouped[k] = sorted(grouped[k], key=key)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


def format_outstanding_section(tasks_all_open):
    lines = []
    lines.append("## Outstanding Asana Tasks")
    lines.append(f"_Last updated: {TODAY_WITA_STR}_")
    lines.append("")
    if not tasks_all_open:
        lines.append("(none)")
        lines.append("")
        return "\n".join(lines)

    grouped = group_tasks_by_project(tasks_all_open)
    today = NOW_WITA.date()
    for project, tasks in grouped.items():
        lines.append(f"**{project}**")
        for t in tasks:
            name = (t.get("name") or "(unnamed task)").strip()
            due = t.get("due_on")
            if due:
                try:
                    d = date.fromisoformat(due)
                except Exception:
                    d = None
                if d and d < today:
                    lines.append(f"- [ ] {name} — **overdue** {due}")
                else:
                    lines.append(f"- [ ] {name} — due {due}")
            else:
                lines.append(f"- [ ] {name} — no due date")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def replace_outstanding_section(profile_text: str, new_section: str) -> str:
    # Replace from '## Outstanding Asana Tasks' up to (but not including) '## Activity Log'
    if "## Activity Log" not in profile_text:
        raise ValueError("Profile missing '## Activity Log' section")

    if "## Outstanding Asana Tasks" in profile_text:
        pattern = re.compile(r"^## Outstanding Asana Tasks\n.*?^(?=## Activity Log\b)", re.S | re.M)
        if not pattern.search(profile_text):
            # fallback: simple split
            before, after = profile_text.split("## Outstanding Asana Tasks", 1)
            # restore header we removed in split
            after = "## Outstanding Asana Tasks" + after
            # now cut to activity log
            pre2, act = after.split("## Activity Log", 1)
            return before.rstrip() + "\n\n" + new_section.rstrip() + "\n\n## Activity Log" + act
        return pattern.sub(new_section.rstrip() + "\n\n", profile_text)

    # Insert between metadata block end ('---') and '## Activity Log'
    # Prefer inserting right before Activity Log
    before, after = profile_text.split("## Activity Log", 1)
    before = before.rstrip() + "\n\n" + new_section.rstrip() + "\n\n"
    return before + "## Activity Log" + after


def append_activity_log(profile_text: str, entry_text: str) -> str:
    # Append at end of file; Activity Log is append-only, so safest.
    if not profile_text.endswith("\n"):
        profile_text += "\n"
    return profile_text + "\n" + entry_text.rstrip() + "\n"


def gmail_search(email: str):
    q = f"newer_than:1d in:anywhere (from:{email} OR to:{email})"
    cmd = f"GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search {json.dumps(q)} -a ops@houseofkairos.com"
    out = sh(cmd)
    return out.strip()


def parse_gog_search_output(txt: str):
    # Keep it simple: each line is a hit; but treat "No results" as empty.
    lines = [l.strip() for l in (txt or "").splitlines() if l.strip()]
    if not lines:
        return []
    if any(l.lower().startswith("no results") for l in lines):
        return []
    # Some gog versions print a header line even when there are zero results;
    # if we only have a header-like line, treat as empty.
    if len(lines) == 1 and re.search(r"\bID\b.*\bDATE\b.*\bFROM\b.*\bSUBJECT\b", lines[0]):
        return []
    return lines


def main():
    aliases = json.load(open(ALIASES_PATH, "r"))

    # WhatsApp parsing: skip if today's memory file missing
    memory_path = os.path.join(MEMORY_DIR, f"{TODAY_WITA_STR}.md")
    whatsapp_available = os.path.exists(memory_path)
    memory_text = ""
    if whatsapp_available:
        memory_text = open(memory_path, "r").read()

    # Asana users map
    users_by_email = asana_users_map()

    results = {}

    for slug, emp in aliases.items():
        emp_email = (emp.get("email") or "").strip().lower()
        emp_phone = emp.get("phone")
        emp_wa_name = emp.get("whatsapp_name")
        emp_aliases = emp.get("aliases") or []

        emp_res = {
            "whatsapp": [],  # list of (group, summary)
            "asana": {
                "user": None,
                "completed": [],
                "due_soon": [],
                "open_all": [],
            },
            "gmail": [],
        }

        # WhatsApp mentions
        if whatsapp_available:
            # very lightweight parsing: find sections starting with '### WhatsApp —'
            # and include bullet lines that match any alias / phone / wa name.
            matches = []
            needles = []
            for a in emp_aliases:
                if a:
                    needles.append(a)
            if emp_phone:
                needles.append(emp_phone)
            if emp_wa_name:
                needles.append(emp_wa_name)
            needles_ci = [n.lower() for n in needles if n]

            current_group = None
            for line in memory_text.splitlines():
                m = re.match(r"^### WhatsApp —\s*(.*?)\s*—", line)
                if m:
                    current_group = m.group(1).strip()
                    continue
                if current_group and line.strip().startswith("-"):
                    ll = line.lower()
                    if any(n in ll for n in needles_ci):
                        matches.append((current_group, re.sub(r"\s+", " ", line.strip("- "))))
            # condense per group
            if matches:
                by_group = {}
                for g, s in matches:
                    by_group.setdefault(g, []).append(s)
                for g, items in by_group.items():
                    emp_res["whatsapp"].append((g, "; ".join(items)[:240]))

        # Asana
        if emp_email and emp_email in users_by_email:
            u = users_by_email[emp_email]
            emp_res["asana"]["user"] = u
            gid = u["gid"]

            completed = asana_tasks_search(
                gid,
                f"completed_since={COMPLETED_SINCE_ISO}&opt_fields=name,completed_at,projects.name&is_subtask=false"
            )
            due_soon = asana_tasks_search(
                gid,
                f"due_on.before={NEXT_WEEK_DATE}&completed=false&opt_fields=name,due_on,projects.name&is_subtask=false"
            )
            open_all = asana_tasks_search(
                gid,
                "completed=false&opt_fields=name,due_on,projects.name&is_subtask=false"
            )
            emp_res["asana"]["completed"] = completed
            emp_res["asana"]["due_soon"] = due_soon
            emp_res["asana"]["open_all"] = open_all

        # Gmail
        if emp_email.endswith("@houseofkairos.com"):
            try:
                txt = gmail_search(emp_email)
                hits = parse_gog_search_output(txt)
                emp_res["gmail"] = hits
            except Exception as e:
                emp_res["gmail"] = [f"(gmail search failed: {e})"]

        results[slug] = emp_res

    # Update profiles
    for slug, emp in aliases.items():
        profile_path = os.path.join(TEAM_DIR, f"{slug}.md")
        if not os.path.exists(profile_path):
            # skip missing profiles
            continue
        text = open(profile_path, "r").read()

        emp_res = results.get(slug) or {}
        asana_user = (emp_res.get("asana") or {}).get("user")

        # Step 5: replace outstanding section for employees with matching Asana user
        if asana_user:
            new_sec = format_outstanding_section((emp_res["asana"].get("open_all") or []))
            text = replace_outstanding_section(text, new_sec)

        # Step 6: append activity if any from WhatsApp/Asana/Gmail
        wa_items = emp_res.get("whatsapp") or []
        as_completed = (emp_res.get("asana") or {}).get("completed") or []
        as_due_soon = (emp_res.get("asana") or {}).get("due_soon") or []
        gm_hits = emp_res.get("gmail") or []

        has_activity = bool(wa_items) or bool(as_completed) or bool(as_due_soon) or bool(gm_hits)

        # Idempotency: if there's already an entry for today, don't append another one.
        already_logged_today = re.search(rf"^###\s+{re.escape(TODAY_WITA_STR)}\b", text, re.M) is not None

        if has_activity and not already_logged_today:
            entry_lines = []
            entry_lines.append(f"### {TODAY_WITA_STR}")
            entry_lines.append("")

            if wa_items:
                entry_lines.append("**WhatsApp:**")
                for g, s in wa_items:
                    entry_lines.append(f"- [{g}]: {s}")
                entry_lines.append("")

            if as_completed or as_due_soon:
                entry_lines.append("**Asana:**")
                if as_completed:
                    for t in as_completed:
                        name = (t.get("name") or "(unnamed task)").strip()
                        proj = (t.get("projects") or [])
                        proj_name = proj[0].get("name") if proj else "No Project"
                        entry_lines.append(f"- Completed: {name} ({proj_name})")
                if as_due_soon:
                    for t in as_due_soon:
                        name = (t.get("name") or "(unnamed task)").strip()
                        due = t.get("due_on") or "(no due date)"
                        proj = (t.get("projects") or [])
                        proj_name = proj[0].get("name") if proj else "No Project"
                        entry_lines.append(f"- Due soon: {name} due {due} ({proj_name})")
                entry_lines.append("")

            if gm_hits:
                entry_lines.append("**Email:**")
                # keep first ~10 lines to avoid bloat
                for l in gm_hits[:10]:
                    entry_lines.append(f"- {l}")
                if len(gm_hits) > 10:
                    entry_lines.append(f"- (and {len(gm_hits)-10} more)")
                entry_lines.append("")

            entry = "\n".join(entry_lines).rstrip() + "\n"
            text = append_activity_log(text, entry)

        open(profile_path, "w").write(text)


if __name__ == "__main__":
    main()
