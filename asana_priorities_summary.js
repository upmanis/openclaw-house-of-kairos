#!/usr/bin/env node
/* Daily priorities summary from Asana: My Tasks + CONSTRUCTION CHECKLIST project.
   Requires ASANA_TOKEN in env.
*/

const ASANA_BASE = 'https://app.asana.com/api/1.0';
const token = process.env.ASANA_TOKEN;
if (!token) {
  console.error('Missing ASANA_TOKEN env var');
  process.exit(2);
}

const TZ = 'Asia/Makassar';

function ymdInTZ(date = new Date(), timeZone = TZ) {
  // en-CA yields YYYY-MM-DD
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(date);
}

function addDays(ymd, days) {
  // ymd is YYYY-MM-DD, interpret as UTC midnight for arithmetic; safe for comparisons on date-only.
  const [y, m, d] = ymd.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  return ymdInTZ(dt, 'UTC'); // returns YYYY-MM-DD in UTC (same as dt date)
}

function cmpYmd(a, b) {
  // lexicographic works for YYYY-MM-DD
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

async function asanaGet(path, params = {}) {
  const url = new URL(ASANA_BASE + path);
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Accept': 'application/json'
    }
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Asana GET ${url} failed: ${res.status} ${res.statusText}\n${text}`);
  }
  return res.json();
}

async function listAll(path, params = {}) {
  let offset;
  const out = [];
  while (true) {
    const json = await asanaGet(path, { ...params, offset });
    if (Array.isArray(json.data)) out.push(...json.data);
    offset = json.next_page?.offset;
    if (!offset) break;
  }
  return out;
}

function simplifyTask(t) {
  const due = t.due_on || null;
  const section = (t.memberships && t.memberships[0] && t.memberships[0].section && t.memberships[0].section.name) ? t.memberships[0].section.name : null;
  const projectName = (t.memberships && t.memberships[0] && t.memberships[0].project && t.memberships[0].project.name) ? t.memberships[0].project.name : null;
  return {
    gid: t.gid,
    name: t.name,
    due_on: due,
    section,
    project: projectName,
    permalink_url: t.permalink_url
  };
}

function dedupeByGid(tasks) {
  const m = new Map();
  for (const t of tasks) {
    if (!t?.gid) continue;
    if (!m.has(t.gid)) m.set(t.gid, t);
  }
  return [...m.values()];
}

function categorize(tasks, todayYmd) {
  const tomorrow = addDays(todayYmd, 1);
  const day7 = addDays(todayYmd, 7);
  const day14 = addDays(todayYmd, 14);

  const buckets = {
    overdue: [],
    today: [],
    soon7: [],
    soon14: [],
    noDue: []
  };

  for (const t of tasks) {
    const due = t.due_on;
    if (!due) {
      buckets.noDue.push(t);
      continue;
    }
    if (cmpYmd(due, todayYmd) < 0) buckets.overdue.push(t);
    else if (due === todayYmd) buckets.today.push(t);
    else if (cmpYmd(due, tomorrow) >= 0 && cmpYmd(due, day7) <= 0) buckets.soon7.push(t);
    else if (cmpYmd(due, addDays(todayYmd, 8)) >= 0 && cmpYmd(due, day14) <= 0) buckets.soon14.push(t);
    else {
      // ignore later
    }
  }

  const byDueThenName = (a, b) => {
    if (a.due_on && b.due_on && a.due_on !== b.due_on) return a.due_on.localeCompare(b.due_on);
    return (a.name || '').localeCompare(b.name || '');
  };

  for (const k of Object.keys(buckets)) buckets[k].sort(byDueThenName);
  return buckets;
}

function fmtLine(t) {
  const due = t.due_on ? t.due_on : '—';
  const where = [t.project, t.section].filter(Boolean).join(' / ');
  const whereStr = where ? ` (${where})` : '';
  const link = t.permalink_url ? `\n${t.permalink_url}` : '';
  return `• ${t.name} — ${due}${whereStr}${link}`;
}

function buildMessage({ todayYmd, buckets, counts }) {
  const lines = [];
  lines.push(`DAILY PRIORITIES SUMMARY (Asana) — ${todayYmd} (Bali/WITA)`);

  const top = [...buckets.overdue, ...buckets.today].slice(0, 10);
  lines.push('');
  lines.push('*OVERDUE + TODAY*');
  if (top.length === 0) {
    lines.push('• None 🎉');
  } else {
    for (const t of top) lines.push(fmtLine(t));
    const remaining = (buckets.overdue.length + buckets.today.length) - top.length;
    if (remaining > 0) lines.push(`• (+${remaining} more)`);
  }

  const soon = buckets.soon7.slice(0, 10);
  lines.push('');
  lines.push('*DUE SOON (next 7 days)*');
  if (soon.length === 0) lines.push('• None');
  else {
    for (const t of soon) lines.push(fmtLine(t));
    const remaining = buckets.soon7.length - soon.length;
    if (remaining > 0) lines.push(`• (+${remaining} more)`);
  }

  const notes = [];
  if (counts.noDue > 20) notes.push(`You have ${counts.noDue} tasks with no due date — consider adding due dates for the most important ones.`);
  if (counts.overdue > 10) notes.push(`${counts.overdue} overdue tasks — consider a quick prune/deferral sweep.`);
  if ((counts.overdue + counts.today + counts.soon7) === 0 && counts.soon14 > 0) notes.push(`Nothing due within 7 days; next up: ${counts.soon14} tasks due in 8–14 days.`);

  if (notes.length) {
    lines.push('');
    lines.push('*NOTES / NEXT ACTIONS*');
    for (const n of notes.slice(0, 3)) lines.push(`• ${n}`);
  }

  return lines.join('\n');
}

async function main() {
  const todayYmd = ymdInTZ(new Date(), TZ);

  const me = await asanaGet('/users/me', { opt_fields: 'gid,name' });
  const userGid = me.data.gid;

  // Choose first workspace available.
  const workspaces = await asanaGet('/workspaces', { opt_fields: 'gid,name' });
  const ws = workspaces.data[0];
  if (!ws) throw new Error('No Asana workspace found');

  const optFields = [
    'gid',
    'name',
    'due_on',
    'permalink_url',
    'completed',
    'memberships.project.name',
    'memberships.section.name'
  ].join(',');

  const myTasksRaw = await listAll('/tasks', {
    assignee: userGid,
    workspace: ws.gid,
    completed_since: 'now',
    opt_fields: optFields,
    limit: 100
  });

  // Find CONSTRUCTION CHECKLIST project
  const projects = await listAll('/projects', {
    workspace: ws.gid,
    archived: false,
    opt_fields: 'gid,name',
    limit: 100
  });
  const construction = projects.find(p => (p.name || '').trim().toUpperCase() === 'CONSTRUCTION CHECKLIST');

  let projectTasksRaw = [];
  if (construction?.gid) {
    projectTasksRaw = await listAll('/tasks', {
      project: construction.gid,
      completed_since: 'now',
      opt_fields: optFields,
      limit: 100
    });
  }

  const tasks = dedupeByGid([
    ...myTasksRaw.map(simplifyTask),
    ...projectTasksRaw.map(simplifyTask)
  ]);

  const buckets = categorize(tasks, todayYmd);
  const counts = {
    overdue: buckets.overdue.length,
    today: buckets.today.length,
    soon7: buckets.soon7.length,
    soon14: buckets.soon14.length,
    noDue: buckets.noDue.length
  };

  const msg = buildMessage({ todayYmd, buckets, counts });
  process.stdout.write(msg);
}

main().catch(err => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
