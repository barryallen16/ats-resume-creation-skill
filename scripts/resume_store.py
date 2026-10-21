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
    python3 resume_store.py                          # dashboard: live state
    python3 resume_store.py profile show [--summary] [--fields a,b] [--json]
    python3 resume_store.py profile update --json FILE

    python3 resume_store.py app add --company "Acme" --role "Backend Engineer" \\
        --jd-file jd.txt --resume-docx resume.docx --resume-pdf resume.pdf \\
        [--cover-letter cover.docx] [--status drafted] [--force]

    python3 resume_store.py app list [--company X] [--role Y] [--status S] \\
        [--limit N] [--fields a,b] [--json]
    python3 resume_store.py app view <id|ref> [--full]
    python3 resume_store.py app check-duplicate --company X --role Y
    python3 resume_store.py app update-status --id ID --status S

Exit codes:
    0  success (including no-ops)
    1  blocked -- the action needs a decision (an exact duplicate exists)
    2  usage error (unknown flag, missing required flag, bad value)
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import axi  # noqa: E402  (needs the sys.path.insert above)

DESCRIPTION = "Persistent candidate profile and job-application tracker"

DEFAULT_DATA_DIR = "resume_data"

EMPTY_PROFILE = {
    "contact": {},
    "headline": "",
    "summary": "",
    "skills": [],       # [{"category": str, "items": [str]}]
    "excluded_skills": [],  # [str] legacy tech kept for history, suppressed in tailoring
    "experience": [],   # [{"company","location","title","start","end","bullets":[str],"agent_notes":str}]
    "education": [],    # [{"degree","school","location","grad_year","gpa","achievements":[str]}]
    "projects": [],     # [{"name","url","description"}]
    "awards": [],       # [{"year","achievement","name"}]
}

VALID_STATUSES = {"drafted", "applied", "interviewing", "offer", "rejected", "withdrawn"}

# Columns `app list` knows about. The default set is deliberately short --
# long values belong in `app view`.
APP_FIELDS = ("ref", "date", "company", "role", "status", "id", "docx", "pdf", "jd")
DEFAULT_LIST_FIELDS = ("ref", "date", "company", "role", "status")
PREVIEW_CHARS = 500

PROFILE_SECTIONS = (
    "contact", "headline", "summary", "skills", "excluded_skills",
    "experience", "education", "projects", "awards",
)


def parse_fields(raw, allowed, label):
    """Split and validate a --fields value. Unknown names fail loud."""
    if not raw:
        return None
    names = [f.strip() for f in raw.split(",") if f.strip()]
    unknown = [f for f in names if f not in allowed]
    if unknown:
        axi.usage_error(
            f"unknown {label}: {', '.join(unknown)}",
            hint=f"valid {label}s: {', '.join(allowed)}",
        )
    return names


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


def read_text(path, limit=None):
    """Text file contents, or '' when missing/unreadable."""
    try:
        with open(path or "", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return ""
    if limit is not None and len(text) > limit:
        return text[:limit]
    return text


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
                elif field == "agent_notes":
                    # Binding scope note: latest non-empty value wins;
                    # missing/empty incoming leaves the stored note untouched.
                    if isinstance(value, str) and value.strip():
                        target[field] = value
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
    if incoming.get("excluded_skills"):
        merged["excluded_skills"] = dedupe_preserve_order(
            merged.get("excluded_skills", []) + incoming["excluded_skills"]
        )
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


def profile_stats(profile):
    jobs = profile.get("experience", []) or []
    return {
        "name": (profile.get("contact") or {}).get("name", ""),
        "jobs": len(jobs),
        "bullets": sum(len(j.get("bullets", []) or []) for j in jobs),
        "skill_categories": len(profile.get("skills", []) or []),
        "skills": sum(len(row.get("items", []) or []) for row in profile.get("skills", []) or []),
        "projects": len(profile.get("projects", []) or []),
    }


def profile_summary(profile):
    """Index view: the shape of the history without every bullet."""
    out = {"stats": profile_stats(profile)}
    contact = profile.get("contact") or {}
    if contact:
        out["contact"] = {k: v for k, v in contact.items() if v}
    if profile.get("headline"):
        out["headline"] = profile["headline"]
    jobs = profile.get("experience", []) or []
    if jobs:
        out["jobs"] = [
            {
                "company": j.get("company", ""),
                "title": j.get("title", ""),
                "start": j.get("start", ""),
                "end": j.get("end", ""),
                "bullets": len(j.get("bullets", []) or []),
            }
            for j in jobs
        ]
    for key in ("education", "projects", "awards"):
        rows = profile.get(key) or []
        if rows:
            out[key] = rows
    return out


def cmd_profile_show(args):
    path = profile_path(args.data_dir)
    profile = load_json(path, None)
    if profile is None:
        print(f"profile: none at {path}")
        axi.print_hints([
            "Run `resume_store.py profile update --json <file>` to record the candidate's history",
        ])
        return
    if args.json:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
        return
    if args.summary:
        axi.emit(profile_summary(profile), hints=[
            "Run `resume_store.py profile show` for every bullet and project",
        ])
        return
    stats = profile_stats(profile)
    if args.fields:
        profile = {k: v for k, v in profile.items() if k in args.fields}
    out = {"stats": stats}
    out.update(profile)
    axi.emit(out, hints=[
        "Run `resume_store.py app list` to see the applications already generated",
    ])


def cmd_profile_update(args):
    ensure_dirs(args.data_dir)
    try:
        with open(args.json, "r", encoding="utf-8") as f:
            incoming = json.load(f)
    except FileNotFoundError:
        axi.fail(f"no such file: {args.json}", hint="Pass a path to a JSON fragment to merge in")
    except json.JSONDecodeError as e:
        axi.fail(f"{args.json} is not valid JSON: {e}", hint="Check the file with `python3 -m json.tool <file>`")
    existing = load_json(profile_path(args.data_dir), EMPTY_PROFILE)
    merged = merge_profile(existing, incoming)
    atomic_write_json(profile_path(args.data_dir), merged)
    axi.emit(
        {
            "profile": profile_path(args.data_dir),
            "stats": profile_stats(merged),
            "added": {
                "jobs": len(merged.get("experience", [])) - len(existing.get("experience", [])),
                "skills": len(merged.get("skills", [])) - len(existing.get("skills", [])),
            },
        },
        hints=[
            "Run `resume_store.py profile show` to review the merged profile",
        ],
    )


# ------------------------------------------------------------ applications

def normalize_tokens(text):
    text = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = set(text.split())
    noise = {"inc", "corp", "corporation", "llc", "ltd", "company", "co", "the", "a", "an", "and", "or"}
    return tokens - noise


def role_similarity(role1, role2):
    t1 = normalize_tokens(role1)
    t2 = normalize_tokens(role2)
    if not t1 or not t2:
        return 0.0
    overlap = len(t1 & t2)
    return overlap / min(len(t1), len(t2))


def same_company(row_company, target_company):
    if row_company.strip().lower() == target_company.strip().lower():
        return True
    row_tokens = normalize_tokens(row_company)
    target_tokens = normalize_tokens(target_company)
    return bool(target_tokens) and target_tokens == row_tokens


def find_exact(index, company, role):
    return [
        row for row in index
        if same_company(row.get("company", ""), company)
        and row.get("role", "").strip().lower() == role.strip().lower()
    ]


def find_near(index, company, role):
    out = []
    for row in index:
        if not same_company(row.get("company", ""), company):
            continue
        if role_similarity(row.get("role", ""), role) >= 0.6:
            out.append(row)
    return out


def app_ref(row):
    """Short handle: the unique hex tail of the application id."""
    return row.get("id", "").rsplit("_", 1)[-1]


def resolve_app(index, ident):
    """Find one application by full id, unique prefix, or short ref."""
    exact = [row for row in index if row.get("id") == ident]
    if exact:
        return exact[0]
    suffix = [row for row in index if row.get("id", "").endswith("_" + ident)]
    if len(suffix) == 1:
        return suffix[0]
    prefix = [row for row in index if row.get("id", "").startswith(ident)]
    if len(prefix) == 1:
        return prefix[0]
    if len(suffix) > 1 or len(prefix) > 1:
        axi.fail(
            f"{ident} matches {len(suffix) or len(prefix)} applications",
            hint="Use the full id, or run `resume_store.py app list` to pick one",
        )
    return None


def app_field(row, name):
    if name == "ref":
        return app_ref(row)
    if name == "date":
        return row.get("date_created", "")
    if name == "docx":
        return row.get("resume_docx_path") or ""
    if name == "pdf":
        return row.get("resume_pdf_path") or ""
    if name == "jd":
        return row.get("job_description_path") or ""
    return row.get(name, "")


def app_rows(index, fields):
    """Rows in newest-first order, one dict per application."""
    ordered = sorted(index, key=lambda r: r.get("date_created", ""), reverse=True)
    return [{f: app_field(r, f) for f in fields} for r in ordered]


def cmd_app_add(args):
    ensure_dirs(args.data_dir)
    apps_dir = os.path.join(args.data_dir, "applications")
    index = load_json(applications_index_path(args.data_dir), [])

    existing = find_exact(index, args.company, args.role)
    if existing and not args.force:
        row = existing[0]
        axi.fail(
            f"an application for {args.company} / {args.role} already exists "
            f"({row['id']}, status {row['status']})",
            hint="Confirm with the candidate first, then re-run with --force",
        )

    sources = {
        "--jd-file": args.jd_file,
        "--resume-docx": args.resume_docx,
        "--resume-pdf": args.resume_pdf,
        "--cover-letter": args.cover_letter,
        "--strategy-file": args.strategy_file,
        "--gaps-file": args.gaps_file,
        "--changelog-file": args.changelog_file,
    }
    for flag, path in sources.items():
        if path and path != "-" and not os.path.exists(path):
            axi.fail(f"{flag}: no such file: {path}", hint=f"Pass a readable path for {flag}")

    today = datetime.date.today().isoformat()
    # Internal tracking ID only (unique per application) -- never the
    # submission filename. Submit {First}_{Last}_Resume.pdf (the default
    # from build_resume_docx.py) to ATS portals / recruiters.
    app_id = f"{slugify(args.company)}_{slugify(args.role)}_{today.replace('-', '')}_{uuid.uuid4().hex[:6]}"
    app_folder = os.path.join(apps_dir, app_id)
    os.makedirs(app_folder, exist_ok=True)

    jd_dest = os.path.join(app_folder, "job_description.txt")
    if args.jd_file == "-":
        with open(jd_dest, "w", encoding="utf-8") as f:
            f.write(sys.stdin.read())
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
    strategy = copy_into(args.strategy_file, "strategy.txt") if args.strategy_file else None
    gaps = copy_into(args.gaps_file, "gaps.txt") if args.gaps_file else None
    changelog = copy_into(args.changelog_file, "changelog.txt") if args.changelog_file else None

    record = {
        "id": app_id,
        "date_created": datetime.datetime.now().isoformat(timespec="seconds"),
        "company": args.company,
        "role": args.role,
        "job_description_path": jd_dest,
        "resume_docx_path": resume_docx,
        "resume_pdf_path": resume_pdf,
        "cover_letter_path": cover_letter,
        "strategy_path": strategy,
        "gaps_path": gaps,
        "changelog_path": changelog,
        "status": args.status,
    }

    index.append(record)
    atomic_write_json(applications_index_path(args.data_dir), index)

    stored = []
    for name in sorted(os.listdir(app_folder)):
        path = os.path.join(app_folder, name)
        if os.path.isfile(path):
            stored.append({"name": name, "bytes": os.path.getsize(path)})

    axi.emit(
        {
            "application": app_id,
            "ref": app_ref(record),
            "company": args.company,
            "role": args.role,
            "status": args.status,
            "folder": app_folder,
            "files": stored,
        },
        hints=[
            f"Run `resume_store.py app update-status --id {app_ref(record)} --status applied` once you apply",
            "Run `python3 scripts/tracker_push.py` to sync the web tracker",
        ],
    )


def cmd_app_list(args):
    index = load_json(applications_index_path(args.data_dir), [])
    matched = []
    for row in index:
        if args.company and args.company.lower() not in row.get("company", "").lower():
            continue
        if args.role and args.role.lower() not in row.get("role", "").lower():
            continue
        if args.status and row.get("status") != args.status:
            continue
        matched.append(row)

    total = len(matched)
    fields = args.fields or list(DEFAULT_LIST_FIELDS)
    rows = app_rows(matched, fields)
    shown = rows[: args.limit]

    if args.json:
        print(json.dumps(shown, indent=2, ensure_ascii=False))
        return

    filters = []
    if args.company:
        filters.append(f"--company {args.company!r}")
    if args.role:
        filters.append(f"--role {args.role!r}")
    if args.status:
        filters.append(f"--status {args.status}")
    filter_hint = (" ".join(filters) + " ") if filters else ""

    if not matched:
        where = f"matching {filter_hint.strip()}" if filters else "recorded yet"
        print(f"apps: 0 applications {where}")
        axi.print_hints([
            f"Run `resume_store.py app add {filter_hint}--company \"...\" --role \"...\" "
            f"--jd-file <file> --resume-docx <file> --resume-pdf <file>` to record one",
            "Run `resume_store.py` for the full dashboard",
        ])
        return

    out = {"count": f"{len(shown)} of {total} total"}
    out["apps"] = shown
    hints = []
    if total > len(shown):
        hints.append(f"Run `resume_store.py app list {filter_hint}` for all {total} applications")
    hints.append("Run `resume_store.py app view <ref>` for the full record of one application")
    axi.emit(out, hints=hints)


def cmd_app_view(args):
    index = load_json(applications_index_path(args.data_dir), [])
    row = resolve_app(index, args.id)
    if row is None:
        axi.fail(
            f"no application with id {args.id}",
            hint=f"Run `resume_store.py app list` to see all {len(index)} applications",
        )

    out = {
        "id": row.get("id", ""),
        "ref": app_ref(row),
        "date_created": row.get("date_created", ""),
        "company": row.get("company", ""),
        "role": row.get("role", ""),
        "status": row.get("status", ""),
        "files": {
            "docx": row.get("resume_docx_path") or "",
            "pdf": row.get("resume_pdf_path") or "",
            "cover_letter": row.get("cover_letter_path") or "",
        },
    }

    texts = {
        "job_description": read_text(row.get("job_description_path")),
        "strategy": read_text(row.get("strategy_path")),
        "gaps": read_text(row.get("gaps_path")),
        "changelog": read_text(row.get("changelog_path")),
    }
    previews = {}
    for name, text in texts.items():
        if not text:
            continue
        flat = " ".join(text.split())
        previews[name] = flat if len(flat) <= PREVIEW_CHARS else flat[:PREVIEW_CHARS] + " ..."
        previews[f"{name}_chars"] = len(text)

    out["preview"] = previews
    hints = [
        f"Run `resume_store.py app update-status --id {app_ref(row)} --status <status>` to update it",
    ]
    if not args.full and any(texts.values()):
        hints.append(f"Run `resume_store.py app view {app_ref(row)} --full` for the complete texts")
    axi.emit(out, hints=hints)

    if args.full:
        print()
        for name, text in texts.items():
            if not text:
                continue
            print(f"=== {name} ({len(text)} chars) ===")
            print(text)
            print()


def cmd_app_check_duplicate(args):
    index = load_json(applications_index_path(args.data_dir), [])
    exact = find_exact(index, args.company, args.role)
    near = [row for row in find_near(index, args.company, args.role) if row not in exact]

    out = {"company": args.company, "role": args.role}
    if near:
        out["near_matches"] = [
            {
                "ref": app_ref(r),
                "role": r.get("role", ""),
                "status": r.get("status", ""),
                "date": r.get("date_created", ""),
            }
            for r in near
        ]
    if exact:
        row = exact[0]
        out["duplicate"] = "exact"
        out["existing"] = row.get("id", "")
        out["ref"] = app_ref(row)
        out["status"] = row.get("status", "")
        out["date_created"] = row.get("date_created", "")
        out["resume_pdf"] = row.get("resume_pdf_path") or ""
        axi.emit(out, hints=[
            "Confirm with the candidate before applying again, then re-run `app add` with --force",
        ])
        sys.exit(1)

    out["duplicate"] = "none"
    axi.emit(out, hints=[
        f"Run `resume_store.py app add --company {args.company!r} --role {args.role!r} "
        f"--jd-file <file> --resume-docx <file> --resume-pdf <file>` to record it",
    ])


def cmd_app_update_status(args):
    index = load_json(applications_index_path(args.data_dir), [])
    row = resolve_app(index, args.id)
    if row is None:
        axi.fail(
            f"no application with id {args.id}",
            hint=f"Run `resume_store.py app list` to see all {len(index)} applications",
        )
    current = row.get("status", "")
    if current == args.status:
        axi.emit(
            {"application": row.get("id", ""), "ref": app_ref(row), "status": current, "changed": False},
            hints=[
                "Run `python3 scripts/tracker_push.py` to sync the web tracker",
            ],
        )
        return
    row["status"] = args.status
    atomic_write_json(applications_index_path(args.data_dir), index)
    axi.emit(
        {
            "application": row.get("id", ""),
            "ref": app_ref(row),
            "status": args.status,
            "previous_status": current,
            "changed": True,
        },
        hints=[
            "Run `python3 scripts/tracker_push.py` to sync the web tracker",
        ],
    )


# ------------------------------------------------------------------ home

def cmd_home(args):
    index = load_json(applications_index_path(args.data_dir), [])
    profile = load_json(profile_path(args.data_dir), None)

    out = {
        "bin": axi.bin_path(),
        "description": "Persistent candidate profile and job-application tracker",
        "data_dir": args.data_dir,
    }
    if profile:
        out["profile"] = profile_stats(profile)
    else:
        out["profile"] = {"status": "empty", "path": profile_path(args.data_dir)}

    by_status = {}
    for row in index:
        by_status[row.get("status", "unknown")] = by_status.get(row.get("status", "unknown"), 0) + 1
    out["applications"] = {"total": len(index), "by_status": by_status}

    recent = app_rows(index, DEFAULT_LIST_FIELDS)[:10]
    out["count"] = f"{len(recent)} of {len(index)} total"
    out["apps"] = recent

    hints = []
    if not profile:
        hints.append("Run `resume_store.py profile update --json <file>` to record the candidate's history")
    else:
        hints.append("Run `resume_store.py profile show` for the full candidate history")
    if len(index) > len(recent):
        hints.append(f"Run `resume_store.py app list` for all {len(index)} applications")
    hints.append("Run `resume_store.py app list` to filter by company, role, or status")
    axi.emit(out, hints=hints)


# --------------------------------------------------------------------- cli

class AxiParser(axi.AxiParser):
    """Kept as a local alias so the parser reads the same everywhere."""


def main():
    base_parser = AxiParser(add_help=False)
    base_parser.add_argument("--data-dir", default=argparse.SUPPRESS,
                              help="Base directory for persistent data (default: ./resume_data)")
    axi.add_version(base_parser)

    parser = AxiParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter,
                        parents=[base_parser])
    sub = parser.add_subparsers(dest="entity")

    profile_p = sub.add_parser("profile", parents=[base_parser])
    profile_sub = profile_p.add_subparsers(dest="action")

    show_p = profile_sub.add_parser("show", parents=[base_parser])
    show_p.add_argument("--summary", action="store_true",
                         help="Index view: job list and counts instead of every bullet")
    show_p.add_argument("--fields", help="Comma-separated top-level sections to include "
                                         "(contact,headline,summary,skills,excluded_skills,"
                                         "experience,education,projects,awards)")
    show_p.add_argument("--json", action="store_true", help="Print raw JSON instead of TOON")

    up = profile_sub.add_parser("update", parents=[base_parser])
    up.add_argument("--json", required=True, help="Path to a JSON fragment to merge into the profile")

    app_p = sub.add_parser("app", parents=[base_parser])
    app_sub = app_p.add_subparsers(dest="action")

    add_p = app_sub.add_parser("add", parents=[base_parser])
    add_p.add_argument("--company", required=True)
    add_p.add_argument("--role", required=True)
    add_p.add_argument("--jd-file", required=True, help="Path to the job description text, or '-' for stdin")
    add_p.add_argument("--resume-docx", required=True)
    add_p.add_argument("--resume-pdf")
    add_p.add_argument("--cover-letter")
    add_p.add_argument("--strategy-file", help="JD strategy note (text) - shown on the tracker row")
    add_p.add_argument("--gaps-file", help="Gap summary (text) - shown on the tracker row")
    add_p.add_argument("--changelog-file", help="Change log (text) - shown on the tracker row")
    add_p.add_argument("--status", default="drafted", choices=sorted(VALID_STATUSES))
    add_p.add_argument("--force", action="store_true",
                       help="Record even when the same company + role already exists")

    list_p = app_sub.add_parser("list", parents=[base_parser])
    list_p.add_argument("--company", help="Only applications whose company contains this text")
    list_p.add_argument("--role", help="Only applications whose role contains this text")
    list_p.add_argument("--status", choices=sorted(VALID_STATUSES), help="Only applications in this status")
    list_p.add_argument("--limit", type=int, default=100, help="Max rows to show (default: 100)")
    list_p.add_argument("--fields", help="Comma-separated columns: " + ",".join(APP_FIELDS))
    list_p.add_argument("--json", action="store_true", help="Print raw JSON instead of TOON")

    view_p = app_sub.add_parser("view", parents=[base_parser])
    view_p.add_argument("id", help="Application id, unique prefix, or short ref")
    view_p.add_argument("--full", action="store_true", help="Print the complete stored texts")

    dup_p = app_sub.add_parser("check-duplicate", parents=[base_parser])
    dup_p.add_argument("--company", required=True)
    dup_p.add_argument("--role", required=True)

    status_p = app_sub.add_parser("update-status", parents=[base_parser])
    status_p.add_argument("--id", required=True, help="Application id, unique prefix, or short ref")
    status_p.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))

    args = parser.parse_args()
    args.data_dir = (
        getattr(args, "data_dir", None)
        or os.environ.get("RESUME_DATA_DIR")
        or DEFAULT_DATA_DIR
    )
    if getattr(args, "fields", None):
        allowed = PROFILE_SECTIONS if args.entity == "profile" else APP_FIELDS
        args.fields = parse_fields(args.fields, allowed, "field")

    if getattr(args, "entity", None) is None:
        cmd_home(args)
        return

    if args.entity == "profile":
        ensure_dirs(args.data_dir)
        if args.action is None:
            axi.usage_error("profile needs an action", hint="valid actions: show, update")
        if args.action == "show":
            cmd_profile_show(args)
        else:
            cmd_profile_update(args)
    elif args.entity == "app":
        ensure_dirs(args.data_dir)
        if args.action is None:
            axi.usage_error("app needs an action", hint="valid actions: add, list, view, check-duplicate, update-status")
        if args.action == "add":
            cmd_app_add(args)
        elif args.action == "list":
            cmd_app_list(args)
        elif args.action == "view":
            cmd_app_view(args)
        elif args.action == "check-duplicate":
            cmd_app_check_duplicate(args)
        else:
            cmd_app_update_status(args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Happens harmlessly when output is piped into e.g. `head`
        sys.stderr.close()
        sys.exit(0)
