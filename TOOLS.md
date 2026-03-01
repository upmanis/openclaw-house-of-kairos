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

## OpenClaw config (protected)

- In `openclaw.json`, keep `requireMention: false` so the agent receives *all* group messages and can log them verbatim. Do not change this to `true`.

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

**ALWAYS use the helper script** instead of inline curl|python. This avoids shell escaping issues.

```bash
# List incomplete tasks for a project (sorted by due date)
python3 scripts/asana-tasks.py PROJECT_GID

# With filters
python3 scripts/asana-tasks.py PROJECT_GID --assignee "Name"
python3 scripts/asana-tasks.py PROJECT_GID --overdue
python3 scripts/asana-tasks.py PROJECT_GID --due-this-week
python3 scripts/asana-tasks.py PROJECT_GID --due-next-week
python3 scripts/asana-tasks.py PROJECT_GID --due-before 2026-03-01
python3 scripts/asana-tasks.py PROJECT_GID --due-after 2026-02-15
python3 scripts/asana-tasks.py PROJECT_GID --no-date
python3 scripts/asana-tasks.py PROJECT_GID --completed

# Sorting and limiting
python3 scripts/asana-tasks.py PROJECT_GID --sort assignee   # sort by: date (default), assignee, name
python3 scripts/asana-tasks.py PROJECT_GID --sort date --reverse
python3 scripts/asana-tasks.py PROJECT_GID --limit 10

# Combine any filters
python3 scripts/asana-tasks.py PROJECT_GID --assignee "Kaspars" --due-this-week --sort date

# Search tasks across entire workspace
python3 scripts/asana-tasks.py search "search term"

# Get details of a specific task (includes subtasks)
python3 scripts/asana-tasks.py task TASK_GID

# List all projects with GIDs
python3 scripts/asana-tasks.py projects
```

**Fallback** (only if the script is unavailable): use `curl` with `$ASANA_TOKEN`:
```bash
curl -s -H "Authorization: Bearer $ASANA_TOKEN" \
  "https://app.asana.com/api/1.0/tasks?project=PROJECT_GID&completed_since=now&opt_fields=name,due_on,assignee.name"
```

### Tips
- **Prefer the script** — it handles pagination, sorting, overdue marking, and formatting automatically
- All dates use WITA timezone (UTC+8)
- Filters can be combined freely (e.g. `--assignee "Name" --due-this-week --sort name`)
- When asked "what's due this week" → use `--due-this-week`
- When asked "overdue tasks" → use `--overdue`
- When asked "unscheduled tasks" → use `--no-date`
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
python3 /Users/ai/openclaw/workspace/scripts/team.py birthdays [limit]
python3 /Users/ai/openclaw/workspace/scripts/team.py ages [limit]
python3 /Users/ai/openclaw/workspace/scripts/team.py joiners [limit]
python3 /Users/ai/openclaw/workspace/scripts/team.py contracts [limit]
python3 /Users/ai/openclaw/workspace/scripts/team.py list [limit]
```

Example: `python3 /Users/ai/openclaw/workspace/scripts/team.py birthdays 3`

For employee emails and details, see `employees.md` in workspace.

- Tip: Always check both inbox and spam for recent emails related to HR or contracts.
- **Org chart / reporting lines:** See inline org chart below. Full version also in `team/org-chart.md`.

### Org Chart — House of Kairos

Kaspars Upmanis — Founder / Owner
├── Nicolas Castrillon — General Manager
│   ├── Gints Valdmanis — Fitness Manager
│   ├── I Putu Dimas — F&B Manager
│   ├── Andy S — Head Chef
│   ├── Sakinah Dava Erawan — Marketing Manager
│   └── Nisya Nur Ayuna — HR Manager
└── Yohanes Baptista — IT/PA (dual report: Kaspars + Nicolas)

**Unassigned:** Laila Karimah (Finance), Kelvin De Araujo (Housekeeper), Bintang Cahya (Gym Attendant), Alpin Brahmana (Housekeeper)

### Employee Context Profiles

Per-employee activity logs live in `team/`. Updated daily by the `employee-context-update` cron job.

- **Profiles:** `team/<slug>.md` — one per employee
- **Aliases:** `team/_aliases.json` — name-variant mapping for WhatsApp parsing
- **Init script:** `python3 scripts/init_team_profiles.py` — creates new profiles (safe to re-run)

---

## HOK OS — Read-Only Query API

Query the HOK OS database. **Use presets whenever possible — they never fail.**

### Preset commands (PREFERRED — use these first!)

Via the helper script:
```bash
python3 scripts/hok-query.py member-count
python3 scripts/hok-query.py revenue-month
python3 scripts/hok-query.py revenue-all
python3 scripts/hok-query.py revenue-by-method
python3 scripts/hok-query.py memberships-active
python3 scripts/hok-query.py memberships-month
python3 scripts/hok-query.py checkins-today
python3 scripts/hok-query.py checkins-yesterday
python3 scripts/hok-query.py classes-today
python3 scripts/hok-query.py classes-tomorrow
python3 scripts/hok-query.py joined-week
python3 scripts/hok-query.py yesterday-stats
python3 scripts/hok-query.py schema
```

Or via curl (if the script is unavailable):
```bash
curl -s -X POST -H "x-api-key: 28I+FBXuGhNWO+UivrJFjRw1Gd1Bj7FyTnD/M768uLs=" -H "Content-Type: application/json" -d '{"preset": "revenue-month"}' "https://tsmkchtfljmfvwqurbxy.supabase.co/functions/v1/openclaw-query"
```

Available presets: member-count, revenue-month, revenue-all, revenue-by-method, memberships-active, memberships-month, checkins-today, checkins-yesterday, classes-today, classes-tomorrow, joined-week, yesterday-stats

### Custom queries (only when no preset fits)

```bash
python3 scripts/hok-query.py "SELECT first_name, last_name FROM members WHERE deleted_at IS NULL"
```

### Important

- **ALWAYS try a preset first** before writing custom SQL
- **There is NO payments table** — revenue is in `memberships.price`
- **ONLY members has deleted_at** — do NOT filter other tables by deleted_at
- Prices are in Indonesian Rupiah (IDR)
- Use `--staging` flag for staging environment