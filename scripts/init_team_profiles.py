#!/usr/bin/env python3
"""Initialize employee context profiles for House of Kairos.

Creates:
  - team/<slug>.md   for each employee (skeleton profile)
  - team/_aliases.json  name-variant -> slug mapping

Safe to re-run: skips employees whose profile already exists.
New employees added to team.py + employees.md will get profiles on next run.

Usage:
  python3 init_team_profiles.py               # normal run
  python3 init_team_profiles.py --force        # recreate ALL profiles (destructive)
"""

import json
import os
import re
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAM_DIR = os.path.join(WORKSPACE, "team")
EMPLOYEES_MD = os.path.join(WORKSPACE, "employees.md")
ALIASES_FILE = os.path.join(TEAM_DIR, "_aliases.json")

# ---------------------------------------------------------------------------
# Employee data from employees.md (parsed) and team.py (short names / dates)
# ---------------------------------------------------------------------------

# Canonical employee records keyed by ID.
# Fields: legal, role, email, join_date, end_date, birthday
# Parsed from employees.md table at runtime.

# Phone numbers keyed by slug (from WhatsApp session data).
# Employees not yet seen in WhatsApp have no entry here.
PHONE_MAP = {
    "kaspars-upmanis": "+37120000453",
    "nicolas-castrillon": "+6281238198668",
    "nisya-nur-ayuna": "+6281928883368",
    "i-putu-dimas": "+6281337284068",
    "gints-valdmanis": "+37126188818",
    "andy-s": "+628979079933",
    "sakinah-dava-erawan": "+6285333762956",
    "yohanes-baptista": "+6281348476929",
    "laila-karimah": "+6281227214091",
}

# WhatsApp display names keyed by slug (as they appear in chat metadata).
WHATSAPP_NAME_MAP = {
    "kaspars-upmanis": "Kaspars Upmanis",
    "nicolas-castrillon": "Nicolas C.",
    "nisya-nur-ayuna": "Nisya A.",
    "i-putu-dimas": "Putu Dimas",
    "gints-valdmanis": "Gints Valdmanis",
    "andy-s": "Jonathan Andy",
    "sakinah-dava-erawan": "Sakinah",
    "yohanes-baptista": "Vikrama",
}

# Nickname overrides: legal name -> list of preferred first-name aliases
NICKNAME_OVERRIDES = {
    "Yohanes Baptista Vikramaimanthaka": ["Vikrama"],
    "Christopher Jonathan Andy S": ["Andy"],
    "I Putu Dimas Abdi Saputra": ["Dimas"],
    "I Komang Ariawan Widnyana": ["Komang", "Ariawan"],
    "Kelvin Nathanael De Araujo": ["Kelvin"],
    "I Putu Vinda Bramasta": ["Vinda"],
    "I Putu Agus Sudarmawan": ["Agus"],
    "Gede Andre Danayasa": ["Andre"],
    "I Kadek Oka Utama": ["Oka"],
    "Bintang Cahya Tri Sukma": ["Bintang"],
    "Annisa Dwi Pramuningrum": ["Annisa"],
}

# team.py short names -> legal names mapping (for cross-reference)
TEAM_PY_SHORT_TO_LEGAL = {
    "Nicolas Castrillon": "Nicolas Andres Castrillon Baranovski",
    "Kaspars Upmanis": "Kaspars Upmanis",
    "Yohanes Baptista": "Yohanes Baptista Vikramaimanthaka",
    "Sakinah Dava Erawan": "Sakinah Dava Erawan",
    "Nisya Nur Ayuna": "Nisya Nur Ayuna",
    "Laila Karimah": "Laila Karimah",
    "I Putu Dimas": "I Putu Dimas Abdi Saputra",
    "Gints Valdmanis": "Gints Valdmanis",
    "I Komang Ariawan": "I Komang Ariawan Widnyana",
    "Alpin Brahmana": "Alpin Brahmana",
    "Kelvin De Araujo": "Kelvin Nathanael De Araujo",
    "Annisa Dwi Pramuningrum": "Annisa Dwi Pramuningrum",
    "Andy S": "Christopher Jonathan Andy S",
    "Bintang Cahya": "Bintang Cahya Tri Sukma",
    "I Putu Vinda Bramasta": "I Putu Vinda Bramasta",
    "I Putu Agus Sudarmawan": "I Putu Agus Sudarmawan",
    "Gede Andre Danayasa": "Gede Andre Danayasa",
    "I Kadek Oka Utama": "I Kadek Oka Utama",
}


def parse_employees_md(path):
    """Parse the employees.md markdown table into a list of dicts."""
    employees = []
    with open(path) as f:
        lines = f.readlines()

    in_table = False
    for line in lines:
        line = line.strip()
        if line.startswith("| ID"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 7:
                emp = {
                    "id": cols[0],
                    "legal": cols[1],
                    "role": cols[2] if cols[2] != "\u2014" else "",
                    "email": cols[3],
                    "join_date": cols[4],
                    "end_date": cols[5] if cols[5] != "\u2014" else "---",
                    "birthday": cols[6],
                }
                employees.append(emp)
        elif in_table and not line.startswith("|"):
            break

    return employees


def make_slug(legal_name):
    """Convert a legal name to a filename slug.

    Examples:
        Nicolas Andres Castrillon Baranovski -> nicolas-castrillon
        I Putu Dimas Abdi Saputra -> i-putu-dimas
        Christopher Jonathan Andy S -> andy-s
    """
    # Use the short name from team.py mapping if available
    short = None
    for s, l in TEAM_PY_SHORT_TO_LEGAL.items():
        if l == legal_name:
            short = s
            break

    name = short if short else legal_name
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


def build_aliases(emp, slug):
    """Build alias variants for an employee."""
    legal = emp["legal"]
    parts = legal.split()
    first = parts[0]

    # Start with the short name from team.py
    short = None
    for s, l in TEAM_PY_SHORT_TO_LEGAL.items():
        if l == legal:
            short = s
            break
    short = short or legal

    # Build alias list
    aliases = set()

    # Add nickname overrides
    if legal in NICKNAME_OVERRIDES:
        for nick in NICKNAME_OVERRIDES[legal]:
            aliases.add(nick)
        # Use first nickname as the "first" name
        first_alias = NICKNAME_OVERRIDES[legal][0]
    else:
        first_alias = first
        aliases.add(first)

    # Add last name if it's distinctive (not "I", "S", etc.)
    if short:
        short_parts = short.split()
        for p in short_parts:
            if len(p) > 1:
                aliases.add(p)

    # Add all legal name parts that are >1 char
    for p in parts:
        if len(p) > 1:
            aliases.add(p)

    # Remove common prefixes that aren't distinctive
    aliases.discard("Putu")
    aliases.discard("Kadek")
    aliases.discard("Gede")
    aliases.discard("Komang")

    # Re-add if they're an explicit nickname override
    if legal in NICKNAME_OVERRIDES:
        for nick in NICKNAME_OVERRIDES[legal]:
            aliases.add(nick)

    # Add WhatsApp display name to aliases if it exists and is distinctive
    wa_name = WHATSAPP_NAME_MAP.get(slug)
    if wa_name and wa_name not in aliases:
        aliases.add(wa_name)

    phone = PHONE_MAP.get(slug)

    return {
        "legal": legal,
        "short": short,
        "first": first_alias,
        "aliases": sorted(aliases),
        "email": emp["email"],
        "phone": phone,
        "whatsapp_name": wa_name,
    }


def make_profile(emp):
    """Generate the markdown profile skeleton."""
    return f"""# {emp['legal']}

| Field | Value |
|---|---|
| **ID** | {emp['id']} |
| **Role** | {emp['role'] or '---'} |
| **Email** | {emp['email']} |
| **Join Date** | {emp['join_date']} |
| **End Date** | {emp['end_date']} |
| **Birthday** | {emp['birthday']} |

---

## Activity Log
"""


def main():
    force = "--force" in sys.argv

    # Parse employees
    employees = parse_employees_md(EMPLOYEES_MD)
    print(f"Parsed {len(employees)} employees from employees.md")

    # Create team directory
    os.makedirs(TEAM_DIR, exist_ok=True)

    # Generate profiles
    aliases = {}
    created = 0
    skipped = 0

    for emp in employees:
        slug = make_slug(emp["legal"])
        filepath = os.path.join(TEAM_DIR, f"{slug}.md")

        # Always build aliases (even for existing profiles)
        aliases[slug] = build_aliases(emp, slug)

        if os.path.exists(filepath) and not force:
            print(f"  SKIP {slug}.md (already exists)")
            skipped += 1
            continue

        with open(filepath, "w") as f:
            f.write(make_profile(emp))
        print(f"  CREATE {slug}.md")
        created += 1

    # Write aliases file (always overwritten to pick up new employees)
    with open(ALIASES_FILE, "w") as f:
        json.dump(aliases, f, indent=2, ensure_ascii=False)
    print(f"\nWrote _aliases.json with {len(aliases)} entries")

    print(f"\nDone: {created} created, {skipped} skipped")


if __name__ == "__main__":
    main()
