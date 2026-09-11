# Subskill: Building the .docx and converting it to PDF

This covers turning tailored resume content into an actual resume file:
first a `.docx` (so the candidate has an editable master copy), then a
`.pdf` (the format to actually submit, since it preserves layout across
every machine and viewer).

## Why a script instead of hand-writing XML or prose

Resume formatting has a short list of hard ATS-safety rules (see
`resume_writing_rules.md` section 1) that are easy to accidentally violate
one-off — a stray table for alignment, a date pushed into a footer, a
font substitution. `scripts/build_resume_docx.py` bakes all of these in
once, so every resume this skill produces is automatically compliant
instead of being re-derived (and possibly re-broken) each time.

## Step 1: Produce a `resume_content.json`

Build the tailored content dictionary described in `data_schemas.md`
(`resume_content.json` schema) by pulling the best-fitting subset of the
candidate's persistent profile (`profile.json`) for this specific job
description, following the tailoring guidance in `resume_writing_rules.md`.
Write it to a file, e.g. `resume_content.json`.

## Step 2: Generate the docx (and PDF in the same step)

```bash
python3 scripts/build_resume_docx.py --content resume_content.json --out resume.docx --pdf
# --out omitted: defaults to {First}_{Last}_Resume.docx (+ .pdf with --pdf),
# e.g. Jane_Doe_Resume.pdf — the human-friendly filename to submit to
# ATS portals / recruiters. The slug+hash folder under resume_data/ is
# internal tracking only, never the submission filename.
```

This writes `resume.docx` next to it, then converts it to `resume.pdf` via
headless LibreOffice (`soffice`). Requires `python-docx` (pip) and
LibreOffice (`soffice` on PATH) to be available in the environment; if
either is missing, install with:

```bash
pip install python-docx --break-system-packages   # if not already present
# LibreOffice is a system package (apt/brew/etc.) -- install via the
# environment's package manager if `soffice` isn't found
```

If LibreOffice truly isn't available in the target environment, `resume.docx`
is still a complete, valid deliverable on its own — PDF conversion is a
nice-to-have for submission, not a requirement for the docx to be correct.

## Step 3: Verify visually before calling it done

Never skip this — a docx that "should" render fine can still overflow to a
second page or have a page-break slice through content. Render it to an
image and actually look:

```bash
pdftoppm -jpeg -r 100 resume.pdf page
```

Then view `page-1.jpg` (and `page-2.jpg` if it exists — if there's a page
2, that's the signal to trim). Confirm:
- Exactly one page (`pdfinfo resume.pdf | grep Pages` should say `1`)
- No obviously cut-off text at the bottom margin
- The right-aligned dates in Work Experience/Education actually line up
  against the right margin

## Step 4: If it overflows one page

Fix it in this order, stopping as soon as it fits — each step trades away
less than the next:

1. Cut the single weakest bullet point (per "less is more" in
   `resume_writing_rules.md`) rather than shrinking everything.
2. Drop a lower-value optional section (Awards is usually the safest cut).
3. Only as a last resort, reduce `BODY_SIZE` in the script by 0.5pt
   (never below 10pt) or trim margins slightly (never below 0.4").

## Step 5: Hand off to persistence + job tracking

Once `resume.docx`/`resume.pdf` are final for this application, record
them with `resume_store.py app add ...` — see the main SKILL.md's "Job
tracking" section. Do this every time a resume is actually finalized for a
specific company/role, not just experimented with, so the tracker stays a
reliable record of what's actually been sent out.

## Customizing the script's look

`build_resume_docx.py`'s constants at the top (`BODY_FONT`, `BODY_SIZE`,
section heading size, etc.) are the only things that should normally
change. If a candidate wants a different one of the three ATS-safe fonts,
change `BODY_FONT` to `"Arial"` or `"Garamond"` — don't introduce a fourth
font. Resist requests for logos, colored sidebars, icons, or multi-column
layouts even if they'd look nice — they're exactly the kind of thing that
breaks ATS parsing, which is the entire point of this format.
