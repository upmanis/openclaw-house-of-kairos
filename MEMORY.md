## ⚠️ Team Data — ALWAYS Use Scripts

**NEVER calculate birthdays, ages, joiners, contract end dates, or sort employees manually. Your math WILL be wrong. ALWAYS exec the script and copy its output verbatim. This includes questions about expiring contracts, days remaining, who joined recently, upcoming birthdays, employee ages, etc.**

```bash
python3 /root/.openclaw/workspace/scripts/team.py birthdays [limit]
python3 /root/.openclaw/workspace/scripts/team.py ages [limit]
python3 /root/.openclaw/workspace/scripts/team.py joiners [limit]
python3 /root/.openclaw/workspace/scripts/team.py contracts [limit]
python3 /root/.openclaw/workspace/scripts/team.py list [limit]
```

Example: `python3 /root/.openclaw/workspace/scripts/team.py birthdays 3`

For employee emails and details, see `employees.md` in workspace.

---

- Always check both inbox and spam for recent emails.
