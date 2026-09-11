# Resume Writing Rules

Read this before drafting any resume content. These rules exist because most
resumes are read by an Applicant Tracking System (ATS) before any human sees
them — the ATS parses your document into fields and often auto-rejects or
badly mis-ranks anything it can't parse cleanly. Everything here optimizes
for "survives the ATS parse" first, "wins the 30-second human skim" second.

## 1. Formatting rules (handled by the docx script, but know why)

- **Author in Word/Google Docs, submit PDF.** ATS parsers are tuned on
  Word/Docs output — Photoshop, design tools, and online builders produce
  layouts that parse badly or not at all. Always confirm the PDF's text is
  highlightable/selectable; if it isn't, the ATS can't read it either.
- **Page budget: 1 page for <8 years, 2 pages permitted for 8+ years/Staff+.**
  For students, early career, and mid-level candidates (<8 years), a strict
  single page remains mandatory. For Staff+, Principal, Architects, or
  candidates with 8+ years of deep experience, 2 pages is accepted and
  often expected to demonstrate architectural scope and leadership. However,
  if a second page is used, it must fill at least 60% of the page—never let an
  awkward 2-3 line spillover happen. If tailored content overflows by just a few
  lines, cut the weakest bullet rather than spilling over.
- **Standard fonts only**: Arial, Calibri, or Garamond. Anything else risks
  the ATS mangling characters during parsing.
- **10pt minimum** body text. Smaller is a common way candidates try to
  cram in more content — resist it.
- **No header/footer regions.** Content that lives in a Word header or
  footer is invisible to a lot of ATS parsers. Keep everything in the
  document body and use narrow margins (0.5") to reclaim the space instead.
- **No tables, text boxes, columns, or graphics for structural layout.**
  These are the single biggest cause of an ATS silently dropping whole
  sections. `build_resume_docx.py` already avoids all of these — don't
  add them when customizing its output.
- **No symbols or special characters in section headings.**

## 2. Section order

Use this order and these exact heading names — ATS parsers are tuned to
recognize standard headings, and deviating (e.g. "My Journey" instead of
"Work Experience") can make a whole section fail to parse:

1. **Name + contact info** at the top.
2. **Headline used as the "summary" heading** — instead of a generic
   "Professional Summary" label, put the candidate's own headline there
   (see section 3) with the actual summary sentence(s) underneath.
3. **Skills**
4. **Work Experience**
5. **Education** — move this ABOVE Work Experience only when the
   candidate is a current student, a very recent graduate, or has under
   ~3 years of experience. Otherwise experience goes first.
6. **Projects**
7. **Awards, Accolades and Certifications** (optional — only include if
   there's something genuinely relevant to show)

Set `section_order` from the JD's seniority signal (don't draft content
before deciding this — see sequencing rule in SKILL.md):

| JD signal | Section order (after contact + headline/summary) |
|---|---|
| New Grad / Intern / <3 years | Skills, Education, Projects, Work Experience, Awards |
| Mid-level / default | Skills, Work Experience, Education, Projects, Awards |
| Senior / Staff / Principal / 8+ years | Skills, Work Experience, Projects (architecture-heavy first), Education, Awards |

When the company is unfamiliar, one optional line of domain-language
mapping (company KPIs → candidate vocabulary, e.g. ARR, ROAS) is enough —
never invent experience to match it.

## 3. Writing the headline + summary

The headline replaces the boring "Professional Summary" label with
something that does real work: a compressed, role-first description of the
candidate. Aim for under 10 words. It should read like a slightly richer
version of a LinkedIn headline. Good pattern: start with the job-role noun
itself ("Senior Backend Engineer", "Front End Engineer"), then a phrase that
signals depth or specialty. Examples (each under 10 words):
- "Senior Backend Engineer, 6 years scaling payments on Rails/Postgres"
- "Front End Engineer, 4 years making high-traffic sites fast"

The summary underneath is a maximum of ~50 words and must, in whatever
order makes sense:
- Make the case for why this candidate is a fit for *this* role
- Use active voice and action verbs, not passive descriptions
- Avoid restating the headline — add new information

Write the summary LAST, after the rest of the resume content is drafted —
it should distill what's already true elsewhere on the page, not invent
new claims.

## 4. Contact information

Must include: full name, personal (never work) phone number, city/state,
personal (never work) email, LinkedIn URL.
Nice to include if relevant and strong: GitHub, personal site, competitive
programming profile, Stack Overflow — but only if there's something worth
showing (e.g. a notable rating, a real number of stars/badges). Don't pad
the line with a low-signal profile just to fill space.

Separate items with "|" on a single line. Never use a company email or
phone number here.

## 5. Skills section

Group by category (e.g. Languages, Frameworks, Databases, Cloud/Infra) and
list items after a colon, separated by "|":

```
Languages: Java | Go | Python | SQL
```

Only include a language/technology fluency claim ("10,000+ lines of Java")
if it's genuinely impressive and verifiable — an empty boast here is easy
for an interviewer to puncture in the first five minutes.

Respect `excluded_skills` from the profile (see `data_schemas.md`): legacy
tech kept for history (e.g. jQuery, SVN, PHP 5) must be suppressed during
tailoring for modern JDs unless the posting explicitly asks for it.

## 6. Work experience

Each job needs a header line with this information, in this order:
company, location, title, and dates (MM/YYYY format, "Present" if current).
The docx script renders this as `Company, Location | Title  |  MM/YYYY - MM/YYYY`
(right-aligned dates): the `|` before the dates is a parsing fallback so the
title and date never merge into one token if an ATS strips tab characters.

Every bullet under a job must follow the **2026 Grounded Engineering Formula**:

> **[Active Technical Verb]** + **[System Context & Challenge]** + **[Architecture / Tool Choice]** + **[Verifiable Outcome / Scale]**

### Zero Fabrication Policy (hard constraint)

Never invent numbers, tools, scope, or ownership to make a bullet stronger.
Every metric must trace to `profile.json` or to an explicit user
confirmation in this session. If a bullet lacks a metric, do NOT polish a
fake one — flag it as a **Quantification Opportunity** or **Verify this
number** in the change log (see SKILL.md) and keep the weaker-but-true
wording on the resume.

When the candidate can't recall exact numbers, ask with these safe
templates (user must confirm before use):
- **Minimum bound:** "Processed 500+ records daily"
- **Range:** "Saved 10-20 hours weekly"
- **Share of activity:** "Managed ~40% of the team's active accounts"

Treat per-job/project `agent_notes` in the profile as binding scope
limits (e.g. "frontend only — coworker did backend"). Never expand
ownership beyond what the notes allow.

### Anti-"AI Slop" Guidelines (Critical for 2026):
Recruiters and hiring managers in 2026 are inundated with generic AI-generated
resumes using hollow metrics. Stand out by adhering to strict technical grounding:

- **Banned generic AI filler verbs**: Do NOT use *"Leveraged"*, *"Spearheaded"*,
  *"Orchestrated"*, *"Championed"*, *"Pioneered"*, or *"Utilized"*. Also avoid
  robotic corporate speak: *"delve"*, *"tapestry"*, *"multifaceted"*,
  *"game-changer"*, *"cutting-edge"* (unless quoting the JD).
- **Required engineering action verbs**: Use precise verbs that signal actual
  technical work: *"Architected"*, *"Profiled"*, *"Refactored"*, *"Migrated"*,
  *"Benchmarked"*, *"Decomposed"*, *"Hardened"*, *"Provisioned"*, *"Automated"*.
- **Anchor with real engineering scale**: Prosaic claims ("boosted performance")
  get rejected. Always anchor with concrete units:
  - Throughput & latency: QPS, concurrent connections, P99/P95 latency in ms.
  - Financial/Cost: AWS/GCP cloud spend reduced by $X/month, GPU hours cut.
  - Data scale: Database volume (GB/TB), daily active records processed.
  - Reliability: Error rate dropped from X% to Y%, uptime SLA achieved.
- **Explain the "Why" / Architecture**: State *why* an architectural choice was
  made (e.g. "decoupled billing via Kafka to eliminate synchronous database locks").

### Humanization checklist (run after drafting, before rendering)

Print/confirm each item — this is the mandatory de-AI pass:
- [ ] No banned verbs or robotic phrases above, in any section.
- [ ] No two adjacent bullets open with the same verb or structure.
- [ ] Sentence lengths vary; no three bullets in a row with identical rhythm.
- [ ] Every bullet passes the "So what?" test (why did this matter to the team/user?).
- [ ] Every number is explainable by the candidate in 30 seconds (baseline,
  method, timeframe/denominator present or flagged as Verify).

List jobs in reverse chronological order (most recent first).

## 7. Education

Include: degree name, graduation year (or expected year), school name,
location. Include GPA only if it's above roughly 3.5/4.0 (or the equivalent
on a different scale) — a mediocre GPA is better left off entirely. Add
real achievements: Dean's List, relevant leadership roles, honors societies.

Move this section above Work Experience for students, recent grads, or
anyone with under ~3 years of professional experience.

## 8. Projects

Include at least one or two projects with genuine substance — ideally
linked to a public repo or live site the reader can actually click through
to. State the candidate's specific contribution and, where possible, a
concrete measure of impact or adoption (stars, downloads, users, orgs using
it) rather than just describing what the project is.

Give each project 2-4 achievement bullets shaped exactly like Work
Experience bullets (section 6 formula: verb + context + architecture/tool
choice + outcome/scale) — never a prose paragraph. One bullet should
cover what was built and the candidate's specific contribution; one
should carry the quantified outcome (perf, scale, adoption). The docx
script renders any legacy `description`-only project as bullets as a
fallback, but always author explicit `bullets` in `resume_content.json`.

## 9. Awards, Accolades and Certifications (optional)

Only include entries that are relevant to the job and, ideally,
quantifiable:

```
[Year] | [What made it notable, quantified] | [Name of the award/competition]
```

Skip this section entirely rather than padding it with low-relevance
entries.

## 10. Keyword optimization & semantic intent (2026 AI screening)

Modern ATS platforms (Ashby AI, Eightfold, Greenhouse AI, Workday) now deploy
vector embeddings and LLM screening agents that assess *semantic context and
competency proximity*, rather than just counting string frequencies:

- **Contextual co-occurrence**: Do NOT merely list a cluster of 30 disconnected
  keywords. The AI screener gives the highest weight to terms that co-occur
  with concrete problem-solving in Work Experience bullets.
- **Extract core tech stack + concepts**: Read the target job description to
  identify both explicit tools (e.g. "PostgreSQL", "Kafka", "Go") and high-level
  system concepts (e.g. "distributed consensus", "zero-downtime migrations",
  "multi-tenant data isolation").
- **Surface modern 2026 competencies**: Where present in the candidate's master
  profile, actively highlight competencies prized in the 2026 market:
  - **Cloud Cost & FinOps**: Cloud infrastructure optimization, AWS/GCP spend
    reduction, container rightsizing.
  - **AI & Data Systems**: Vector search (e.g. pgvector, Pinecone), model
    inference latency optimization, agentic workflows, embeddings, data pipelines.
  - **Modern Reliability**: OpenTelemetry, SLO/SLA management, automated canary
    deployments.
- **Spell out abbreviations once**: Maintain ATS safety by spelling out key
  acronyms at least once (e.g. "Amazon Web Services (AWS)", "Google Cloud Platform (GCP)").
- **Never keyword-stuff**: If a human recruiter detects keyword stuffing during
  the 15-second skim, or if the LLM screener detects ungrounded buzzword lists,
  the resume is down-ranked.

## 11. Less is more & page budget control

Prioritizing a candidate's single strongest 2–4 accomplishments per job
over a long list of average ones produces a stronger resume every time:

- **Strict 1-page budget for <8 years of experience**: Early and mid-career
  resumes must fit on one page. Cut the weakest bullet before shrinking fonts.
- **2-page budget for 8+ years / Staff+ / Engineering Leadership**: For
  candidates with 8+ years of deep architecture or management history, a
  2-page resume is acceptable and often preferred to show scope. When targeting
  2 pages, page 2 must fill at least 60% of the page—never leave an awkward
  2-line overflow.
- When given a large master history from `profile.json`, the agent's job is
  curation: selecting the highest-impact 2–4 bullets per role tailored to
  this specific job description.

## 12. Cover letter (optional companion output)

If asked to also draft a cover letter, treat it as a complement to the
resume, not a restatement of it:

- **Opening**: get straight to why this candidate fits this specific role.
- **Middle**: pick one real, specific thread from their background and
  develop it briefly — a cover letter that could be sent to any company
  for any role is a wasted one. Research the company enough to make a
  genuine, specific connection to its mission or work, not a generic
  compliment.
- **Length**: under one page, always.
- Avoid restating bullets already on the resume nearly verbatim — use the
  cover letter to add context (motivation, a story, a connection) the
  resume format can't hold.

## 13. A few things to flag to the candidate, not just do silently

- If the company has an online application form that separately collects
  work history, tell the candidate to fill it out completely and
  accurately — some recruiters review the form data directly and may
  never open the attached resume/PDF.
- If the candidate is applying to more than one role at the same company,
  mention it — applying broadly at one employer can read as unfocused.
   `resume_store.py app check-duplicate` can detect this automatically;
   use it before finalizing a new application (see the main SKILL.md).

## 14. Review tools (run before finalizing)

- **Keyword audit (deterministic, no fake scores).** Run the stdlib audit
  before rendering — it reports missing/underrepresented JD terms and
  stuffing risks, never a 0-100 "ATS score":
```bash
python3 scripts/keyword_audit.py --content resume_content.json --jd job_description.txt
```
  Fix genuine gaps by grounding terms in real experience (section 10);
  never paste keywords the candidate doesn't have.
- **Readability scan.** Paste the draft into an ATS scanner (e.g.
  Resume Worded, AI Resume Judge) and fix parse errors before sending.
  Tailor-check against the job description with a targeted-resume tool
  where available.
- **Plain-text test.** Copy the resume content into a plain-text file. If
  bullets go missing, characters show wrong, or sections scramble, fix the
  source — the ATS sees what the text file shows, not what Word renders.
- **Keyword mirror check.** Confirm must-have job-description terms appear
  verbatim at least once (full form, not just the abbreviation) and weight
  frequency by their importance in the posting — without stuffing past
  natural reading.
- **Change log + gap summary.** Deliver both with every resume (formats in
  SKILL.md): what changed and why (with Verify flags), plus honest
  DEAL-BREAKER / SIGNIFICANT / MINOR gaps the resume cannot fix.
