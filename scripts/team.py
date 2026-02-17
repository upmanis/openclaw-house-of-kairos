#!/usr/bin/env python3
"""House of Kairos team info utility.

Usage:
  python3 team.py birthdays [limit]   — upcoming birthdays sorted by next occurrence
  python3 team.py ages [limit]        — all employees sorted by name with current age
  python3 team.py joiners [limit]     — latest joiners sorted by join date (newest first)
  python3 team.py list                — full team list sorted by name
  python3 team.py birthday-alert      — show today's and tomorrow's birthdays (for alerts)
  python3 team.py contracts [limit]   — contracts ending soonest (nearest end date first)
"""
import sys
from datetime import date

today = date.today()

# (name, role, birth_year, birth_month, birth_day, join_year, join_month, join_day, end_date_str)
# end_date_str is "YYYY-MM-DD" or None if no contract end date
team = [
    ("Nicolas Castrillon", "General Manager", 1989, 11, 28, 2024, 8, 1, None),
    ("Kaspars Upmanis", "Founder/Owner", 1984, 12, 20, 2024, 12, 1, None),
    ("Yohanes Baptista", "", 1999, 2, 8, 2025, 1, 28, "2026-01-27"),
    ("Sakinah Dava Erawan", "Marketing Manager", 2000, 10, 30, 2025, 4, 7, "2026-04-06"),
    ("Nisya Nur Ayuna", "HR Manager", 1986, 4, 2, 2025, 5, 1, "2026-05-24"),
    ("Laila Karimah", "", 2000, 2, 1, 2025, 7, 22, None),
    ("I Putu Dimas", "F&B Manager", 1992, 12, 17, 2025, 9, 1, "2026-08-31"),
    ("Gints Valdmanis", "Fitness Manager", 1983, 12, 14, 2025, 9, 1, "2026-08-31"),
    ("I Komang Ariawan", "", 2003, 2, 2, 2025, 9, 1, "2026-08-31"),
    ("Alpin Brahmana", "", 2003, 12, 11, 2025, 9, 1, "2026-08-31"),
    ("Kelvin De Araujo", "", 2005, 12, 26, 2025, 11, 10, "2026-11-09"),
    ("Annisa Dwi Pramuningrum", "", 1995, 4, 19, 2025, 11, 24, "2026-11-23"),
    ("Andy S", "Head Chef", 1995, 7, 4, 2025, 11, 24, "2026-11-23"),
    ("Bintang Cahya", "", 2001, 11, 2, 2026, 1, 20, "2027-01-19"),
    ("I Putu Vinda Bramasta", "", 2001, 11, 5, 2026, 1, 19, "2027-01-18"),
    ("I Putu Agus Sudarmawan", "", 1992, 8, 27, 2026, 1, 19, "2027-01-18"),
    ("Gede Andre Danayasa", "", 2002, 7, 18, 2026, 1, 21, "2027-01-20"),
    ("I Kadek Oka Utama", "", 1997, 10, 14, 2026, 2, 2, "2027-02-01"),
]

cmd = sys.argv[1] if len(sys.argv) > 1 else "birthdays"
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 99


def get_age(birth_year, m, d):
    return today.year - birth_year - (1 if (today.month, today.day) < (m, d) else 0)


def tag(role):
    return " (%s)" % role if role else ""


if cmd == "birthdays":
    results = []
    for name, role, by, bm, bd, jy, jm, jd, ed in team:
        next_bday = date(today.year, bm, bd)
        if next_bday < today:
            next_bday = date(today.year + 1, bm, bd)
        days_away = (next_bday - today).days
        age = get_age(by, bm, bd)
        results.append((days_away, next_bday, name, role, age))
    results.sort()
    for i, (days, bday, name, role, age) in enumerate(results[:limit], 1):
        print("%d. %s%s — %s (age %d) — in %d days" % (
            i, name, tag(role), bday.strftime("%b %d"), age, days))

elif cmd == "ages":
    results = []
    for name, role, by, bm, bd, jy, jm, jd, ed in team:
        age = get_age(by, bm, bd)
        results.append((name, role, age, date(by, bm, bd)))
    results.sort(key=lambda x: x[0])
    for i, (name, role, age, bday) in enumerate(results[:limit], 1):
        print("%d. %s%s — %d years old (born %s)" % (
            i, name, tag(role), age, bday.strftime("%Y-%m-%d")))

elif cmd == "joiners":
    results = []
    for name, role, by, bm, bd, jy, jm, jd, ed in team:
        join_date = date(jy, jm, jd)
        results.append((join_date, name, role))
    results.sort(reverse=True)  # newest first
    for i, (jd, name, role) in enumerate(results[:limit], 1):
        print("%d. %s%s — joined %s" % (i, name, tag(role), jd.strftime("%Y-%m-%d")))

elif cmd == "contracts":
    results = []
    expired = []
    for name, role, by, bm, bd, jy, jm, jd, ed in team:
        if ed is None:
            continue
        end_date = date(*map(int, ed.split("-")))
        days_left = (end_date - today).days
        if days_left < 0:
            expired.append((end_date, name, role, -days_left))
        else:
            results.append((end_date, days_left, name, role))
    results.sort()
    for i, (end, days_left, name, role) in enumerate(results[:limit], 1):
        print("%d. %s%s — ends %s (in %d days)" % (
            i, name, tag(role), end.strftime("%Y-%m-%d"), days_left))
    if expired:
        print()
        print("EXPIRED:")
        for end, name, role, ago in sorted(expired):
            print("  %s%s — ended %s (%d days ago)" % (
                name, tag(role), end.strftime("%Y-%m-%d"), ago))

elif cmd == "list":
    results = []
    for name, role, by, bm, bd, jy, jm, jd, ed in team:
        age = get_age(by, bm, bd)
        join_date = date(jy, jm, jd)
        end_str = ed if ed else "—"
        results.append((name, role, age, date(by, bm, bd), join_date, end_str))
    results.sort(key=lambda x: x[0])
    for i, (name, role, age, bday, jd, end) in enumerate(results[:limit], 1):
        print("%d. %s%s — age %d (born %s) — joined %s — contract ends %s" % (
            i, name, tag(role), age, bday.strftime("%Y-%m-%d"), jd.strftime("%Y-%m-%d"), end))

elif cmd == "birthday-alert":
    from datetime import timedelta
    tomorrow = today + timedelta(days=1)
    today_bdays = []
    tomorrow_bdays = []
    for name, role, by, bm, bd, jy, jm, jd, ed in team:
        age = get_age(by, bm, bd)
        if (today.month, today.day) == (bm, bd):
            today_bdays.append((name, role, age))
        if (tomorrow.month, tomorrow.day) == (bm, bd):
            next_age = age + 1 if (today.month, today.day) < (bm, bd) else age
            tomorrow_bdays.append((name, role, next_age))
    if today_bdays:
        print("TODAY:")
        for name, role, age in today_bdays:
            print("  %s%s turns %d today!" % (name, tag(role), age))
    if tomorrow_bdays:
        print("TOMORROW:")
        for name, role, age in tomorrow_bdays:
            print("  %s%s turns %d tomorrow" % (name, tag(role), age))
    if not today_bdays and not tomorrow_bdays:
        print("NONE")

else:
    print("Unknown command: %s" % cmd)
    print("Usage: python3 team.py [birthdays|ages|joiners|contracts|list|birthday-alert] [limit]")
    sys.exit(1)
