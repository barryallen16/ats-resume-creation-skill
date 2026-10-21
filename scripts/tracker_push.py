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
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import axi  # noqa: E402  (needs the sys.path.insert above)

DESCRIPTION = "Sync recorded applications to the Grey Matter web tracker"

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
        axi.fail(f"the tracker returned HTTP {e.code} for {base}/api/store/{KEY}",
                 hint="Check that the Grey Matter API is running at that address")
    except urllib.error.URLError as e:
        axi.fail(
            f"cannot reach the Grey Matter tracker at {base} ({e.reason})",
            hint="Local: start the API with `PORT=8080 python api/main.py`; "
                 "VPS: `docker compose up -d --build`, then pass --url https://greymatter.isroot.in",
        )
    return data if isinstance(data, list) else []


def kv_put(base, apps):
    req = urllib.request.Request(
        f"{base}/api/store/{KEY}",
        data=json.dumps(apps).encode("utf-8"),
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status != 200:
                axi.fail(f"the tracker rejected the update (HTTP {r.status})",
                         hint="Check that the Grey Matter API is running at that address")
    except urllib.error.URLError as e:
        axi.fail(f"cannot reach the Grey Matter tracker at {base} ({e.reason})",
                 hint="Start the API, or pass --url to point at a reachable instance")


def file_put(base, name, path):
    """Upload one resume file to /api/files.

    Returns (uploaded_name, warning). Exactly one of the two is set.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return None, f"skipped {path}: {e.strerror}"
    if len(data) > 10 * 1024 * 1024:
        return None, f"skipped {path}: over 10MB, not uploaded"
    req = urllib.request.Request(
        f"{base}/api/files/{urllib.parse.quote(name)}", data=data, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status == 200:
                return name, None
            return None, f"skipped {path}: tracker returned HTTP {r.status}"
    except (urllib.error.URLError, OSError) as e:
        return None, f"skipped {path}: {e}"
    except Exception as e:
        print(f"Warning: could not upload {path} ({e}).")
        return None


def to_epoch_ms(iso):
    try:
        return int(datetime.datetime.fromisoformat(iso).timestamp() * 1000)
    except ValueError:
        return int(datetime.datetime.now().timestamp() * 1000)


def read_text(path):
    """Small text file (JD, strategy, gaps, changelog) or '' if missing."""
    try:
        with open(path or "", encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def friendly_stem(name, role):
    """Download stem like Jayadithya_R_Full-Stack_AI_Engineer (no extension)."""
    def slug(s):
        s = re.sub(r"[^\w-]+", "_", (s or "").strip(), flags=re.UNICODE)
        return re.sub(r"_+", "_", s).strip("_")
    stem = "_".join(p for p in (slug(name), slug(role)) if p)
    return stem[:100] or "resume"


def row_key(company, role):
    """Canonical (company, role) identity — mirrors the tracker UI's own duplicate rule
    (suffix-insensitive: Ltd/Pvt/Limited dropped), so it agrees with job-filter's publish.py."""
    stop = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "corp", "the",
            "hiring", "for", "job", "openings", "urgent", "a", "an", "role", "position"}

    def canon(text):
        return " ".join(w for w in re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split() if w not in stop)

    return canon(company) + "::" + canon(role)


def main():
    ap = axi.AxiParser(description=DESCRIPTION,
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.environ.get("RESUME_DATA_DIR", "resume_data"),
                    help="resume_store.py data dir (default: ./resume_data)")
    ap.add_argument("--url", default=os.environ.get("GREYMATTER_URL", "http://127.0.0.1:8080"),
                    help="Grey Matter base URL (default: $GREYMATTER_URL or http://127.0.0.1:8080)")
    axi.add_version(ap)
    args = ap.parse_args()

    index_path = os.path.join(args.data_dir, "applications", "applications_index.json")
    if not os.path.exists(index_path):
        axi.fail(f"no applications at {index_path}",
                 hint="Run `python3 scripts/resume_store.py app add ...` first")
    try:
        with open(index_path, encoding="utf-8") as f:
            local = json.load(f)
    except json.JSONDecodeError as e:
        axi.fail(f"{index_path} is not valid JSON: {e}",
                 hint=f"Check it with `python3 -m json.tool {index_path}`")
    if not local:
        axi.fail(f"{index_path} is empty - nothing to push",
                 hint="Run `python3 scripts/resume_store.py app add ...` first")

    try:
        with open(os.path.join(args.data_dir, "profile.json"), encoding="utf-8") as f:
            cand = json.load(f).get("contact", {}).get("name", "")
    except (OSError, ValueError):
        cand = ""

    apps = kv_get(args.url)
    by_id = {a.get("id"): a for a in apps}
    # job-filter publishes the same postings into this tracker, so match on canonical
    # (company, role) as well as our own id — matching on id alone would add a second
    # row for a posting that is already there.
    by_key = {row_key(a.get("company", ""), a.get("role", "")): a for a in apps}

    added = updated = 0
    warnings = []
    for rec in local:
        row = by_id.get(rec["id"]) or by_key.get(row_key(rec.get("company", ""), rec.get("role", "")))
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
            "jd": read_text(rec.get("job_description_path")),
            "dl": friendly_stem(cand, rec.get("role", "")),
        }
        for key, path_key in (("strategy", "strategy_path"),
                              ("gaps", "gaps_path"),
                              ("changelog", "changelog_path")):
            text = read_text(rec.get(path_key))
            if text:
                entry[key] = text
        if row:
            # local copy gone (e.g. gitignored data dir) — keep server text
            for key in ("jd", "strategy", "gaps", "changelog"):
                if not entry.get(key) and row.get(key):
                    entry[key] = row[key]
        # Upload the actual resume files so the tracker can view/download them
        files = []
        warnings = []
        for src, suffix in ((rec.get("resume_pdf_path"), ".pdf"),
                            (rec.get("resume_docx_path"), ".docx")):
            if src and os.path.exists(src):
                uploaded, warning = file_put(args.url, rec["id"] + suffix, src)
                if uploaded:
                    files.append(uploaded)
                if warning:
                    warnings.append(warning)
        cover = rec.get("cover_letter_path")
        if cover and os.path.exists(cover):
            ext = os.path.splitext(cover)[1].lower()
            if ext in (".pdf", ".docx"):
                uploaded, warning = file_put(args.url, rec["id"] + "-cover" + ext, cover)
                if uploaded:
                    files.append(uploaded)
                if warning:
                    warnings.append(warning)
        if files:
            entry["files"] = files
        elif row and row.get("files"):
            entry["files"] = row["files"]  # local copy gone, keep server link
        if row:
            # Phone-side edits win. The local index has no link/type/followup and always
            # says status=drafted, so a blind update() wipes links typed on the phone and
            # walks a real status backwards. Only fill blanks; never regress status.
            for key, value in entry.items():
                if key == "notes" and value == "ats-resume-skill":
                    continue  # constant marker, carries no information
                if not value and row.get(key):
                    continue  # local side is empty, server already has something
                if key == "status" and value == "saved" and row.get(key) not in ("", "saved"):
                    continue  # never walk applied/interview/offer/rejected backwards
                row[key] = value
            updated += 1
        else:
            apps.append(entry)
            by_id[rec["id"]] = entry
            by_key[row_key(entry.get("company", ""), entry.get("role", ""))] = entry
            added += 1

    kv_put(args.url, apps)
    out = {
        "url": args.url,
        "added": added,
        "updated": updated,
        "total_on_tracker": len(apps),
    }
    if warnings:
        out["warnings"] = warnings
    axi.emit(out, hints=[
        "Open the tracker at /tracker/ to review the synced rows",
    ])


if __name__ == "__main__":
    main()
