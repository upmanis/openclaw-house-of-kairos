#!/usr/bin/env python3
"""Query the HOK OS database via the openclaw-query Edge Function.

Usage:
    python3 scripts/hok-query.py schema
    python3 scripts/hok-query.py revenue-month
    python3 scripts/hok-query.py member-count
    python3 scripts/hok-query.py "SELECT count(*) FROM members WHERE deleted_at IS NULL"
    python3 scripts/hok-query.py --staging revenue-month
"""
import sys, json, urllib.request, urllib.error

ENDPOINTS = {
    "production": {
        "url": "https://tsmkchtfljmfvwqurbxy.supabase.co/functions/v1/openclaw-query",
        "key": "28I+FBXuGhNWO+UivrJFjRw1Gd1Bj7FyTnD/M768uLs="
    },
    "staging": {
        "url": "https://ktrskhlxroktiruyrdcm.supabase.co/functions/v1/openclaw-query",
        "key": "s/xX6J2zsySDMa0Ss9IV/SIlw4nOPoWj/EvfX38tboo="
    }
}

# Preset queries — use these instead of writing SQL
PRESETS = {
    "member-count": "SELECT count(*) as active_members FROM members WHERE deleted_at IS NULL",
    "revenue-month": "SELECT coalesce(sum(price), 0) as revenue_idr FROM memberships WHERE created_at >= date_trunc('month', now())",
    "revenue-all": "SELECT coalesce(sum(price), 0) as revenue_idr FROM memberships",
    "revenue-by-method": "SELECT payment_method, sum(price) as total, count(*) as count FROM memberships GROUP BY payment_method ORDER BY total DESC",
    "memberships-active": "SELECT count(*) as active FROM memberships WHERE status = 'valid' AND end_date >= now()",
    "memberships-month": "SELECT count(*) as new_memberships FROM memberships WHERE created_at >= date_trunc('month', now())",
    "checkins-today": "SELECT count(*) as checkins FROM check_ins WHERE timestamp::date = now()::date",
    "checkins-yesterday": "SELECT count(*) as checkins FROM check_ins WHERE timestamp::date = (now() - interval '1 day')::date",
    "classes-today": "SELECT c.title, c.start_time, c.end_time, co.name as coach FROM classes c LEFT JOIN coaches co ON c.coach_id = co.id WHERE c.start_time::date = now()::date ORDER BY c.start_time",
    "classes-tomorrow": "SELECT c.title, c.start_time, c.end_time, co.name as coach FROM classes c LEFT JOIN coaches co ON c.coach_id = co.id WHERE c.start_time::date = (now() + interval '1 day')::date ORDER BY c.start_time",
    "joined-week": "SELECT first_name, last_name, created_at FROM members WHERE deleted_at IS NULL AND created_at >= now() - interval '7 days' ORDER BY created_at DESC",
    "yesterday-stats": "SELECT (SELECT count(*) FROM check_ins WHERE timestamp::date = (now() - interval '1 day')::date) as checkins, (SELECT count(*) FROM memberships WHERE created_at::date = (now() - interval '1 day')::date) as new_memberships, (SELECT coalesce(sum(price), 0) FROM memberships WHERE created_at::date = (now() - interval '1 day')::date) as sales_idr",
}

def main():
    args = sys.argv[1:]
    env = "production"
    if "--staging" in args:
        args.remove("--staging")
        env = "staging"

    if not args:
        print("Usage: python3 scripts/hok-query.py [--staging] <command>")
        print("\nPreset commands:")
        for name in sorted(PRESETS):
            print("  {}".format(name))
        print("\nOr pass a raw SQL SELECT query in quotes.")
        sys.exit(1)

    ep = ENDPOINTS[env]
    query = " ".join(args)

    if query.lower() == "schema":
        req = urllib.request.Request(ep["url"], headers={"x-api-key": ep["key"]})
    elif query.lower() in PRESETS:
        sql = PRESETS[query.lower()]
        body = json.dumps({"sql": sql}).encode()
        req = urllib.request.Request(
            ep["url"], data=body,
            headers={"x-api-key": ep["key"], "Content-Type": "application/json"},
            method="POST"
        )
    else:
        body = json.dumps({"sql": query}).encode()
        req = urllib.request.Request(
            ep["url"], data=body,
            headers={"x-api-key": ep["key"], "Content-Type": "application/json"},
            method="POST"
        )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print("Error ({}): {}".format(e.code, err), file=sys.stderr)
        sys.exit(1)

    if "schema" in data:
        print(data["schema"])
    elif "data" in data:
        rows = data["data"]
        count = data.get("rowCount", len(rows))
        if not rows:
            print("No results.")
        elif len(rows) == 1 and len(rows[0]) <= 3:
            for k, v in rows[0].items():
                if isinstance(v, (int, float)) and v >= 1000:
                    print("{}: Rp {:,.0f}".format(k, v) if "idr" in k.lower() or "revenue" in k.lower() or "sales" in k.lower() or "total" in k.lower() or "price" in k.lower() else "{}: {}".format(k, v))
                else:
                    print("{}: {}".format(k, v))
        else:
            keys = list(rows[0].keys())
            print(" | ".join(keys))
            print("-" * (len(" | ".join(keys))))
            for row in rows:
                print(" | ".join(str(row.get(k, "")) for k in keys))
        suffix = "s" if count != 1 else ""
        print("\n({} row{})".format(count, suffix))
    else:
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
