#!/usr/bin/env python3
"""
resume_store.py

Two jobs, both file-based (no external DB required) so they work in any
agent sandbox with a writable filesystem:

  1. PROFILE  -- a persistent, ever-growing record of the candidate's full
     work history (every job, every bullet, every project) at
     <data-dir>/profile.json. Each new resume tailors a SUBSET of this
     master record for one specific application, but nothing the
     candidate has told the agent about their background is ever
     thrown away. Re-running `profile update` merges new information in
     instead of overwriting it.

  2. APPLICATION TRACKER -- one row per resume actually generated, at
     <data-dir>/applications/applications_index.json, plus a per-application
     folder holding the exact job description, the .docx/.pdf that were
     produced, and (optionally) the cover letter. This is what lets the
     skill answer "what have I already sent to Google?" or warn "you
     already tailored a resume for this same company + role."

Usage:
    python3 resume_store.py profile show [--data-dir DIR]
    python3 resume_store.py profile update --json FILE [--data-dir DIR]

    python3 resume_store.py app add --company "Acme" --role "Backend Engineer" \\
        --jd-file jd.txt --resume-docx resume.docx --resume-pdf resume.pdf \\
        [--cover-letter cover.docx] [--status drafted] [--data-dir DIR]

    python3 resume_store.py app list [--company X] [--role Y] [--status S] [--data-dir DIR]
    python3 resume_store.py app check-duplicate --company X --role Y [--data-dir DIR]
    python3 resume_store.py app update-status --id ID --status S [--data-dir DIR]
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import uuid

DEFAULT_DATA_DIR = "resume_data"

EMPTY_PROFILE = {
    "contact": {},
    "headline": "",
    "summary": "",
    "skills": [],       # [{"category": str, "items": [str]}]
    "experience": [],   # [{"company","location","title","start","end","bullets":[str]}]
    "education": [],    # [{"degree","school","location","grad_year","gpa","achievements":[str]}]
    "projects": [],     # [{"name","url","description"}]
    "awards": [],       # [{"year","achievement","name"}]
}

VALID_STATUSES = {"drafted", "applied", "interviewing", "offer", "rejected", "withdrawn"}


# ---------------------------------------------------------------- helpers

def slugify(text):
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return re.sub(r"-+", "-", text).strip("-")


def atomic_write_json(path, data):
    tmp_path = f"{path}.tmp-{uuid.uuid4().hex}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, "applications"), exist_ok=True)


def profile_path(data_dir):
    return os.path.join(data_dir, "profile.json")


def applications_index_path(data_dir):
    return os.path.join(data_dir, "applications", "applications_index.json")


# ---------------------------------------------------------------- profile

def dedupe_preserve_order(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def merge_skills(existing, incoming):
    by_category = {row["category"]: row for row in existing}
    for row in incoming:
        cat = row["category"]
        if cat in by_category:
            by_category[cat]["items"] = dedupe_preserve_order(
                by_category[cat]["items"] + row["items"]
            )
        else:
            existing.append(row)
            by_category[cat] = row
    return existing


def merge_list_section(existing, incoming, key_fields, list_fields=()):
    """Generic merge for experience/education/projects/awards.

    key_fields identify "the same entry" (e.g. company+title for a job).
    list_fields (e.g. 'bullets') are unioned rather than overwritten so
    a later update can ADD accomplishments to a job without erasing the
    ones already recorded.
    """
    def key_of(entry):
        return tuple(entry.get(k, "") for k in key_fields)

    index = {key_of(e): e for e in existing}
    for new_entry in incoming:
        k = key_of(new_entry)
        if k in index:
            target = index[k]
            for field, value in new_entry.items():
                if field in list_fields:
                    target[field] = dedupe_preserve_order(target.get(field, []) + value)
                else:
                    target[field] = value
        else:
            existing.append(new_entry)
            index[k] = new_entry
    return existing


def merge_profile(existing, incoming):
    merged = json.loads(json.dumps(existing))  # deep copy
    if incoming.get("contact"):
        merged.setdefault("contact", {}).update(incoming["contact"])
    if incoming.get("headline"):
        merged["headline"] = incoming["headline"]
    if incoming.get("summary"):
        merged["summary"] = incoming["summary"]
    if incoming.get("skills"):
        merged["skills"] = merge_skills(merged.get("skills", []), incoming["skills"])
    if incoming.get("experience"):
        merged["experience"] = merge_list_section(
            merged.get("experience", []), incoming["experience"],
            key_fields=("company", "title", "start"), list_fields=("bullets",)
        )
    if incoming.get("education"):
        merged["education"] = merge_list_section(
            merged.get("education", []), incoming["education"],
            key_fields=("school", "degree"), list_fields=("achievements",)
        )
    if incoming.get("projects"):
        merged["projects"] = merge_list_section(
            merged.get("projects", []), incoming["projects"], key_fields=("name",)
        )
    if incoming.get("awards"):
        merged["awards"] = merge_list_section(
            merged.get("awards", []), incoming["awards"], key_fields=("name", "year")
        )
    return merged


def cmd_profile_show(args):
    profile = load_json(profile_path(args.data_dir), EMPTY_PROFILE)
    print(json.dumps(profile, indent=2, ensure_ascii=False))


def cmd_profile_update(args):
    ensure_dirs(args.data_dir)
    with open(args.json, "r", encoding="utf-8") as f:
        incoming = json.load(f)
    existing = load_json(profile_path(args.data_dir), EMPTY_PROFILE)
    merged = merge_profile(existing, incoming)
    atomic_write_json(profile_path(args.data_dir), merged)
    print(f"Profile updated at {profile_path(args.data_dir)}")


# ------------------------------------------------------------ applications

def cmd_app_add(args):
    ensure_dirs(args.data_dir)
    apps_dir = os.path.join(args.data_dir, "applications")

    today = datetime.date.today().isoformat()
    app_id = f"{slugify(args.company)}_{slugify(args.role)}_{today.replace('-', '')}_{uuid.uuid4().hex[:6]}"
    app_folder = os.path.join(apps_dir, app_id)
    os.makedirs(app_folder, exist_ok=True)

    jd_dest = os.path.join(app_folder, "job_description.txt")
    if args.jd_file == "-":
        jd_text = sys.stdin.read()
        with open(jd_dest, "w", encoding="utf-8") as f:
            f.write(jd_text)
    else:
        shutil.copyfile(args.jd_file, jd_dest)

    def copy_into(src, dest_name):
        if not src:
            return None
        dest = os.path.join(app_folder, dest_name)
        shutil.copyfile(src, dest)
        return dest

    resume_docx = copy_into(args.resume_docx, "resume.docx")
    resume_pdf = copy_into(args.resume_pdf, "resume.pdf")
    cover_letter = copy_into(args.cover_letter, os.path.basename(args.cover_letter)) if args.cover_letter else None

    record = {
        "id": app_id,
        "date_created": datetime.datetime.now().isoformat(timespec="seconds"),
        "company": args.company,
        "role": args.role,
        "job_description_path": jd_dest,
        "resume_docx_path": resume_docx,
        "resume_pdf_path": resume_pdf,
        "cover_letter_path": cover_letter,
        "status": args.status,
    }

    index = load_json(applications_index_path(args.data_dir), [])
    index.append(record)
    atomic_write_json(applications_index_path(args.data_dir), index)

    print(f"Application recorded: {app_id}")
    print(json.dumps(record, indent=2, ensure_ascii=False))


def cmd_app_list(args):
    index = load_json(applications_index_path(args.data_dir), [])
    for row in index:
        if args.company and args.company.lower() not in row["company"].lower():
            continue
        if args.role and args.role.lower() not in row["role"].lower():
            continue
        if args.status and row["status"] != args.status:
            continue
        print(f"{row['id']:<45} {row['date_created']:<20} {row['company']:<20} "
              f"{row['role']:<28} {row['status']}")


def cmd_app_check_duplicate(args):
    index = load_json(applications_index_path(args.data_dir), [])
    matches = [
        row for row in index
        if row["company"].strip().lower() == args.company.strip().lower()
        and row["role"].strip().lower() == args.role.strip().lower()
    ]
    if matches:
        print(f"DUPLICATE: {len(matches)} existing application(s) for "
              f"{args.company} / {args.role}:")
        for row in matches:
            print(f"  - {row['id']} (status: {row['status']}, created {row['date_created']})")
        sys.exit(1)
    else:
        print("No existing application found for this company + role.")
        sys.exit(0)


def cmd_app_update_status(args):
    if args.status not in VALID_STATUSES:
        print(f"Warning: '{args.status}' is not one of the usual statuses {sorted(VALID_STATUSES)}, "
              f"saving it anyway.")
    index = load_json(applications_index_path(args.data_dir), [])
    found = False
    for row in index:
        if row["id"] == args.id:
            row["status"] = args.status
            found = True
            break
    if not found:
        print(f"No application found with id {args.id}")
        sys.exit(1)
    atomic_write_json(applications_index_path(args.data_dir), index)
    print(f"Updated {args.id} -> status: {args.status}")


# --------------------------------------------------------------------- cli

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Base directory for persistent data")
    sub = parser.add_subparsers(dest="entity", required=True)

    profile_p = sub.add_parser("profile")
    profile_sub = profile_p.add_subparsers(dest="action", required=True)
    profile_sub.add_parser("show")
    up = profile_sub.add_parser("update")
    up.add_argument("--json", required=True, help="Path to a JSON fragment to merge into the profile")

    app_p = sub.add_parser("app")
    app_sub = app_p.add_subparsers(dest="action", required=True)

    add_p = app_sub.add_parser("add")
    add_p.add_argument("--company", required=True)
    add_p.add_argument("--role", required=True)
    add_p.add_argument("--jd-file", required=True, help="Path to the job description text, or '-' for stdin")
    add_p.add_argument("--resume-docx", required=True)
    add_p.add_argument("--resume-pdf")
    add_p.add_argument("--cover-letter")
    add_p.add_argument("--status", default="drafted", choices=sorted(VALID_STATUSES))

    list_p = app_sub.add_parser("list")
    list_p.add_argument("--company")
    list_p.add_argument("--role")
    list_p.add_argument("--status", choices=sorted(VALID_STATUSES))

    dup_p = app_sub.add_parser("check-duplicate")
    dup_p.add_argument("--company", required=True)
    dup_p.add_argument("--role", required=True)

    status_p = app_sub.add_parser("update-status")
    status_p.add_argument("--id", required=True)
    status_p.add_argument("--status", required=True)

    args = parser.parse_args()

    if args.entity == "profile":
        ensure_dirs(args.data_dir)
        {"show": cmd_profile_show, "update": cmd_profile_update}[args.action](args)
    elif args.entity == "app":
        ensure_dirs(args.data_dir)
        {
            "add": cmd_app_add,
            "list": cmd_app_list,
            "check-duplicate": cmd_app_check_duplicate,
            "update-status": cmd_app_update_status,
        }[args.action](args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Happens harmlessly when output is piped into e.g. `head`
        sys.stderr.close()
        sys.exit(0)
