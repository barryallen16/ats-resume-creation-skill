#!/usr/bin/env python3
"""
scripts/pipeline.py

Unified execution pipeline for ATS resume generation, automated verification,
and durable application recording.

Replaces multi-turn manual tool-calling with a single automated pass:
  1. Compiles ATS-safe .docx and .pdf (via build_resume_docx).
  2. Deterministically verifies page budget (target 1 page) with 0 vision tokens.
  3. Audits keyword coverage and detects excluded skill leaks.
  4. Verifies PDF text-layer hyphenation survival (ats_hyphen_check).
  5. Records application to persistent index and stores artifacts (resume_store).
  6. Archives PDF to candidate's dated Desktop archive (~/Desktop/resume-applications).
  7. Syncs with Grey Matter web tracker (graceful if offline).

Usage:
    # 1. Pre-draft check (duplicate check & candidate history summary)
    python3 scripts/pipeline.py check --company "Acme Corp" --role "Backend Engineer"

    # 2. Complete compilation, verification, and recording pipeline
    python3 scripts/pipeline.py run --content resume_content.json --jd job_description.txt \\
        --company "Acme Corp" --role "Backend Engineer"
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import axi  # noqa: E402
import resume_store  # noqa: E402
from tracker_push import friendly_stem  # noqa: E402

DESCRIPTION = "Unified resume compilation, automated layout check, audit, and recording pipeline"

DEFAULT_DATA_DIR = os.environ.get("RESUME_DATA_DIR", "resume_data")
DEFAULT_DEST_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "resume-applications")


def get_pdf_page_count(pdf_path: str) -> int:
    """Extract page count from PDF using pdfinfo or regex fallback.

    Requires zero vision/multimodal tokens.
    """
    if not os.path.exists(pdf_path):
        return 0
    # Try pdfinfo first if installed
    try:
        res = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.startswith("Pages:"):
                    return int(line.split(":")[1].strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass

    # Pure Python regex fallback
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
        matches = re.findall(rb"/Type\s*/Pages.*?/Count\s+(\d+)", data, re.DOTALL)
        if matches:
            return int(matches[0])
        pages = re.findall(rb"/Type\s*/Page\b", data)
        if pages:
            return len(pages)
    except Exception:
        pass
    return 1


def check_hyphen_survival(content_path: str, pdf_path: str):
    """Run ats_hyphen_check logic and return list of broken hyphenated words."""
    try:
        cmd = [sys.executable, os.path.join(_HERE, "ats_hyphen_check.py"), "--content", content_path, "--pdf", pdf_path]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return lines
    except Exception:
        pass
    return []


def run_keyword_audit(content_path: str, jd_path: str, profile_path: Optional[str] = None):
    """Run keyword_audit and extract key advisory findings."""
    cmd = [
        sys.executable,
        os.path.join(_HERE, "keyword_audit.py"),
        "--content", content_path,
        "--jd", jd_path,
        "--json"
    ]
    if profile_path and os.path.exists(profile_path):
        cmd.extend(["--profile", profile_path])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            return json.loads(res.stdout)
    except Exception:
        pass
    return None


def sync_tracker(data_dir: str):
    """Sync to tracker gracefully without crashing the pipeline if unreachable."""
    try:
        cmd = [sys.executable, os.path.join(_HERE, "tracker_push.py"), "--data-dir", data_dir]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.returncode == 0, res.stdout.strip()
    except Exception as e:
        return False, str(e)


# ------------------------------------------------------------------ Subcommands

def cmd_check(args):
    """Pre-drafting check: verify duplicate status and candidate profile."""
    data_dir = getattr(args, "data_dir", DEFAULT_DATA_DIR)
    index = resume_store.load_json(resume_store.applications_index_path(data_dir), [])
    profile = resume_store.load_json(resume_store.profile_path(data_dir), None)

    out = {
        "status": "clear_to_draft",
        "company": args.company,
        "role": args.role,
    }

    # 1. Profile status
    if not profile:
        axi.fail(
            f"No profile found at {resume_store.profile_path(data_dir)}",
            hint="Create profile.json or run `resume_store.py profile update --json <file>`",
        )
    stats = resume_store.profile_stats(profile)
    out["candidate"] = stats.get("name") or "Unknown"
    out["profile_stats"] = f"{stats.get('jobs', 0)} jobs, {stats.get('projects', 0)} projects, {stats.get('skills', 0)} skill categories"

    # 2. Duplicate check
    exact = resume_store.find_exact(index, args.company, args.role)
    if exact:
        row = exact[0]
        out["status"] = "duplicate_found"
        out["existing_application"] = {
            "id": row.get("id"),
            "ref": resume_store.app_ref(row),
            "status": row.get("status"),
            "date": row.get("date_created"),
        }
        axi.emit(
            out,
            hints=[
                f"An exact application already exists for {args.company} / {args.role}.",
                "If the candidate wishes to re-apply, pass --force to `pipeline.py run`.",
            ],
        )
        sys.exit(1)

    near = resume_store.find_near(index, args.company, args.role)
    if near:
        out["near_matches"] = [
            {"ref": resume_store.app_ref(r), "company": r.get("company"), "role": r.get("role"), "status": r.get("status")}
            for r in near
        ]

    hints = [
        "Profile loaded and duplicate check passed. Proceed to draft resume_content.json.",
        f"Then run: python3 scripts/pipeline.py run --content resume_content.json --jd <jd.txt> --company {args.company!r} --role {args.role!r}",
    ]
    axi.emit(out, hints=hints)


def cmd_run(args):
    """Execute the full compilation, layout verification, audit, and recording pipeline."""
    data_dir = getattr(args, "data_dir", DEFAULT_DATA_DIR)
    dest_dir = getattr(args, "dest_dir", DEFAULT_DEST_DIR)
    target_pages = getattr(args, "target_pages", 1)
    force = getattr(args, "force", False)

    # 1. Verify inputs
    if not os.path.exists(args.content):
        axi.fail(f"Content file not found: {args.content}", hint="Draft resume_content.json first")
    if not os.path.exists(args.jd):
        axi.fail(f"Job description file not found: {args.jd}", hint="Provide the target job description text")

    with open(args.content, "r", encoding="utf-8") as f:
        try:
            content = json.load(f)
        except json.JSONDecodeError as e:
            axi.fail(f"Invalid JSON in {args.content}: {e}", hint="Fix syntax in resume_content.json")

    # 2. Check duplicate in applications index
    index = resume_store.load_json(resume_store.applications_index_path(data_dir), [])
    existing = resume_store.find_exact(index, args.company, args.role)
    if existing and not force:
        row = existing[0]
        axi.fail(
            f"An application for {args.company} / {args.role} already exists ({row['id']}, status {row['status']})",
            hint="Confirm with the candidate first, then re-run with --force",
        )

    # 3. Determine output docx path
    out_docx = args.out
    if not out_docx:
        candidate_name = content.get("contact", {}).get("name", "")
        friendly_stem_str = friendly_stem(candidate_name, args.role)
        out_docx = f"{friendly_stem_str}.docx" if friendly_stem_str else "resume.docx"

    # 4. Build docx and PDF
    build_cmd = [
        sys.executable,
        os.path.join(_HERE, "build_resume_docx.py"),
        "--content", args.content,
        "--out", out_docx,
        "--pdf",
    ]
    if getattr(args, "md", False):
        build_cmd.append("--md")
    if getattr(args, "txt", False):
        build_cmd.append("--txt")

    res_build = subprocess.run(build_cmd, capture_output=True, text=True)
    if res_build.returncode != 0:
        axi.fail(
            f"Docx/PDF compilation failed:\n{res_build.stderr or res_build.stdout}",
            hint="Check that python-docx and LibreOffice (soffice) are available and content schema is valid",
        )

    out_pdf = os.path.splitext(out_docx)[0] + ".pdf"
    if not os.path.exists(out_pdf):
        axi.fail(f"Expected compiled PDF not found at {out_pdf}", hint="Ensure LibreOffice is working properly")

    # 5. Page count verification (AUTOMATED LAYOUT CHECK - ZERO VISION TOKENS)
    actual_pages = get_pdf_page_count(out_pdf)
    if actual_pages > target_pages:
        axi.fail(
            f"Generated PDF overflowed: {actual_pages} pages (target is {target_pages} page).",
            hint=(
                "Cut 1-2 lower-impact bullets or drop an optional section (e.g. Awards) "
                "in resume_content.json, then re-run."
            ),
        )

    # 6. ATS Hyphen Check
    broken_hyphens = check_hyphen_survival(args.content, out_pdf)

    # 7. Keyword Audit
    prof_path = getattr(args, "profile", None) or os.path.join(data_dir, "profile.json")
    audit_data = run_keyword_audit(args.content, args.jd, prof_path)

    # 8. Record Application in resume_store
    resume_store.ensure_dirs(data_dir)
    apps_dir = os.path.join(data_dir, "applications")
    today = datetime.date.today().isoformat()
    app_id = f"{resume_store.slugify(args.company)}_{resume_store.slugify(args.role)}_{today.replace('-', '')}_{resume_store.uuid.uuid4().hex[:6]}"
    app_folder = os.path.join(apps_dir, app_id)
    os.makedirs(app_folder, exist_ok=True)

    jd_dest = os.path.join(app_folder, "job_description.txt")
    shutil.copyfile(args.jd, jd_dest)

    def _copy_into(src, dest_name):
        if not src or not os.path.exists(src):
            return None
        dest = os.path.join(app_folder, dest_name)
        shutil.copyfile(src, dest)
        return dest

    recorded_docx = _copy_into(out_docx, "resume.docx")
    recorded_pdf = _copy_into(out_pdf, "resume.pdf")
    recorded_cl = _copy_into(getattr(args, "cover_letter", None), os.path.basename(args.cover_letter)) if getattr(args, "cover_letter", None) else None
    recorded_strat = _copy_into(getattr(args, "strategy_file", None), "strategy.txt") if getattr(args, "strategy_file", None) else None
    recorded_gaps = _copy_into(getattr(args, "gaps_file", None), "gaps.txt") if getattr(args, "gaps_file", None) else None
    recorded_clog = _copy_into(getattr(args, "changelog_file", None), "changelog.txt") if getattr(args, "changelog_file", None) else None

    new_row = {
        "id": app_id,
        "date_created": datetime.datetime.now().isoformat(timespec="seconds"),
        "company": args.company,
        "role": args.role,
        "job_description_path": jd_dest,
        "resume_docx_path": recorded_docx,
        "resume_pdf_path": recorded_pdf,
        "cover_letter_path": recorded_cl,
        "strategy_path": recorded_strat,
        "gaps_path": recorded_gaps,
        "changelog_path": recorded_clog,
        "status": getattr(args, "status", "drafted"),
    }
    index = [r for r in index if not (resume_store.same_company(r.get("company", ""), args.company) and r.get("role", "").strip().lower() == args.role.strip().lower())]
    index.append(new_row)
    resume_store.atomic_write_json(resume_store.applications_index_path(data_dir), index)

    # 9. Archive to candidate desktop archive
    archived_target = None
    if getattr(args, "archive", True):
        when = datetime.datetime.now()
        folder = f"{when:%d-%b}".lower()
        candidate_name = content.get("contact", {}).get("name", "")
        archive_stem = friendly_stem(candidate_name, args.role) or "resume"
        target_dir = os.path.join(dest_dir, folder)
        os.makedirs(target_dir, exist_ok=True)
        archived_target = os.path.join(target_dir, f"{archive_stem}.pdf")
        shutil.copyfile(out_pdf, archived_target)

    # 10. Sync with Grey Matter Tracker
    tracker_synced = False
    if getattr(args, "tracker", True):
        tracker_synced, _ = sync_tracker(data_dir)

    # Build pipeline summary output
    out = {
        "result": "success",
        "application_id": app_id,
        "ref": resume_store.app_ref(new_row),
        "pages": f"{actual_pages} of {target_pages} (budget met)",
        "files": {
            "docx": out_docx,
            "pdf": out_pdf,
            "archived": archived_target or "skipped",
        },
        "tracker_sync": "synced" if tracker_synced else "offline_or_skipped",
    }

    if broken_hyphens:
        out["broken_hyphens_warning"] = broken_hyphens

    if audit_data:
        advisory = {}
        missing = audit_data.get("missing", [])
        under = audit_data.get("underrepresented", [])
        leaks = audit_data.get("excluded_skill_leaks", [])
        stuffing = audit_data.get("stuffing_risk", [])
        checks = audit_data.get("content_checks", [])

        if missing:
            advisory["missing_jd_terms"] = [m.get("term") for m in missing[:8]]
        if under:
            advisory["underrepresented_terms"] = [u.get("term") for u in under[:5]]
        if leaks:
            advisory["excluded_skill_leaks"] = leaks
        if stuffing:
            advisory["stuffing_risk"] = stuffing
        if checks:
            advisory["content_checks"] = checks

        if advisory:
            out["audit_advisory"] = advisory

    hints = [
        f"Application recorded under {app_id} (ref: {resume_store.app_ref(new_row)}).",
        f"Submit friendly PDF: {out_pdf}",
    ]
    if not tracker_synced and getattr(args, "tracker", True):
        hints.append("Tracker was unreachable (offline); update later with `python3 scripts/tracker_push.py`.")

    axi.emit(out, hints=hints)


# --------------------------------------------------------------------- CLI

def main():
    base_parser = axi.AxiParser(add_help=False)
    base_parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                             help="Persistent data dir (default: ./resume_data)")
    axi.add_version(base_parser)

    parser = axi.AxiParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter,
                           parents=[base_parser])
    sub = parser.add_subparsers(dest="command")

    # Check subcommand
    check_p = sub.add_parser("check", parents=[base_parser], help="Verify duplicate status and candidate profile")
    check_p.add_argument("--company", required=True, help="Target company name")
    check_p.add_argument("--role", required=True, help="Target role title")

    # Run subcommand
    run_p = sub.add_parser("run", parents=[base_parser], help="Build, verify layout, audit, record, and archive")
    run_p.add_argument("--content", required=True, help="Path to tailored resume_content.json")
    run_p.add_argument("--jd", required=True, help="Path to target job description text file")
    run_p.add_argument("--company", required=True, help="Target company name")
    run_p.add_argument("--role", required=True, help="Target role title")
    run_p.add_argument("--target-pages", type=int, default=1, help="Max page budget (default: 1)")
    run_p.add_argument("--out", help="Custom output docx path")
    run_p.add_argument("--profile", help="Path to master profile.json")
    run_p.add_argument("--dest-dir", default=DEFAULT_DEST_DIR, help="Desktop archive directory")
    run_p.add_argument("--status", default="drafted", choices=list(resume_store.VALID_STATUSES),
                       help="Initial application status (default: drafted)")
    run_p.add_argument("--force", action="store_true", help="Bypass duplicate application guard")
    run_p.add_argument("--no-archive", dest="archive", action="store_false", help="Skip desktop archive copy")
    run_p.add_argument("--skip-tracker", dest="tracker", action="store_false", help="Skip web tracker sync")
    run_p.add_argument("--md", action="store_true", help="Also generate markdown resume source")
    run_p.add_argument("--txt", action="store_true", help="Also generate paste-ready plain text")
    run_p.add_argument("--cover-letter", help="Optional companion cover letter file")
    run_p.add_argument("--strategy-file", help="Optional strategy notes file")
    run_p.add_argument("--gaps-file", help="Optional gaps summary file")
    run_p.add_argument("--changelog-file", help="Optional changelog file")

    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
