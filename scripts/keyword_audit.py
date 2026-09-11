#!/usr/bin/env python3
"""
keyword_audit.py

Deterministic pre-submission audit: compares a tailored resume against the
target job description and reports findings as text. Stdlib-only, no network,
no ML models, no numeric "ATS score" (counts are a signal, semantic fit and
honesty matter more).

Checks:
  1. JD terms missing or underrepresented in the resume (single tokens and
     a small set of known multi-word / abbreviated forms).
  2. Stuffing risk: terms repeated excessively in the resume.
  3. Excluded-skill leaks: profile `excluded_skills` appearing in the resume.
  4. Light content checks: contact present, 2-4 bullets per job/project,
     projects use bullets, section_order valid.

Usage:
    python3 scripts/keyword_audit.py --content resume_content.json --jd job_description.txt
    python3 scripts/keyword_audit.py --content resume_content.json --jd job_description.txt --profile resume_data/profile.json

Exit code is always 0 (findings are advisory). Never paste keywords the
candidate doesn't have just to clear the missing list — record those as
gaps instead (see SKILL.md).
"""

import argparse
import collections
import json
import re
import sys

STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "has", "had", "this", "that", "from", "into", "about", "across", "between",
    "per", "all", "any", "can", "may", "should", "must", "need", "needs",
    "plus", "including", "include", "such", "more", "most", "other", "than",
    "then", "them", "they", "their", "there", "these", "those", "through",
    "under", "over", "both", "each", "few", "who", "whom", "what", "when",
    "where", "which", "while", "within", "without", "using", "used", "use",
    "work", "working", "team", "teams", "role", "roles", "job", "join",
    "help", "helps", "including", "preferred", "required", "requirements",
    "responsibilities", "qualifications", "experience", "years", "year",
    "ability", "strong", "excellent", "good", "great", "best", "new",
    "company", "business", "product", "products", "customer", "customers",
    "inc", "corp", "llc", "ltd", "co", "etc", "eg", "ie", "via", "amp",
}

# Abbreviation -> full form pairs to check together (ATS safety: spell out once).
ABBREV_PAIRS = [
    ("aws", "amazon web services"),
    ("gcp", "google cloud platform"),
    ("k8s", "kubernetes"),
    ("ci", "continuous integration"),
    ("cd", "continuous delivery"),
    ("ml", "machine learning"),
    ("nlp", "natural language processing"),
    ("llm", "large language model"),
    ("api", "application programming interface"),
    ("sql", "structured query language"),
]

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.+_#/-][A-Za-z0-9]+)*\+*")


def tokenize(text):
    return TOKEN_RE.findall(text)


def resume_blob(content):
    parts = []
    contact = content.get("contact", {})
    parts.append(contact.get("name", ""))
    parts.append(content.get("headline", ""))
    parts.append(content.get("summary", ""))
    for row in content.get("skills", []):
        parts.append(row.get("category", ""))
        parts.extend(row.get("items", []))
    for job in content.get("experience", []):
        parts.append(job.get("company", ""))
        parts.append(job.get("title", ""))
        parts.extend(job.get("bullets", []))
    for edu in content.get("education", []):
        parts.append(edu.get("degree", ""))
        parts.append(edu.get("school", ""))
        parts.extend(edu.get("achievements", []))
    for proj in content.get("projects", []):
        parts.append(proj.get("name", ""))
        parts.extend(proj.get("bullets", []) or [])
        if proj.get("description"):
            parts.append(proj["description"])
    for award in content.get("awards", []):
        parts.append(award.get("name", ""))
        parts.append(award.get("achievement", ""))
    return "\n".join(p for p in parts if p)


def count_occurrences(blob_lower, term_lower):
    # Word-boundary match; multi-word terms match as substrings with boundaries.
    pat = r"(?<![A-Za-z0-9])" + re.escape(term_lower) + r"(?![A-Za-z0-9])"
    return len(re.findall(pat, blob_lower))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", required=True, help="Path to resume_content.json")
    ap.add_argument("--jd", required=True, help="Path to job_description.txt")
    ap.add_argument("--profile", required=False, default=None,
                    help="Optional profile.json (checks excluded_skills leaks)")
    ap.add_argument("--min-jd-count", type=int, default=2,
                    help="Min JD occurrences for a term to be reported (default: 2)")
    ap.add_argument("--stuff-limit", type=int, default=8,
                    help="Resume occurrences above this flag stuffing risk (default: 8)")
    args = ap.parse_args()

    with open(args.content, "r", encoding="utf-8") as f:
        content = json.load(f)
    with open(args.jd, "r", encoding="utf-8") as f:
        jd_text = f.read()
    blob = resume_blob(content)
    blob_lower = blob.lower()
    jd_lower = jd_text.lower()

    # --- JD term frequencies (single tokens) ---
    freq = collections.Counter()
    for tok in tokenize(jd_text):
        low = tok.lower()
        if len(low) < 2 or low in STOPWORDS:
            continue
        if low.isdigit():
            continue
        freq[low] += 1

    candidates = sorted(
        ((t, c) for t, c in freq.items() if c >= args.min_jd_count),
        key=lambda kv: (-kv[1], kv[0]),
    )[:40]

    missing, underrep = [], []
    for term, jd_count in candidates:
        rc = count_occurrences(blob_lower, term)
        if rc == 0:
            missing.append((term, jd_count))
        elif jd_count >= 3 and rc == 1:
            underrep.append((term, jd_count, rc))

    # --- Abbreviation / full-form check ---
    abbrev_notes = []
    for short, full in ABBREV_PAIRS:
        in_jd = short in freq or full in jd_lower
        if not in_jd:
            continue
        s_hit = count_occurrences(blob_lower, short) > 0
        f_hit = count_occurrences(blob_lower, full) > 0
        if s_hit and not f_hit:
            abbrev_notes.append(f"'{short}' appears without full form '{full}' — spell it out once.")
        elif f_hit and not s_hit:
            abbrev_notes.append(f"'{full}' appears without '{short}' — pairing helps both parsers and skimmers.")

    # --- Stuffing risk ---
    resume_tok_freq = collections.Counter(t.lower() for t in tokenize(blob))
    stuffing = sorted(
        ((t, c) for t, c in resume_tok_freq.items()
         if c > args.stuff_limit and t not in STOPWORDS and len(t) >= 3),
        key=lambda kv: -kv[1],
    )[:10]

    # --- Excluded-skill leaks ---
    leaks = []
    if args.profile:
        try:
            with open(args.profile, "r", encoding="utf-8") as f:
                profile = json.load(f)
            for skill in profile.get("excluded_skills", []):
                if skill and count_occurrences(blob_lower, skill.lower()) > 0:
                    leaks.append(skill)
        except FileNotFoundError:
            print(f"Warning: profile not found at {args.profile}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: profile JSON invalid: {e}", file=sys.stderr)

    # --- Light content checks ---
    checks = []
    contact = content.get("contact", {})
    for field in ("name", "email", "phone"):
        if not contact.get(field):
            checks.append(f"Contact missing '{field}'.")
    for job in content.get("experience", []):
        n = len(job.get("bullets", []) or [])
        label = f"{job.get('company', '?')} / {job.get('title', '?')}"
        if n == 0:
            checks.append(f"Experience '{label}' has no bullets.")
        elif n == 1:
            checks.append(f"Experience '{label}' has only 1 bullet (aim for 2-4).")
        elif n > 4:
            checks.append(f"Experience '{label}' has {n} bullets (trim to 2-4 strongest).")
    for proj in content.get("projects", []):
        if not (proj.get("bullets") or []) and proj.get("description"):
            checks.append(f"Project '{proj.get('name', '?')}' uses legacy description — author explicit bullets.")
        elif not (proj.get("bullets") or []):
            checks.append(f"Project '{proj.get('name', '?')}' has no bullets or description.")
    order = content.get("section_order")
    if order:
        known = {"contact", "headline_summary", "skills", "experience",
                 "education", "projects", "awards"}
        unknown = [s for s in order if s not in known]
        if unknown:
            checks.append(f"Unknown section_order entries: {unknown}.")

    # --- Report ---
    print(f"Keyword audit: {len(candidates)} JD terms checked (min JD count {args.min_jd_count}).")
    print("No numeric ATS score is given — semantic fit and honesty outrank counts.")
    print()
    if missing:
        print("MISSING (in JD, absent in resume — add only if genuinely true, else log as gap):")
        for term, c in missing:
            print(f"  - {term} (JD x{c})")
    else:
        print("MISSING: none at this threshold.")
    print()
    if underrep:
        print("UNDERREPRESENTED (JD emphasizes, resume mentions once):")
        for term, jc, rc in underrep:
            print(f"  - {term} (JD x{jc}, resume x{rc})")
    else:
        print("UNDERREPRESENTED: none.")
    print()
    if abbrev_notes:
        print("ABBREVIATION HYGIENE:")
        for n in abbrev_notes:
            print(f"  - {n}")
        print()
    if stuffing:
        print("STUFFING RISK (repeated heavily — trim or vary):")
        for term, c in stuffing:
            print(f"  - {term} (resume x{c})")
        print()
    if leaks:
        print("EXCLUDED-SKILL LEAKS (in excluded_skills but present in resume):")
        for s in leaks:
            print(f"  - {s}")
        print()
    if checks:
        print("CONTENT CHECKS:")
        for c in checks:
            print(f"  - {c}")
        print()
    if not (missing or underrep or abbrev_notes or stuffing or leaks or checks):
        print("Clean: no findings at current thresholds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
