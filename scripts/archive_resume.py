#!/usr/bin/env python3
"""
archive_resume.py

Copy a generated resume PDF into the candidate's dated application folder:

    <dest-dir>/<DD>-<mmm>/<First_Last>_<Role_Slug>.pdf

The folder is the day of the month plus the 3-letter month ("19-oct"), and the
file name reuses the same download stem the Grey Matter tracker already uses
for that application, so the two never drift apart.

Usage:
    python3 archive_resume.py --pdf path/to/resume.pdf --role "Engineer, Programmer Analyst"
    python3 archive_resume.py --pdf path/to/resume.pdf --role "..." --dest-dir ~/Desktop/resume-applications
    python3 archive_resume.py --pdf path/to/resume.pdf --role "..." --date 2026-10-19

The candidate's name is read from <data-dir>/profile.json; pass --name to
override it.
"""

import argparse
import datetime
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tracker_push import friendly_stem  # same slug rule the tracker downloads use

DEFAULT_DEST_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "resume-applications")
DEFAULT_DATA_DIR = "resume_data"


def candidate_name(data_dir, override):
    if override:
        return override
    try:
        with open(os.path.join(data_dir, "profile.json"), encoding="utf-8") as f:
            return json.load(f).get("contact", {}).get("name", "")
    except (OSError, ValueError):
        return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", required=True, help="Path to the resume PDF to archive")
    parser.add_argument("--role", required=True, help="Role title, exactly as posted")
    parser.add_argument("--dest-dir", default=DEFAULT_DEST_DIR, help="Root applications folder")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Where profile.json lives")
    parser.add_argument("--name", default="", help="Override the candidate name from profile.json")
    parser.add_argument("--date", default="", help="Archive date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        sys.exit(f"PDF not found: {args.pdf}")

    if args.date:
        try:
            when = datetime.datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            sys.exit(f"--date must be YYYY-MM-DD, got: {args.date}")
    else:
        when = datetime.datetime.now()

    folder = f"{when:%d-%b}".lower()
    stem = friendly_stem(candidate_name(args.data_dir, args.name), args.role)
    if not stem:
        stem = "resume"

    target_dir = os.path.join(args.dest_dir, folder)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, f"{stem}.pdf")
    shutil.copyfile(args.pdf, target)

    print(f"Archived: {target}")


if __name__ == "__main__":
    main()
