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
candidate doesn't have just to clear the missing list -- record those as
gaps instead (see SKILL.md).
"""

import argparse
import collections
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import axi  # noqa: E402  (needs the sys.path.insert above)

DESCRIPTION = "Audit a tailored resume against a job description for keyword coverage"

STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "has", "had", "this", "that", "from", "into", "about", "across", "between",
    "per", "all", "any", "can", "may", "should", "must", "need", "needs",
    "plus", "including", "include", "such", "more", "most", "other", "than",
    "then", "them", "they", "their", "there", "these", "those", "through",
    "under", "over", "both", "each", "few", "who", "whom", "what", "when",
    "where", "which", "while", "within", "without", "using", "used", "use",
    "work", "working", "team", "teams", "role", "roles", "job", "join",
    "help", "helps", "preferred", "required", "requirements",
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


def read_json_file(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        axi.fail(f"{label} not found: {path}", hint=f"Pass a readable path for {label}")
    except json.JSONDecodeError as e:
        axi.fail(f"{label} is not valid JSON: {e}", hint=f"Check it with `python3 -m json.tool {path}`")


def read_text_file(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        axi.fail(f"{label} not found: {path}", hint=f"Pass a readable path for {label}")


def main():
    ap = axi.AxiParser(description=DESCRIPTION,
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", required=True, help="Path to resume_content.json")
    ap.add_argument("--jd", required=True, help="Path to job_description.txt")
    ap.add_argument("--profile", required=False, default=None,
                    help="Optional profile.json (checks excluded_skills leaks)")
    ap.add_argument("--min-jd-count", type=int, default=2,
                    help="Min JD occurrences for a term to be reported (default: 2)")
    ap.add_argument("--stuff-limit", type=int, default=8,
                    help="Resume occurrences above this flag stuffing risk (default: 8)")
    ap.add_argument("--max-terms", type=int, default=40,
                    help="Max JD terms to check (default: 40)")
    ap.add_argument("--json", action="store_true", help="Print raw JSON instead of TOON")
    axi.add_version(ap)
    args = ap.parse_args()

    content = read_json_file(args.content, "--content")
    jd_text = read_text_file(args.jd, "--jd")
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
    )[: args.max_terms]

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
        short_in_jd = short in freq
        full_in_jd = full in jd_lower
        if not (short_in_jd or full_in_jd):
            continue
        s_hit = count_occurrences(blob_lower, short) > 0
        f_hit = count_occurrences(blob_lower, full) > 0
        if s_hit and not f_hit:
            abbrev_notes.append(f"'{short}' appears without full form '{full}' - spell it out once.")
        elif f_hit and not s_hit and short_in_jd:
            # Only worth asking for the short form when the job description
            # used it - "k8s" is not a term a resume should gain just because
            # the JD spelled Kubernetes out.
            abbrev_notes.append(
                f"'{full}' appears without '{short}' - the job description used '{short}', so pair them."
            )

    # --- Stuffing risk ---
    resume_tok_freq = collections.Counter(t.lower() for t in tokenize(blob))
    stuffing = sorted(
        ((t, c) for t, c in resume_tok_freq.items()
         if c > args.stuff_limit and t not in STOPWORDS and len(t) >= 3),
        key=lambda kv: -kv[1],
    )[:10]

    # --- Excluded-skill leaks ---
    leaks = []
    warnings = []
    if args.profile:
        try:
            with open(args.profile, "r", encoding="utf-8") as f:
                profile = json.load(f)
            for skill in profile.get("excluded_skills", []):
                if skill and count_occurrences(blob_lower, skill.lower()) > 0:
                    leaks.append(skill)
        except FileNotFoundError:
            warnings.append(f"profile not found at {args.profile} - excluded-skill leaks were not checked")
        except json.JSONDecodeError as e:
            warnings.append(f"profile JSON invalid ({e}) - excluded-skill leaks were not checked")

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
    out = {
        "audit": {
            "jd_terms_checked": len(candidates),
            "min_jd_count": args.min_jd_count,
            "missing": len(missing),
            "underrepresented": len(underrep),
            "abbreviation_notes": len(abbrev_notes),
            "stuffing_risk": len(stuffing),
            "excluded_skill_leaks": len(leaks),
            "content_checks": len(checks),
        },
        "note": "No numeric ATS score is given - semantic fit and honesty outrank counts.",
    }
    if warnings:
        out["warnings"] = warnings
    if missing:
        out["missing"] = [{"term": t, "jd_count": c} for t, c in missing]
    if underrep:
        out["underrepresented"] = [
            {"term": t, "jd_count": jc, "resume_count": rc} for t, jc, rc in underrep
        ]
    if abbrev_notes:
        out["abbreviation_hygiene"] = abbrev_notes
    if stuffing:
        out["stuffing_risk"] = [{"term": t, "resume_count": c} for t, c in stuffing]
    if leaks:
        out["excluded_skill_leaks"] = leaks
    if checks:
        out["content_checks"] = checks
    if not (missing or underrep or abbrev_notes or stuffing or leaks or checks or warnings):
        out["clean"] = True

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    hints = []
    if missing or underrep:
        hints.append("Add a term only when the candidate genuinely has that experience - "
                     "otherwise record it as a gap in the change log")
    if checks:
        hints.append("Fix the content checks in resume_content.json, then re-run this audit")
    hints.append("Run `python3 scripts/build_resume_docx.py --content <file> --pdf` once the content is settled")
    axi.emit(out, hints=hints)
    return 0


if __name__ == "__main__":
    sys.exit(main())
