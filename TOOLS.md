# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

## Asana — House of Kairos

You have full API access to the House of Kairos Asana workspace via `ASANA_TOKEN` (already in your environment).

### Workspace

- **Workspace GID:** `1208695572000101`
- **Workspace name:** House of Kairos

### Projects

| GID | Project |
|-----|---------|
| 1208705090521783 | General Timeline |
| 1208771583102101 | CONSTRUCTION CHECKLIST |
| 1208771583102212 | F&B |
| 1208779826982626 | Recruitment |
| 1208814711748515 | CRM & Mobile App |
| 1208868712398357 | Marketing |
| 1209429425610210 | PA tasks |
| 1210285702711160 | Operations |
| 1210383979101819 | HR |
| 1211596101449010 | Marketing - Thumbcrumble |
| 1211820105476765 | Marketing - Janis Project |
| 1211845297723780 | Marketing - Merch |
| 1212602232370923 | Printed |
| 1213111337708211 | Marketing - Pre-sales campaign |
| 1213200794602805 | Architecture |

### How to query Asana

Use `curl` with the `ASANA_TOKEN` env var. Do NOT use node-fetch or require(). Avoid JS template literals in bash.

**IMPORTANT: Always use `curl`, not Node.js, for Asana API calls.** This avoids bash escaping issues.

```bash
# List incomplete tasks for a project
curl -s -H "Authorization: Bearer $ASANA_TOKEN" \
  "https://app.asana.com/api/1.0/tasks?project=PROJECT_GID&completed_since=now&opt_fields=name,due_on,assignee.name"

# Search tasks across workspace
curl -s -H "Authorization: Bearer $ASANA_TOKEN" \
  "https://app.asana.com/api/1.0/workspaces/1208695572000101/tasks/search?text=SEARCH_TERM&completed=false&opt_fields=name,due_on,projects.name,assignee.name"

# Get a single task by GID
curl -s -H "Authorization: Bearer $ASANA_TOKEN" \
  "https://app.asana.com/api/1.0/tasks/TASK_GID?opt_fields=name,due_on,notes,assignee.name,completed,projects.name"
```

### Parsing results

Use `python3` to format the JSON output (it's always available):

```bash
curl -s -H "Authorization: Bearer $ASANA_TOKEN" \
  "https://app.asana.com/api/1.0/tasks?project=PROJECT_GID&completed_since=now&opt_fields=name,due_on,assignee.name" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin).get('data', [])
for t in sorted(data, key=lambda x: x.get('due_on') or 'zzzz'):
    due = t.get('due_on') or 'no date'
    name = t.get('name', '?')
    assignee = (t.get('assignee') or {}).get('name', 'unassigned')
    print(f'{due} | {name} | {assignee}')
"
```

### Tips
- Use `completed_since=now` to get only incomplete tasks
- Use `opt_fields` to control what fields are returned
- For paginated results, check `next_page.uri` in response and follow it
- When asked "what's due this week" or "overdue tasks", filter by `due_on`
- Keep output WhatsApp-friendly: bullet lists, no tables
- **Never use node-fetch, require(), or JS template literals in exec commands**

---

## Gmail — ops@houseofkairos.com

You have read and send access to the House of Kairos operations inbox via `gog`.

**Important:** Always set `GOG_KEYRING_PASSWORD=openclaw-hok-2026` before running gog commands.

### Common commands

```bash
# Search recent emails (last 7 days)
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search 'newer_than:7d' -a ops@houseofkairos.com

# Search by sender
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search 'from:someone@example.com' -a ops@houseofkairos.com

# Search by subject
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search 'subject:invoice' -a ops@houseofkairos.com

# Read a specific message (use ID from search results)
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail get <messageId> -a ops@houseofkairos.com

# Combine queries
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail search 'newer_than:3d is:unread' -a ops@houseofkairos.com
```

### Gmail search syntax

- `newer_than:7d` — last 7 days
- `is:unread` — unread only
- `from:email` — by sender
- `subject:keyword` — by subject
- `has:attachment` — with attachments
- `label:INBOX` — inbox only

### Sending emails

```bash
# Send a simple email
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail send --to "recipient@example.com" --subject "Subject" --body "Email body" -a ops@houseofkairos.com

# Reply to a message (use message ID from search/get)
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail send --reply-to-message-id <messageId> --reply-all --body "Reply text" -a ops@houseofkairos.com

# Send with CC and attachment
GOG_KEYRING_PASSWORD=openclaw-hok-2026 gog gmail send --to "to@example.com" --cc "cc@example.com" --subject "Subject" --body "Body" --attach /path/to/file -a ops@houseofkairos.com
```

### Notes

- Account: `ops@houseofkairos.com` (House of Kairos operations)
- Access: **read + send** (gmail.modify scope)
- New emails are also pushed to you in real-time via Gmail Pub/Sub webhook
- **Sending to kaspars@houseofkairos.com** — allowed without asking
- **Sending to anyone else** — always ask Kaspars for approval first

---

## Team scripts

Add local team-management script usage and guidance here. These are the canonical commands for team data so you don't have to remember to run them manually.

**Rule:** NEVER calculate birthdays, ages, joiners, contract end dates, or sort employees manually. Use the scripts below and copy the output verbatim.

```bash
python3 /root/.openclaw/workspace/scripts/team.py birthdays [limit]
python3 /root/.openclaw/workspace/scripts/team.py ages [limit]
python3 /root/.openclaw/workspace/scripts/team.py joiners [limit]
python3 /root/.openclaw/workspace/scripts/team.py contracts [limit]
python3 /root/.openclaw/workspace/scripts/team.py list [limit]
```

Example: `python3 /root/.openclaw/workspace/scripts/team.py birthdays 3`

For employee emails and details, see `employees.md` in workspace.

- Tip: Always check both inbox and spam for recent emails related to HR or contracts.

### Employee Context Profiles

Per-employee activity logs live in `team/`. Updated daily by the `employee-context-update` cron job.

- **Profiles:** `team/<slug>.md` — one per employee
- **Aliases:** `team/_aliases.json` — name-variant mapping for WhatsApp parsing
- **Init script:** `python3 scripts/init_team_profiles.py` — creates new profiles (safe to re-run)
