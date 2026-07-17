#!/usr/bin/env python3
"""
build_resume_docx.py

Turns a structured resume-content JSON file into an ATS-friendly .docx,
and (optionally) converts it straight to PDF.

Usage:
    python3 build_resume_docx.py --content resume_content.json --out resume.docx
    python3 build_resume_docx.py --content resume_content.json --out resume.docx --pdf

See references/data_schemas.md (in the parent skill) for the exact shape
of resume_content.json. See references/docx_creation.md for *why* each
formatting choice below exists -- it's all in service of ATS parseability
plus a clean single-page read for a human.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_TAB_ALIGNMENT, WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BODY_FONT = "Calibri"          # Arial / Calibri / Garamond are the only ATS-safe choices
BODY_SIZE = Pt(10.5)           # never go below 10pt
NAME_SIZE = Pt(18)
HEADLINE_SIZE = Pt(11.5)
SECTION_HEAD_SIZE = Pt(11.5)
MARGIN = Inches(0.5)           # narrow margins instead of header/footer regions
USABLE_WIDTH = Inches(8.5 - 1.0)  # Letter width minus the two 0.5" margins


def set_narrow_margins(section):
    section.left_margin = MARGIN
    section.right_margin = MARGIN
    section.top_margin = MARGIN
    section.bottom_margin = MARGIN


def set_default_font(document, name=BODY_FONT, size=BODY_SIZE):
    style = document.styles["Normal"]
    style.font.name = name
    style.font.size = size
    # Force the east-asian font slot too, otherwise some renderers fall back
    rpr = style.element.get_or_add_rPr()
    rFonts = rpr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rpr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), name)


def add_bottom_border(paragraph, size=6, color="808080"):
    """Add a thin horizontal rule under a paragraph -- used for section
    headings instead of a table or a drawn line, so it stays 100% plain
    text underneath (a table row is a common ATS-parsing trap)."""
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def tight(paragraph, before=0, after=4):
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = 1.0


def add_section_heading(document, text):
    p = document.add_paragraph()
    tight(p, before=8, after=2)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = SECTION_HEAD_SIZE
    add_bottom_border(p)
    return p


def add_bullet(document, text, indent=Inches(0.18), hang=Inches(0.18)):
    """A literal bullet character on a plain paragraph, not Word's
    auto-numbering. Some lightweight ATS parsers drop text that lives
    inside a numbering field -- a literal '-' + space is always read as
    plain text, so it's the safer default for a document you can't test
    against every ATS in the world."""
    p = document.add_paragraph()
    tight(p, before=0, after=2)
    pf = p.paragraph_format
    pf.left_indent = indent
    pf.first_line_indent = -hang
    run = p.add_run(f"-  {text}")
    run.font.size = BODY_SIZE
    return p


def add_right_tab_line(document, left_text, right_text, bold_left=True):
    p = document.add_paragraph()
    tight(p, before=6, after=0)
    p.paragraph_format.tab_stops.add_tab_stop(USABLE_WIDTH, WD_TAB_ALIGNMENT.RIGHT)
    r1 = p.add_run(left_text)
    r1.bold = bold_left
    r1.font.size = BODY_SIZE
    r2 = p.add_run(f"\t{right_text}")
    r2.font.size = BODY_SIZE
    return p


def add_contact_line(document, contact):
    parts = []
    if contact.get("location"):
        parts.append(contact["location"])
    if contact.get("phone"):
        parts.append(contact["phone"])
    if contact.get("email"):
        parts.append(contact["email"])
    for key in ("linkedin", "github", "website"):
        if contact.get(key):
            parts.append(contact[key])
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tight(p, before=0, after=8)
    run = p.add_run("  |  ".join(parts))
    run.font.size = Pt(9.5)


def build_header(document, content):
    name_p = document.add_paragraph()
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tight(name_p, before=0, after=0)
    name_run = name_p.add_run(content["contact"]["name"])
    name_run.bold = True
    name_run.font.size = NAME_SIZE

    add_contact_line(document, content["contact"])


def build_summary(document, content):
    # The headline itself IS the section heading here (a slightly more
    # descriptive title than a bare "Professional Summary" label), with
    # the actual summary sentence(s) directly underneath.
    add_section_heading(document, content["headline"])
    p = document.add_paragraph()
    tight(p, before=0, after=6)
    run = p.add_run(content["summary"])
    run.font.size = BODY_SIZE


def build_skills(document, content):
    add_section_heading(document, "Skills")
    for row in content.get("skills", []):
        p = document.add_paragraph()
        tight(p, before=0, after=2)
        label = p.add_run(f"{row['category']}: ")
        label.bold = True
        label.font.size = BODY_SIZE
        items = p.add_run(" | ".join(row["items"]))
        items.font.size = BODY_SIZE


def build_experience(document, content):
    add_section_heading(document, "Work Experience")
    for job in content.get("experience", []):
        left = f"{job['company']}, {job['location']} | {job['title']}"
        right = f"{job['start']} - {job['end']}"
        add_right_tab_line(document, left, right)
        for bullet in job.get("bullets", []):
            add_bullet(document, bullet)


def build_education(document, content):
    add_section_heading(document, "Education")
    for edu in content.get("education", []):
        left = f"{edu['degree']}, {edu['school']}, {edu['location']}"
        right = edu.get("grad_year", "")
        add_right_tab_line(document, left, right)
        details = []
        if edu.get("gpa"):
            details.append(f"GPA: {edu['gpa']}")
        details.extend(edu.get("achievements", []))
        if details:
            p = document.add_paragraph()
            tight(p, before=0, after=4)
            run = p.add_run(" | ".join(details))
            run.font.size = BODY_SIZE


def build_projects(document, content):
    projects = content.get("projects", [])
    if not projects:
        return
    add_section_heading(document, "Projects")
    for proj in projects:
        p = document.add_paragraph()
        tight(p, before=4, after=0)
        name_run = p.add_run(proj["name"])
        name_run.bold = True
        name_run.font.size = BODY_SIZE
        if proj.get("url"):
            url_run = p.add_run(f"  ({proj['url']})")
            url_run.font.size = Pt(9.5)
            url_run.italic = True
        desc_p = document.add_paragraph()
        tight(desc_p, before=0, after=4)
        desc_run = desc_p.add_run(proj["description"])
        desc_run.font.size = BODY_SIZE


def build_awards(document, content):
    awards = content.get("awards", [])
    if not awards:
        return
    add_section_heading(document, "Awards, Accolades and Certifications")
    for award in awards:
        p = document.add_paragraph()
        tight(p, before=0, after=2)
        run = p.add_run(f"{award['year']} | {award['achievement']} | {award['name']}")
        run.font.size = BODY_SIZE


SECTION_BUILDERS = {
    "contact": build_header,
    "headline_summary": build_summary,
    "skills": build_skills,
    "experience": build_experience,
    "education": build_education,
    "projects": build_projects,
    "awards": build_awards,
}

DEFAULT_ORDER = [
    "contact",
    "headline_summary",
    "skills",
    "experience",
    "education",
    "projects",
    "awards",
]


def build_resume(content, out_path):
    document = Document()
    section = document.sections[0]
    set_narrow_margins(section)
    set_default_font(document)

    order = content.get("section_order", DEFAULT_ORDER)
    # contact/header always renders first regardless of requested order
    build_header(document, content)
    for key in order:
        if key in ("contact",):
            continue
        builder = SECTION_BUILDERS.get(key)
        if builder:
            builder(document, content)

    document.save(out_path)
    return out_path


def convert_to_pdf(docx_path, out_dir=None):
    out_dir = out_dir or os.path.dirname(os.path.abspath(docx_path)) or "."
    # Give this conversion its own LibreOffice user profile dir. Headless
    # soffice locks a single shared profile by default, which throws
    # spurious errors when an agent runs conversions back-to-back or in
    # parallel -- a fresh temp profile per call sidesteps that entirely.
    profile_dir = os.path.join(tempfile.gettempdir(), f"lo_profile_{uuid.uuid4().hex}")
    env = os.environ.copy()
    cmd = [
        "soffice",
        "--headless",
        "--norestore",
        f"-env:UserInstallation=file://{profile_dir}",
        "--convert-to",
        "pdf",
        "--outdir",
        out_dir,
        docx_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"soffice conversion failed (code {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    pdf_path = os.path.join(
        out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf"
    )
    if not os.path.exists(pdf_path):
        raise RuntimeError(f"Expected PDF not found at {pdf_path} after conversion")
    return pdf_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", required=True, help="Path to resume_content.json")
    parser.add_argument("--out", required=True, help="Output .docx path")
    parser.add_argument("--pdf", action="store_true", help="Also convert to PDF")
    args = parser.parse_args()

    with open(args.content, "r", encoding="utf-8") as f:
        content = json.load(f)

    docx_path = build_resume(content, args.out)
    print(f"Wrote {docx_path}")

    if args.pdf:
        pdf_path = convert_to_pdf(docx_path)
        print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
