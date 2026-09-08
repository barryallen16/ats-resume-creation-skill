#!/usr/bin/env python3
"""Push recorded applications into the Grey Matter web tracker.

Reads <data-dir>/applications/applications_index.json (written by
resume_store.py app add) and merges each entry into the Grey Matter
tracker, so entries show up on the phone at /tracker/ without manual
retyping.

Idempotent: entries are keyed by the skill's application id — re-running
after `app update-status` updates the existing entry in place instead of
duplicating it.

Usage:
    python3 scripts/tracker_push.py [--data-dir DIR] [--url URL]

    --url  Grey Matter base URL. Default: $GREYMATTER_URL or
           http://127.0.0.1:8080 (local API). On the VPS use:
           --url https://greymatter.isroot.in

Status mapping (skill -> web tracker):
    drafted      -> saved
    applied      -> applied
    interviewing -> interview
    offer        -> offer
    rejected     -> rejected
    withdrawn    -> rejected   (web tracker has no withdrawn stage)
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

KEY = "tracker-apps-v1"

STATUS_MAP = {
    "drafted": "saved",
    "applied": "applied",
    "interviewing": "interview",
    "offer": "offer",
    "rejected": "rejected",
    "withdrawn": "rejected",
}


def kv_get(base):
    """Current tracker array from the Grey Matter KV API ([] if empty)."""
    try:
        with urllib.request.urlopen(f"{base}/api/store/{KEY}", timeout=10) as r:
            data = json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        sys.exit(f"GET {base}/api/store/{KEY} failed: HTTP {e.code}")
    except urllib.error.URLError as e:
        sys.exit(
            f"Cannot reach Grey Matter at {base} ({e.reason}).\n"
            "Local:   PORT=8080 python api/main.py   (from the job-search repo)\n"
            "VPS:     docker compose up -d --build    then pass --url https://greymatter.isroot.in"
        )
    return data if isinstance(data, list) else []


def kv_put(base, apps):
    req = urllib.request.Request(
        f"{base}/api/store/{KEY}",
        data=json.dumps(apps).encode("utf-8"),
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        if r.status != 200:
            sys.exit(f"PUT failed: HTTP {r.status}")


def to_epoch_ms(iso):
    try:
        return int(datetime.datetime.fromisoformat(iso).timestamp() * 1000)
    except ValueError:
        return int(datetime.datetime.now().timestamp() * 1000)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default="resume_data",
                    help="resume_store.py data dir (default: ./resume_data)")
    ap.add_argument("--url", default=os.environ.get("GREYMATTER_URL", "http://127.0.0.1:8080"),
                    help="Grey Matter base URL (default: $GREYMATTER_URL or http://127.0.0.1:8080)")
    args = ap.parse_args()

    index_path = os.path.join(args.data_dir, "applications", "applications_index.json")
    if not os.path.exists(index_path):
        sys.exit(f"No applications at {index_path} — run resume_store.py app add first.")
    with open(index_path, encoding="utf-8") as f:
        local = json.load(f)
    if not local:
        sys.exit(f"{index_path} is empty — nothing to push.")

    apps = kv_get(args.url)
    by_id = {a.get("id"): a for a in apps}

    added = updated = 0
    for rec in local:
        entry = {
            "id": rec["id"],
            "company": rec.get("company", ""),
            "role": rec.get("role", ""),
            "link": rec.get("link", ""),
            "type": rec.get("type", ""),
            "status": STATUS_MAP.get(rec.get("status", "drafted"), "saved"),
            "followup": rec.get("followup", ""),
            "notes": rec.get("notes", "ats-resume-skill"),
            "created": to_epoch_ms(rec.get("date_created", "")),
        }
        if rec["id"] in by_id:
            by_id[rec["id"]].update(entry)
            updated += 1
        else:
            apps.append(entry)
            added += 1

    kv_put(args.url, apps)
    print(f"Synced to {args.url}: {added} added, {updated} updated ({len(apps)} total on the tracker).")


if __name__ == "__main__":
    main()
