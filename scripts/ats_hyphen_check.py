#!/usr/bin/env python3
"""
ats_hyphen_check.py

Check that every hyphenated word in a resume's content JSON survives PDF text
extraction intact.

A hyphenated word that lands at a line end gets de-hyphenated by the PDF text
layer: "first-author" can extract as "firstauthor" or as "fix- explanation".
Both read as broken words to an ATS keyword matcher, which is exactly the
failure this script exists to catch.

Usage:
    python3 ats_hyphen_check.py --content resume_content.json --pdf resume.pdf

Exit code 0 when every hyphenated word survives, 1 when one or more are
broken.
"""

import argparse
import json
import re
import subprocess
import sys


def content_words(content):
    parts = [content.get("headline", ""), content.get("summary", "")]
    parts += [s for row in content.get("skills", []) for s in row.get("items", [])]
    parts += [b for p in content.get("projects", []) for b in (p.get("bullets") or [])]
    parts += [b for e in content.get("experience", []) for b in (e.get("bullets") or [])]
    for a in content.get("awards", []) or []:
        parts += [a.get("name", ""), a.get("achievement", "")]
    return " ".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", required=True)
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()

    with open(args.content, encoding="utf-8") as f:
        content = json.load(f)
    out = subprocess.run(["pdftotext", args.pdf, "-"], capture_output=True, text=True).stdout.lower()
    flat = re.sub(r"\s+", " ", out)

    words = sorted(set(w.lower() for w in re.findall(r"[A-Za-z]+-[A-Za-z-]+", content_words(content))))
    broken = []
    for w in words:
        if w in flat:
            continue
        broken.append((w, "joined" if w.replace("-", "") in flat else "lost"))

    for w, kind in broken:
        print(f"  BROKEN: {w:50} ({kind})")
    if broken:
        print(f"\n{len(broken)} hyphenated word(s) do not survive extraction - reword or rewrap.")
        return 1
    print(f"Clean: all {len(words)} hyphenated words survive extraction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
