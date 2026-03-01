#!/usr/bin/env python3
import json, os, re, subprocess
from datetime import datetime, timedelta

WORKSPACE = "/Users/ai/openclaw/workspace"
ALIASES_PATH = os.path.join(WORKSPACE, "team/_aliases.json")
TEAM_DIR = os.path.join(WORKSPACE, "team")
MEM_DIR = os.path.join(WORKSPACE, "memory")

TODAY = os.environ.get("TODAY")
YESTERDAY = os.environ.get("YESTERDAY")
if not TODAY or not YESTERDAY:
    raise SystemExit("TODAY/YESTERDAY env vars required")

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
    full_text = open(mem_path, "r", encoding="utf-8").read()
    raw_text = full_text.split("# Daily Summary", 1)[0]
    lines = raw_text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("### WhatsApp — "):
            header = lines[i]
            j = i + 1
            while j < len(lines) and not lines[j].startswith("### WhatsApp — "):
                if lines[j].startswith("# Daily Summary"):
                    break
                j += 1
            body_lines = lines[i+1:j]
            block_text = "\n".join([header] + body_lines).rstrip() + "\n"
            blocks.append({"header": header, "body": "\n".join(body_lines).rstrip() + "\n", "text": block_text})
            i = j
        else:
            i += 1
    # dedupe
    seen = set(); uniq=[]
    for b in blocks:
        if b["text"] in seen: continue
        seen.add(b["text"]); uniq.append(b)
    return uniq


def block_group_and_time(header: str):
    m = re.match(r"^### WhatsApp — (.*?) — (.*)$", header)
    if not m:
        return (header.replace("### WhatsApp — ", "WhatsApp"), "")
    return m.group(1).strip(), m.group(2).strip()


def compile_employee_whatsapp(aliases, blocks):
    emp_blocks = {slug: [] for slug in aliases.keys()}
    for slug, meta in aliases.items():
        patterns = []
        for a in meta.get("aliases") or []:
            if a:
                patterns.append(re.compile(re.escape(a), re.IGNORECASE))
        if meta.get("phone"):
            patterns.append(re.compile(re.escape(meta["phone"]), re.IGNORECASE))
        if meta.get("whatsapp_name"):
            patterns.append(re.compile(re.escape(meta["whatsapp_name"]), re.IGNORECASE))
        if not patterns:
            continue
        for b in blocks:
            if any(p.search(b["text"]) for p in patterns):
                emp_blocks[slug].append(b)
    return emp_blocks


def asana_get_users():
    out = sh('curl -s -H "Authorization: Bearer $ASANA_TOKEN" "https://app.asana.com/api/1.0/users?workspace=1208695572000101&opt_fields=name,email,gid"')
    users = json.loads(out).get("data", [])
    return { (u.get("email") or "").lower(): u for u in users if u.get("email") }


def asana_search(params: dict):
    # minimal URL encoding
    import urllib.parse
    url = "https://app.asana.com/api/1.0/workspaces/1208695572000101/tasks/search?" + urllib.parse.urlencode(params)
    out = sh(f'curl -s -H "Authorization: Bearer $ASANA_TOKEN" "{url}"')
    return json.loads(out).get("data", [])


def asana_for_user(user_gid: str):
    completed = asana_search({
        "assignee.any": user_gid,
        "completed": "true",
        "completed_at.after": start_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "completed_at.before": end_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "opt_fields": "name,completed_at,memberships.project.name"
    })
    verified=[]
    for t in completed:
        ca=t.get("completed_at")
        if not ca: continue
        try:
            dt=datetime.fromisoformat(ca.replace('Z','+00:00'))
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
    return verified, due_soon


def gmail_for_email(email: str):
    try:
        out = sh(f'GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search "newer_than:1d in:anywhere (from:{email} OR to:{email})" -a ops@houseofkairos.com')
    except Exception:
        return []
    lines = [l.rstrip() for l in out.splitlines() if l.strip()]
    return [{"line": l} for l in lines[:20]]


def task_project_name(t):
    ms=t.get('memberships') or []
    if ms and ms[0].get('project') and ms[0]['project'].get('name'):
        return ms[0]['project']['name']
    return 'No Project'


def format_activity(wh_blocks, completed, due_soon, gmail_items):
    lines=[]
    lines.append(f"### {TODAY}")
    lines.append("")
    lines.append("**WhatsApp:**")
    lines.append("")
    if not wh_blocks:
        lines.append("- (none)")
        lines.append("")
    else:
        for b in wh_blocks:
            group,time=block_group_and_time(b['header'])
            lines.append(f"#### {group} — {time}")
            body=b['body'].rstrip('\n')
            if body:
                lines.extend(body.splitlines())
            lines.append("")

    if completed or due_soon:
        lines.append("**Asana:**")
        for t in completed:
            lines.append(f"- Completed: {t.get('name','').strip()} ({task_project_name(t)})")
        for t in due_soon:
            lines.append(f"- Due soon: {t.get('name','').strip()} due {t.get('due_on') or ''} ({task_project_name(t)})")
        lines.append("")

    lines.append("**Email:**")
    if not gmail_items:
        lines.append("- (none)")
    else:
        for it in gmail_items[:10]:
            lines.append(f"- {it['line']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def replace_today_entry(text: str, new_entry: str) -> str:
    # Replace the FIRST section starting with '### TODAY' (at start or after newline)
    # up to the next dated activity heading (### YYYY-MM-DD) or end of file.
    pat = re.compile(rf"(^|\n)### {re.escape(TODAY)}\n.*?(?=\n### \d{{4}}-\d{{2}}-\d{{2}}\n|\Z)", re.S)
    m = pat.search(text)
    if not m:
        return text
    out = text[:m.start()] + (m.group(1) or "") + new_entry.rstrip("\n") + "\n" + text[m.end():]
    # Remove any additional duplicate TODAY sections (keep only the first/new one)
    while True:
        m2 = pat.search(out, m.start() + 1)
        if not m2:
            break
        out = out[:m2.start()] + (m2.group(1) or "") + out[m2.end():]
    return out


def main():
    aliases=load_aliases()
    blocks=read_memory_blocks()
    emp_wh=compile_employee_whatsapp(aliases, blocks) if blocks else {slug: [] for slug in aliases}
    asana_users=asana_get_users()

    repaired=[]
    for slug, meta in aliases.items():
        path=os.path.join(TEAM_DIR, f"{slug}.md")
        if not os.path.exists(path):
            continue
        text=open(path,'r',encoding='utf-8').read()
        if f"### {TODAY}" not in text:
            continue

        email=(meta.get('email') or '').strip()
        asana_user=asana_users.get(email.lower()) if email else None
        completed=due_soon=[]
        if asana_user:
            try:
                completed, due_soon = asana_for_user(asana_user['gid'])
            except Exception:
                completed, due_soon = [], []
        gmail_items = gmail_for_email(email) if email.lower().endswith('@houseofkairos.com') else []

        new_entry = format_activity(emp_wh.get(slug, []), completed, due_soon, gmail_items)
        new_text = replace_today_entry(text, new_entry)
        if new_text != text:
            open(path,'w',encoding='utf-8').write(new_text)
            repaired.append(slug)

    print('REPAIRED:')
    for s in repaired:
        print(s)

if __name__=='__main__':
    main()
