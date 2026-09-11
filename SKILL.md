---
name: resume-builder
description: Use this skill to CREATE a tailored, ATS-friendly software engineer resume (and optionally a cover letter) as a .docx/.pdf file — not to review, critique, or score an existing one. Trigger on requests like "write my resume for this job", "build me a FAANG-style resume", "tailor my resume to this job description", "make a resume for [Company]'s [Role] posting", "create an ATS-friendly resume", or any request whose deliverable is a new or updated resume file. Also handles keeping a persistent profile of the candidate's full work history so future resumes can be tailored quickly without re-collecting everything from scratch, and logging every resume actually generated (with company, role, job description, and date) so past applications can be tracked and duplicate applications flagged. Do not use this for resume review/feedback/ATS-scoring of an already-written resume — that is a different task.
---

# Resume Builder

Creates tailored, ATS-friendly resumes for software engineering (and
adjacent) roles, end to end: gather/reuse the candidate's background,
tailor it to a specific job description, generate the actual `.docx` and
`.pdf` files, and keep a durable record of both the candidate's full
history and every application produced.

This skill is for **creation**, not critique. If someone hands you a
finished resume and asks "how's this / what's wrong with it / will this
pass ATS", that's a review task — this skill's rules and scripts are
built around producing new content, not scoring existing content.

## Why persistence and tracking matter here

A resume is never really "done" — the same candidate will tailor a dozen
versions across a job search, and doing the intake interview from zero
each time is exactly the kind of repeated, avoidable work an agent should
eliminate. So this skill keeps two things on disk across sessions:

1. A **profile** — the candidate's complete work history, which only ever
   grows (new jobs, new bullets, new projects get merged in, nothing is
   thrown away just because today's resume didn't use it).
2. An **application tracker** — a record of every resume actually
   generated, with the job description, company, role, and date it was
   made, so the candidate (or you, next session) can answer "did I
   already apply here?" or "what did I send this company?"

## Workflow

### 1. Load (or start) the candidate's profile

Check for `resume_data/profile.json` (see `references/data_schemas.md` for
its shape):

```bash
python3 scripts/resume_store.py profile show
```

- **If it exists**: read it. This is most of the intake done already —
  only ask the candidate about anything genuinely missing or stale (a new
  job since last time, a project they haven't mentioned, etc.).
- **If it's empty/missing**: interview the candidate for their full
  background — not just what might fit one resume, but everything: every
  job with every accomplishment they can recall (push for quantified
  outcomes — see `references/resume_writing_rules.md` section 6),
  education, projects, awards, contact info. Write it as a JSON file
  and merge it in:

```bash
python3 scripts/resume_store.py profile update --json new_info.json
```

Do this same `profile update` step any time you learn something new during
a conversation (a job the candidate mentions in passing, a bullet they add
while reviewing a draft) — don't let it live only in that one resume.

### 2. Get the job description for this specific application

Ask for (or fetch, if a URL/file is given) the job posting text, plus the
company name and role title. Before drafting, check whether this exact
company + role has already been done:

```bash
python3 scripts/resume_store.py app check-duplicate --company "Acme Corp" --role "Backend Engineer"
```

If it finds a match, tell the candidate and confirm they still want to
proceed (per `resume_writing_rules.md` section 13, applying repeatedly at
one company can itself hurt a candidacy) — don't silently regenerate.

### 3. Tailor the content

Read `references/resume_writing_rules.md` in full before drafting — it
covers section order, exact heading names, how to write the
headline/summary, how to phrase accomplishment bullets, and — critically —
how to mine the job description for the keywords that actually matter for
ATS ranking. Then build a `resume_content.json` (schema in
`references/data_schemas.md`) by selecting and rewording the best-fitting
subset of `profile.json` for this job description. This is the step where
judgment matters most: which 2-4 bullets per job are the strongest fit,
which projects to surface, how to reorder skills.

Sequencing rule: do NOT draft a single bullet until JD analysis and
strategy are written down (even briefly):
- **JD analysis:** required vs preferred skills, top keywords/concepts,
  seniority signal, team structure if stated, domain language.
- **Strategy:** top 3 strengths to lead with, what to downplay or suppress
  (see `excluded_skills`), `section_order` per seniority table, page target.
- **Content + humanization:** draft bullets (zero-fabrication policy:
  trace every number to the profile or flag Verify), then run the
  humanization checklist in `resume_writing_rules.md` section 6.

Deliver two short artifacts with every resume (chat or markdown file):
- **Gap summary:** honest DEAL-BREAKER / SIGNIFICANT / MINOR gaps the
  resume cannot fix. E.g. "JD requires Kubernetes — zero K8s in profile.
  Highlighted Docker as closest proxy; study K8s before interview." Never
  invent experience to close a gap; suggest cover-letter framing instead.
- **Change log:** every rewritten bullet / keyword injection with reason
  plus confidence (`confirmed` from profile vs `verify this number` vs
  `quantification opportunity`). The candidate owns every number.

### 4. Generate the docx, then the PDF

Read `references/docx_creation.md` for the full procedure and the ATS
formatting rationale, then:

```bash
python3 scripts/build_resume_docx.py --content resume_content.json --out resume.docx --pdf
# --out omitted: defaults to {First}_{Last}_Resume.docx (+ .pdf), e.g.
# Jane_Doe_Resume.pdf — use that friendly name for the actual submission.
# The slug+hash folder under resume_data/applications/ is internal tracking.
# Add --md for a version-control-friendly markdown source next to the docx.
```

Run the deterministic keyword audit before treating the draft as final
(audit, never a fake 0-100 score):

```bash
python3 scripts/keyword_audit.py --content resume_content.json --jd job_description.txt
```

Fix genuine gaps by grounding terms in real experience — never paste
keywords the candidate doesn't have. Then visually verify the rendered
PDF (procedure in `references/docx_creation.md`) before treating it as
final — confirm it's exactly one page and nothing is cut off.

### 5. Record the application

Once the resume is finalized for this specific company/role:

```bash
python3 scripts/resume_store.py app add \
  --company "Acme Corp" --role "Backend Engineer" \
  --jd-file job_description.txt \
  --resume-docx resume.docx --resume-pdf resume.pdf \
  --strategy-file strategy.txt --gaps-file gaps.txt \
  --changelog-file changelog.txt \
  --status drafted
```

This copies the job description and both resume files into a dedicated
folder under `resume_data/applications/<id>/` and adds a row to the
tracker index — see `references/data_schemas.md` for exactly what's
stored. Update the status later as the candidate hears back:

```bash
python3 scripts/resume_store.py app update-status --id <id> --status applied
```

Valid statuses: `drafted`, `applied`, `interviewing`, `offer`, `rejected`,
`withdrawn`.

### 5b. Sync to the Grey Matter web tracker

After `app add` or `update-status`, push the changes to the candidate's
web tracker (phone-visible at greymatter.isroot.in/tracker/):

```bash
python3 scripts/tracker_push.py                          # local API (default http://127.0.0.1:8080)
python3 scripts/tracker_push.py --url https://greymatter.isroot.in   # VPS
```

It merges `applications_index.json` into the web tracker, keyed by
application id — re-running is safe and updates statuses in place
(never duplicates). It also uploads each application's resume PDF/DOCX
(as `<id>.pdf` / `<id>.docx`) so they are viewable on the tracker row
and under Files. Do this as the last step of any application
workflow, after the status is final for this session.

### 6. List past applications, on request

```bash
python3 scripts/resume_store.py app list                       # everything
python3 scripts/resume_store.py app list --company "Acme Corp"  # filtered
```

### 7. Optional: cover letter

If asked for a cover letter too, follow the structure and pitfalls in
`references/resume_writing_rules.md` section 12. Pass `--cover-letter
<path>` to `app add` so it's stored alongside the resume for that
application.

## Where everything lives on disk

```
resume_data/                          <- persists across sessions
├── profile.json                      <- candidate's full history
└── applications/
    ├── applications_index.json       <- one row per resume generated
    └── <company>_<role>_<date>_<id>/
        ├── job_description.txt
        ├── resume.docx
        ├── resume.pdf
        └── cover_letter.docx (if produced)
```

All `resume_store.py` commands accept `--data-dir <path>` if this
shouldn't default to `./resume_data` (e.g. a fixed location per candidate).

## Reference files — read these, don't guess

- `references/resume_writing_rules.md` — the actual content rules: section
  order and headings, how to write every section, keyword optimization,
  cover letter structure. **Read before drafting any content.**
- `references/docx_creation.md` — the docx/PDF generation procedure, why
  each ATS formatting choice exists, and the fix-it order if a resume
  overflows one page. **Read before running `build_resume_docx.py`.**
- `references/data_schemas.md` — exact JSON shapes for `profile.json`,
  `resume_content.json`, and `applications_index.json`.

## Scripts

- `scripts/build_resume_docx.py` — turns a `resume_content.json` into
  `resume.docx` (and `resume.pdf` with `--pdf`, `resume.md` with `--md`).
  Requires `python-docx` and, for PDF conversion, LibreOffice (`soffice`) on PATH.
- `scripts/keyword_audit.py` — stdlib-only pre-submission audit: JD terms
  missing/underrepresented in the resume, stuffing-risk flags, and
  excluded-skill leaks. Reports findings, never a numeric "ATS score".
- `scripts/resume_store.py` — profile persistence (`profile show|update`)
  and application tracking (`app add|list|check-duplicate|update-status`).
- `scripts/tracker_push.py` — syncs recorded applications to the Grey
  Matter web tracker (`/tracker/`); stdlib-only, idempotent, run after
  every `app add` / `update-status` (see section 5b).
  Pure Python + JSON files, no external services required.
