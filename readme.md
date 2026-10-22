# resume-builder-skill

An [Agent Skill](https://agentskills.io) that **creates** tailored, ATS-friendly
software engineer resumes - not reviews or scores existing ones. Point it at a
candidate's background and a job posting, and it:

- tailors resume content to that specific job description (section order,
  headline/summary, keyword optimization, quantified bullets)
- generates a real `.docx` and converts it to `.pdf`
- deterministically validates the strict 1-page layout with **zero vision tokens**
- keeps a **persistent profile** of the candidate's full work history that
  grows across sessions instead of being re-collected every time
- **tracks every resume generated** (company, role, job description, date,
  status) and flags duplicate applications to the same company + role

Built for [OpenClaw](https://docs.openclaw.ai), Claude Code, Hermes Agent, and any
agent runtime that supports the `SKILL.md` format. The scripts are plain Python and
work standalone too.

## Contents

```
resume-builder/
├── SKILL.md                          # fast 2-step agent workflow + self-contained writing rules
├── references/
│   ├── resume_writing_rules.md       # content rules: sections, headline/summary,
│   │                                  #   keyword optimization, cover letters
│   ├── docx_creation.md              # docx → PDF subskill + ATS formatting rationale
│   └── data_schemas.md               # JSON shapes for profile/content/tracker
└── scripts/
    ├── pipeline.py                   # unified CLI: check, compile, layout check, audit, record, archive
    ├── axi.py                        # shared output layer: TOON encoder + exit codes
    ├── build_resume_docx.py          # generates ATS-safe .docx, converts to PDF
    ├── keyword_audit.py              # pre-submission JD keyword audit (no scores)
    ├── resume_store.py               # profile persistence + job-application tracking CLI
    ├── archive_resume.py             # dated Desktop archive copy
    ├── ats_hyphen_check.py           # checks PDF text extraction hyphen survival
    └── tracker_push.py               # syncs applications to the Grey Matter web tracker
```

## Requirements

- Python 3.8+
- [`python-docx`](https://python-docx.readthedocs.io/) - `uv sync` installs it
- [LibreOffice](https://www.libreoffice.org/) (`soffice` on `PATH`) - optional,
  only needed for the `.docx` -> `.pdf` conversion step. Without it you still
  get a complete, valid `.docx`.

Every other script is stdlib-only.

## Quickstart

```bash
# 1. Clone (or download) this repo
git clone https://github.com/barryallen16/ats-resume-creation-skill.git
cd ats-resume-creation-skill

# 2. Install the Python dependency
uv sync                                  # or: pip install python-docx

# 3. (optional) Install LibreOffice for PDF conversion
sudo apt-get install libreoffice      # Debian/Ubuntu
brew install libreoffice              # macOS

# 4. Install the skill into your agent
#    OpenClaw:
openclaw skills install . --as resume-builder --global

#    Claude Code / Claude.ai:
cp -r . ~/.claude/skills/resume-builder

#    Hermes Agent:
cp -r . ~/.hermes/skills/resume-builder

# 5. Start a new agent session and try:
#    "build me a resume for a Backend Engineer role at Acme Corp"
```

## How it works (Fast 2-Step Agent Pipeline)

The skill uses a fast, 2-turn execution pipeline that eliminates multi-turn tool loops
and multimodal vision inspection:

1. **Pre-draft check & load profile**:
   ```bash
   python3 scripts/pipeline.py check --company "Acme Corp" --role "Backend Engineer"
   ```
   Checks for duplicate past applications and loads the candidate's persistent history (`resume_data/profile.json`).

2. **Tailor content and execute unified pipeline**:
   The agent drafts `resume_content.json` following the inline writing rules in `SKILL.md`,
   then runs the entire compilation, layout check, audit, recording, and archive in **one single command**:
   ```bash
   python3 scripts/pipeline.py run --content resume_content.json --jd job_description.txt \
     --company "Acme Corp" --role "Backend Engineer"
   ```

   `pipeline.py run` automatically:
   - Compiles `.docx` and `.pdf` via headless LibreOffice.
   - **Verifies page count** (target 1 page) deterministically with **zero vision tokens** (exits code 1 if trimmed bullets are needed).
   - Audits JD keyword coverage and flags excluded-skill leaks.
   - Verifies hyphen survival on the PDF text layer.
   - Records the application under `resume_data/applications/<id>/`.
   - Copies the PDF to `~/Desktop/resume-applications/<DD>-<mmm>/`.
   - Syncs with the Grey Matter web tracker (if reachable).

See `SKILL.md` for the complete writing standards, banned verbs, engineering bullet formula, and JSON schemas.

## Output format for agents

Every script prints [TOON](https://toonformat.dev/), a compact
tab-separated encoding of JSON. On this skill's own output that is 25% to
65% fewer tokens than the equivalent pretty-printed JSON, and the result
still reads as a table.

```
$ python3 scripts/resume_store.py app list
count: 3 of 3 total
apps[3]{ref,date,company,role,status}:
  b52714,"2026-10-21T17:20:21",Acme Corp,Backend Engineer,drafted
  ...
help[1]:
  Run `resume_store.py app view <ref>` for the full record of one application
```

The scripts follow one exit-code contract:

| Code | Meaning |
|---|---|
| 0 | success, including no-ops |
| 1 | blocked - the action needs a decision |
| 2 | usage error - unknown flag, missing flag, bad value |

Errors print on stdout as `error: <what went wrong>` plus
`help: <the command that fixes it>`.

## Development & Testing

```bash
uv sync                                  # installs python-docx + ruff
uv run ruff check scripts/               # lint
uv run python scripts/test_axi.py        # TOON encoder unit tests
uv run python scripts/test_resume_store.py   # profile + tracker CLI tests
uv run python scripts/test_cli.py        # audit, docx builder, tracker push tests
uv run python scripts/test_pipeline.py   # unified pipeline unit tests
```

## Data persistence layout

Everything persists under `resume_data/` (configurable via `--data-dir` on
either script, or the `RESUME_DATA_DIR` environment variable), and is safe
to `.gitignore` - it's per-candidate runtime data, not part of the skill
itself:

```
resume_data/
├── profile.json                      # candidate's full history
└── applications/
    ├── applications_index.json       # one row per resume generated
    └── <company>_<role>_<date>_<id>/
        ├── job_description.txt
        ├── resume.docx
        ├── resume.pdf
        └── cover_letter.docx (if produced)
```

## Security note

This skill executes Python on your behalf and only ever writes inside the
`resume_data/` directory and desktop archive. Review `scripts/` before installing
if you'd like to confirm that yourself.
