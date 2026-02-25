import json, os, re, subprocess, datetime
from collections import defaultdict

WORKDIR = os.path.dirname(__file__)
ALIASES_PATH = os.path.join(WORKDIR, 'team', '_aliases.json')
ASANA_USERS_PATH = os.path.join(WORKDIR, 'tmp_asana_users.json')
TEAM_DIR = os.path.join(WORKDIR, 'team')
MEMORY_DIR = os.path.join(WORKDIR, 'memory')

UTC_NOW = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
WITA = datetime.timezone(datetime.timedelta(hours=8))
WITA_TODAY = UTC_NOW.astimezone(WITA).date()  # YYYY-MM-DD
TODAY_STR = WITA_TODAY.isoformat()

# Asana time bounds
YESTERDAY_ISO = (UTC_NOW - datetime.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
NEXT_WEEK_ISO = (UTC_NOW + datetime.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S.000Z')

# WhatsApp logs: only if memory file exists for WITA date
MEMORY_PATH = os.path.join(MEMORY_DIR, f'{TODAY_STR}.md')
DO_WHATSAPP = os.path.exists(MEMORY_PATH)


def run(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, cwd=WORKDIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f'cmd failed ({p.returncode}): {cmd}\nSTDERR:\n{p.stderr[:2000]}')
    return p.stdout


ASANA_TOKEN = os.environ.get('ASANA_TOKEN','')


def asana_search(url: str):
    if not ASANA_TOKEN:
        raise RuntimeError('ASANA_TOKEN missing from environment')
    out = run(f'curl -s -H "Authorization: Bearer {ASANA_TOKEN}" "{url}"')
    data = json.loads(out).get('data', [])
    return data


def parse_gog_search(output: str):
    # gog output format can vary; keep a list of lines that look like subject rows.
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    # Heuristic: skip lines that are just IDs.
    return lines


def load_aliases():
    with open(ALIASES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_asana_users_by_email():
    with open(ASANA_USERS_PATH, 'r', encoding='utf-8') as f:
        users = json.load(f).get('data', [])
    by_email = {}
    for u in users:
        em = (u.get('email') or '').lower().strip()
        if em:
            by_email[em] = u
    return by_email


def group_tasks_by_project(tasks):
    grouped = defaultdict(list)
    for t in tasks:
        name = t.get('name') or '(unnamed)'
        due = t.get('due_on')
        projects = t.get('projects') or []
        if projects:
            # Asana search returns list of projects with name
            proj_names = [p.get('name') for p in projects if p.get('name')]
            proj = proj_names[0] if proj_names else 'No Project'
        else:
            proj = 'No Project'
        grouped[proj].append((name, due))
    # sort within project by due (None last) then name
    for proj in list(grouped.keys()):
        grouped[proj].sort(key=lambda x: (x[1] is None, x[1] or '9999-12-31', x[0].lower()))
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


def format_outstanding_section(grouped):
    lines = []
    lines.append('## Outstanding Asana Tasks')
    lines.append(f'_Last updated: {TODAY_STR}_')
    lines.append('')
    if not grouped or all(len(v)==0 for v in grouped.values()):
        lines.append('(none)')
        lines.append('')
        return '\n'.join(lines)

    today = WITA_TODAY
    for proj, items in grouped.items():
        lines.append(f'**{proj}**')
        for name, due in items:
            if due:
                due_date = datetime.date.fromisoformat(due)
                if due_date < today:
                    lines.append(f'- [ ] {name} — **overdue** {due}')
                else:
                    lines.append(f'- [ ] {name} — due {due}')
            else:
                lines.append(f'- [ ] {name} — no due date')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def replace_outstanding_section(profile_text: str, new_section: str) -> str:
    # Replace everything from '## Outstanding Asana Tasks' up to '## Activity Log'
    if '## Activity Log' not in profile_text:
        raise ValueError('Profile missing ## Activity Log section')

    if '## Outstanding Asana Tasks' in profile_text:
        pattern = re.compile(r'^## Outstanding Asana Tasks\n.*?^## Activity Log\n', re.DOTALL | re.MULTILINE)
        m = pattern.search(profile_text)
        if not m:
            # fallback: replace by manual split
            before, rest = profile_text.split('## Outstanding Asana Tasks', 1)
            rest2 = rest.split('## Activity Log', 1)[1]
            return before + new_section + '\n\n## Activity Log\n' + rest2
        start, end = m.span()
        return profile_text[:start] + new_section + '\n\n## Activity Log\n' + profile_text[end:]
    else:
        # Insert before ## Activity Log
        parts = profile_text.split('## Activity Log', 1)
        return parts[0].rstrip() + '\n\n' + new_section + '\n\n## Activity Log' + parts[1]


def append_activity_log(profile_text: str, block: str) -> str:
    # Append at end (under Activity Log), without modifying existing
    if not profile_text.endswith('\n'):
        profile_text += '\n'
    return profile_text + '\n' + block.rstrip() + '\n'


def main():
    aliases = load_aliases()
    asana_users = load_asana_users_by_email()

    whatsapp_mentions = {}  # slug -> list[(group, summary)]
    if DO_WHATSAPP:
        # Not expected today; implement minimal parser if file exists
        mem = open(MEMORY_PATH,'r',encoding='utf-8').read()
        for slug, info in aliases.items():
            hits = []
            needles = []
            for a in (info.get('aliases') or []):
                if a: needles.append(a)
            if info.get('phone'): needles.append(info['phone'])
            if info.get('whatsapp_name'): needles.append(info['whatsapp_name'])
            for n in set([x for x in needles if x]):
                if re.search(re.escape(n), mem, re.IGNORECASE):
                    hits.append(n)
            if hits:
                whatsapp_mentions[slug] = [('(unknown group)', f"Mentioned: {', '.join(sorted(hits))}")]

    # Asana + Gmail per employee
    for slug, info in aliases.items():
        email = (info.get('email') or '').lower().strip()
        profile_path = os.path.join(TEAM_DIR, f'{slug}.md')
        if not os.path.exists(profile_path):
            continue

        profile_text = open(profile_path, 'r', encoding='utf-8').read()

        asana_user = asana_users.get(email) if email else None
        asana_completed = []
        asana_due_soon = []
        asana_all_open = []

        if asana_user:
            gid = asana_user['gid']
            completed_url = (
                'https://app.asana.com/api/1.0/workspaces/1208695572000101/tasks/search'
                f'?assignee.any={gid}&completed_since={YESTERDAY_ISO}'
                '&opt_fields=name,completed_at,projects.name&is_subtask=false'
            )
            due_soon_url = (
                'https://app.asana.com/api/1.0/workspaces/1208695572000101/tasks/search'
                f'?assignee.any={gid}&due_on.before={NEXT_WEEK_ISO}&completed=false'
                '&opt_fields=name,due_on,projects.name&is_subtask=false'
            )
            all_open_url = (
                'https://app.asana.com/api/1.0/workspaces/1208695572000101/tasks/search'
                f'?assignee.any={gid}&completed=false'
                '&opt_fields=name,due_on,projects.name&is_subtask=false'
            )
            asana_completed = asana_search(completed_url)
            asana_due_soon = asana_search(due_soon_url)
            asana_all_open = asana_search(all_open_url)

            # Replace Outstanding Asana Tasks section
            grouped = group_tasks_by_project(asana_all_open)
            new_section = format_outstanding_section(grouped)
            new_profile_text = replace_outstanding_section(profile_text, new_section)
            if new_profile_text != profile_text:
                with open(profile_path, 'w', encoding='utf-8') as f:
                    f.write(new_profile_text)
                profile_text = new_profile_text

        # Gmail search for @houseofkairos.com only
        gmail_lines = []
        if email.endswith('@houseofkairos.com'):
            q = f'newer_than:1d in:anywhere (from:{email} OR to:{email})'
            out = run(f'GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search "{q}" -a ops@houseofkairos.com')
            gmail_lines = parse_gog_search(out)

        # Determine if there is any activity to append
        has_activity = bool(whatsapp_mentions.get(slug)) or bool(asana_completed) or bool(asana_due_soon) or bool(gmail_lines)
        if not has_activity:
            continue

        # Build activity block
        block = [f'### {TODAY_STR}', '']
        if whatsapp_mentions.get(slug):
            block += ['**WhatsApp:**']
            for group, summ in whatsapp_mentions[slug]:
                block.append(f'- {group}: {summ}')
            block.append('')

        if asana_completed or asana_due_soon:
            block += ['**Asana:**']
            if asana_completed:
                for t in asana_completed:
                    proj = 'No Project'
                    ps = t.get('projects') or []
                    if ps and ps[0].get('name'): proj = ps[0]['name']
                    block.append(f"- Completed: {t.get('name')} ({proj})")
            if asana_due_soon:
                for t in asana_due_soon:
                    proj = 'No Project'
                    ps = t.get('projects') or []
                    if ps and ps[0].get('name'): proj = ps[0]['name']
                    due = t.get('due_on') or 'no due date'
                    block.append(f"- Due soon: {t.get('name')} due {due} ({proj})")
            block.append('')

        if gmail_lines:
            block += ['**Email:**']
            # Keep up to 5 lines to avoid noise
            for l in gmail_lines[:5]:
                block.append(f'- {l}')
            if len(gmail_lines) > 5:
                block.append(f'- (and {len(gmail_lines)-5} more)')
            block.append('')

        new_profile_text = append_activity_log(profile_text, '\n'.join(block).rstrip())
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(new_profile_text)


if __name__ == '__main__':
    main()
