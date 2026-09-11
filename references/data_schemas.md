# Data Schemas

Three JSON shapes are used across this skill. `profile.json` and
`applications_index.json` are managed for you by `resume_store.py` — you
mostly need to know their shape so you can read them back and reason about
what's already known. `resume_content.json` is something you construct
fresh for each application to feed into `build_resume_docx.py`.

## `profile.json` — the persistent master record

Lives at `<data-dir>/profile.json`. This is the candidate's *entire*
professional history — every job, every bullet, every project they've ever
mentioned — not just what fits on one page. Keep everything here even if a
given resume only uses a fraction of it; a bullet that isn't relevant to
today's job description might be exactly what's needed for next month's.

```jsonc
{
  "contact": {
    "name": "...", "phone": "...", "location": "...", "email": "...",
    "linkedin": "...", "github": "...", "website": "..."
  },
  "headline": "...",          // most recent/default headline
  "summary": "...",           // most recent/default summary
  "skills": [
    {"category": "Languages", "items": ["Java", "Go", "..."]}
  ],
  "experience": [
    {
      "company": "...", "location": "...", "title": "...",
      "start": "MM/YYYY", "end": "MM/YYYY or Present",
      "bullets": ["...", "..."]   // keep ALL known bullets for this job here,
                                   // even ones a past resume didn't use
    }
  ],
  "education": [
    {"degree": "...", "school": "...", "location": "...",
     "grad_year": "...", "gpa": "...", "achievements": ["..."]}
  ],
  "projects": [
    {"name": "...", "url": "...", "description": "...",
     "bullets": ["...", "..."]}   // bullets REQUIRED for resume_content.json:
                                   // 2-4 achievement bullets, same shape as
                                   // experience bullets (see writing rules §8);
                                   // "description" is legacy input only — the
                                   // docx script auto-splits it into bullets
                                   // as a fallback, but always author bullets
  ],
  "awards": [
    {"year": "...", "achievement": "...", "name": "..."}
  ]
}
```

Update it incrementally with `resume_store.py profile update --json <file>`
— pass only the fields/entries that are new or changed. The merge logic
(see `resume_store.py`'s `merge_profile`) matches existing experience
entries by (company, title, start date), education by (school, degree),
projects by (name), and awards by (name, year); bullets/achievements are
unioned rather than replaced, so re-running an update never loses
previously recorded accomplishments.

## `resume_content.json` — one tailored resume's worth of content

Not persisted long-term as its own file (though it's fine to keep the one
used for a given application inside that application's folder for
reference) — this is the *subset and rewording* of `profile.json` chosen
specifically for one job description, matching what
`build_resume_docx.py` expects:

```jsonc
{
  "contact": { /* same shape as profile.json */ },
  "headline": "...",     // may be re-tailored per role, e.g. emphasizing
                          // "Senior Backend Engineer - Payments" vs
                          // "Senior Backend Engineer - Platform"
  "summary": "...",      // re-tailored to this job description
  "skills": [ /* usually the full list from profile.json, reordered so
                the JD's priority skills come first */ ],
  "experience": [ /* full job list, but each job's "bullets" trimmed down
                     to the 2-4 strongest/most relevant for this JD */ ],
  "education": [ /* usually copied as-is from profile.json */ ],
  "projects": [ /* the 1-2 most relevant projects for this JD; give each
                 2-4 "bullets" shaped like experience bullets */ ],
  "awards": [ /* optional; omit the whole "awards" key or leave it an
                 empty list if nothing is relevant */ ],
  "section_order": [       // optional; defaults to the standard order
    "contact", "headline_summary", "skills", "experience",
    "education", "projects", "awards"
  ]
}
```

Set `"section_order"` to put `"education"` before `"experience"` for
students / recent grads / candidates with under ~3 years of experience
(see `resume_writing_rules.md` section 2).

## `applications_index.json` — the job tracker

Lives at `<data-dir>/applications/applications_index.json`, a flat JSON
array, one entry per resume actually finalized for a specific application
(added via `resume_store.py app add`):

```jsonc
[
  {
    "id": "acme-corp_backend-engineer_20260717_a1b2c3",
    "date_created": "2026-07-17T14:32:05",
    "company": "Acme Corp",
    "role": "Backend Engineer",
    "job_description_path": "<data-dir>/applications/<id>/job_description.txt",
    "resume_docx_path": "<data-dir>/applications/<id>/resume.docx",
    "resume_pdf_path": "<data-dir>/applications/<id>/resume.pdf",
    "cover_letter_path": null,
    "status": "drafted"   // drafted | applied | interviewing | offer | rejected | withdrawn
  }
]
```

Each entry's `<id>` also names a folder under `<data-dir>/applications/`
holding the actual job description text and the generated resume (and
cover letter, if any) exactly as they were at the time of that specific
application — so re-opening an old application later shows exactly what
was sent, even if the candidate's `profile.json` has since grown.
