# resume-builder-skill

An [Agent Skill](https://agentskills.io) that **creates** tailored, ATS-friendly
software engineer resumes — not reviews or scores existing ones. Point it at a
candidate's background and a job posting, and it:

- tailors resume content to that specific job description (section order,
  headline/summary, keyword optimization, quantified bullets)
- generates a real `.docx` and converts it to `.pdf`
- keeps a **persistent profile** of the candidate's full work history that
  grows across sessions instead of being re-collected every time
- **tracks every resume generated** (company, role, job description, date,
  status) and flags duplicate applications to the same company + role

Built for [OpenClaw](https://docs.openclaw.ai) and any other agent runtime
that supports the `SKILL.md` format, but the scripts are plain Python and
work standalone too.

## Contents

```
resume-builder/
├── SKILL.md                          # workflow + triggers
├── references/
│   ├── resume_writing_rules.md       # content rules: sections, headline/summary,
│   │                                  #   keyword optimization, cover letters
│   ├── docx_creation.md              # docx → PDF subskill + ATS formatting rationale
│   └── data_schemas.md               # JSON shapes for profile/content/tracker
└── scripts/
    ├── build_resume_docx.py          # generates ATS-safe .docx, converts to PDF
    ├── keyword_audit.py              # pre-submission JD keyword audit (no scores)
    └── resume_store.py               # profile persistence + job-application tracking CLI
```

## Requirements

- Python 3.8+
- [`python-docx`](https://python-docx.readthedocs.io/)
- [LibreOffice](https://www.libreoffice.org/) (`soffice` on `PATH`) — optional,
  only needed for the `.docx` → `.pdf` conversion step. Without it you still
  get a complete, valid `.docx`.

## Quickstart

```bash
# 1. Clone (or download) this repo
git clone https://github.com/barryallen16/ats-resume-creation-skill.git
cd ats-resume-creation-skill

# 2. Install the Python dependency
pip install python-docx --break-system-packages   # drop the flag if not needed on your system

# 3. (optional) Install LibreOffice for PDF conversion
sudo apt-get install libreoffice      # Debian/Ubuntu
brew install libreoffice              # macOS

# 4. Install the skill into your agent
#    OpenClaw:
openclaw skills install . --as resume-builder
#    add --global to make it available to every agent on the machine instead
#    of just the current workspace:
openclaw skills install . --as resume-builder --global

#    Claude Code / Claude.ai / other AgentSkills-compatible runtimes:
#    copy (or symlink) this folder into that tool's skills directory, e.g.
cp -r . ~/.claude/skills/resume-builder

#    Hermes Agent (Nous Research):
#    copy (or symlink) this folder into Hermes skills directory:
cp -r . ~/.hermes/skills/resume-builder
#    (or configure in your Hermes workspace skills folder)

# 5. Start a new agent session (skills are snapshotted at session start,
#    so an already-open session won't see it) and try:
#    "build me a resume for a Backend Engineer role at Acme Corp"
```

## How it works

1. **Load or start the candidate's profile** — a persistent JSON file
   (`resume_data/profile.json`) holding every job, bullet, project, and award
   the candidate has ever mentioned. New info merges in without erasing
   anything already recorded.
2. **Get the job description** for the specific application, and check
   whether that company + role has already been applied to.
3. **Tailor the content** — pick the best-fitting subset of the profile for
   this job, following the rules in `references/resume_writing_rules.md`
   (ATS-safe formatting, section order, keyword optimization, quantified
   accomplishment bullets).
4. **Generate the file**:
   ```bash
   python3 scripts/build_resume_docx.py --content resume_content.json --out resume.docx --pdf
   ```
5. **Record the application**:
   ```bash
   python3 scripts/resume_store.py app add \
     --company "Acme Corp" --role "Backend Engineer" \
     --jd-file job_description.txt \
     --resume-docx resume.docx --resume-pdf resume.pdf \
     --status drafted
   ```

See `SKILL.md` for the full step-by-step workflow an agent follows, and
`references/data_schemas.md` for the exact JSON shapes used throughout.

## Data persistence layout

Everything persists under `resume_data/` (configurable via `--data-dir` on
either script), and is safe to `.gitignore` — it's per-candidate runtime data,
not part of the skill itself:

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
`resume_data/` directory it creates. Review `scripts/build_resume_docx.py`
and `scripts/resume_store.py` before installing if you'd like to confirm
that yourself.
