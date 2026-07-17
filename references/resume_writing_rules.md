# Resume Writing Rules

Read this before drafting any resume content. These rules exist because most
resumes are read by an Applicant Tracking System (ATS) before any human sees
them — the ATS parses your document into fields and often auto-rejects or
badly mis-ranks anything it can't parse cleanly. Everything here optimizes
for "survives the ATS parse" first, "wins the 30-second human skim" second.

## 1. Formatting rules (handled by the docx script, but know why)

- **One page.** A second page rarely gets read. If tailored content doesn't
  fit, cut the weakest bullet before shrinking fonts or margins.
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

## 3. Writing the headline + summary

The headline replaces the boring "Professional Summary" label with
something that does real work: a compressed, role-first description of the
candidate. Aim for under 10 words. It should read like a slightly richer
version of a LinkedIn headline. Good pattern: start with the job-role noun
itself ("Senior Backend Engineer", "Front End Engineer"), then a phrase that
signals depth or specialty.

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

## 6. Work experience

Each job needs a header line with this information, in this order:
company, location, title, and dates (MM/YYYY format, "Present" if current).

Every bullet under a job should follow this shape:

> [What you did], resulting in [a quantified outcome]

A bullet with a number in it (latency reduced X%, cost cut by $Y, N users
served, team of Z people led) is dramatically stronger than the same bullet
without one. When drafting content from a candidate's raw description of
their work, actively probe for the number — "how much faster", "how many
users", "how big was the team" — rather than writing a vague accomplishment.

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

## 9. Awards, Accolades and Certifications (optional)

Only include entries that are relevant to the job and, ideally,
quantifiable:

```
[Year] | [What made it notable, quantified] | [Name of the award/competition]
```

Skip this section entirely rather than padding it with low-relevance
entries.

## 10. Keyword optimization

This is the step that most determines whether a resume clears the ATS
ranking, not just the parse:

- Read the target job description and extract the specific must-have and
  nice-to-have skills/technologies/experience it names.
- Work those same terms into Skills, and naturally into Work Experience
  and Projects bullets, using language that closely mirrors the job
  description's own phrasing rather than a rough synonym.
- Spell out abbreviations at least once (e.g. "Amazon Web Services" rather
  than only "AWS", "Google Cloud Platform" rather than only "GCP") since
  some ATS keyword-match on the full term.
- Weight how much a term shows up by how important it is in the job
  description — a "must-have" listed first deserves more presence than a
  "nice-to-have" buried in a long list.
- Never keyword-stuff to the point that a sentence stops reading naturally
  — a human reads this resume too, eventually.

## 11. Less is more

Prioritizing a candidate's single strongest 2–3 accomplishments per job
over a long list of average ones produces a stronger resume every time.
When given a large raw history of everything someone has done (which is
exactly what the persistent profile is for — see the main SKILL.md), the
job of tailoring a resume is picking the best-fitting subset for *this*
job description, not including everything.

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
