# Golden Set — Extraction and Eligibility Reference Examples

Real pages, fetched and saved on August 26, 2026. Saved now rather than at Stage 2 specifically because Example 1's deadline is days away from changing, at which point the hand-written answer below would stop matching the live page.

---

## Part 1 — Extraction examples (Stage 2)

### Example 1 — genuinely open, clean case

**Source:** https://www.ciiwaste2worth.com/4R-excellence-categories.php

**Saved page content (trimmed of navigation menus, substantive content preserved verbatim):**

> ## CATEGORIES FOR 4R AWARDS (APPLICATION OPEN FOR CII 4R AWARDS 2026. THE LAST DATE IS August 31st 2026)
>
> ### Important Instructions
>
> STEP 1: REGISTRATION FOR CII 4R AWARDS — Applicant needs to first Register to apply for the below mentioned categories of CII 4R Awards.
>
> STEP 2: SUBMISSION OF APPLICATION FORM(S) — Registered applicant can now select the application form from below mentioned categories, sub-categories (if any) and proceed to fill it online. In case of Excellence in Innovative Solutions for waste management (Academic & Research Institutes / Labs) the applicant can download the application and send the dully filled in applications at chair.4Rawards@cii.in. Applicant can apply for multiple categories using the same User Account.
>
> STEP 3: PARTICIPATION FEE — The payment towards participation fees (depending upon scale - large, MSMEs and Start-ups) has to be made within the last date of entry.
>
> Categories: Excellence in Managing MSW by private firms · Excellence in Innovative Solutions by Start-ups for Sustainable Waste management · Excellence in Best Practices in Managing Plastics & Packaging Waste or E-Waste (under EPR) · Excellence in Zero/minimum Waste Generating Products · Excellence in 4R by Industry (Manage Own Waste) · Excellence in Innovative Solutions for waste management (Academic & Research Institutes/Labs)
>
> Participation fee: Large Enterprises (Above 500 Cr turnover) INR 75,000; Large Enterprises (100-500 Cr) INR 60,000; MSME (less than 100 Cr) INR 50,000; Academic Research Labs INR 25,000; Industry Research Labs INR 35,000; Start-ups INR 10,000.
>
> Start-ups incorporated or registered in India with following criteria: (1) Up to a period of 10 years from the date of incorporation/registration. (2) Annual turnover not exceeding Rs 25 crore in any preceding financial year. (3) Works towards innovation, development or improvement of products/processes/services, or is a scalable business model with high potential for employment generation or wealth creation. (4) Offering innovative solutions for sustainable waste management.

**Correct extraction:**
```
title: "CII 4R Awards 2026"
organizing_body: "CII" (Confederation of Indian Industry)
base_title: "CII 4R Awards"
cycle_year: 2026
category: "award"
eligibility_criteria: [
  "Start-ups incorporated or registered in India, up to 10 years from incorporation/registration",
  "Start-up annual turnover not exceeding Rs 25 crore in any preceding financial year",
  "Applicant must work towards innovation, development, or improvement of products/processes/services in sustainable waste management, or be a scalable business model with high potential for employment/wealth generation",
  "Participation fee scales by category: Large Enterprises INR 60,000-75,000, MSME INR 50,000, Start-ups INR 10,000"
]
submission_deadline: "2026-08-31"
deadline_note: null
deadline_verified: true   # "THE LAST DATE IS August 31st 2026" appears verbatim on the page
event_date: null
source_url: "https://www.ciiwaste2worth.com/4R-excellence-categories.php"
```

**What this example is for:** the baseline case. Clean open call, explicit deadline with year stated, multi-part eligibility criteria that need to be split into separate list items, not left as one paragraph.

---

### Example 2 — looks open, is actually closed

**Source:** https://bwevents.co.in/bwsustainability/bw-sustainable-world-awards-2026/

**Saved page content (trimmed, substantive content preserved verbatim):**

> ## BW Sustainable World Awards 2026
> Celebrating Leadership, Innovation & Impact for a Regenerative Future
>
> The BW Sustainable World Awards 2026, part of the Sustainable World Conclave – Mumbai Chapter, celebrate the changemakers leading India's sustainability transformation. These awards recognise organisations, innovators, and individuals who drive measurable impact in environmental stewardship, social equity, governance transparency, and technology-led sustainability. The 2026 edition expands its scope to include new-age enterprises, startups, and tech innovators.
>
> Who Should Apply? Corporates & Large Enterprises leading in ESG transformation · Startups & MSMEs with sustainability-driven innovations · Tech & AI Companies enabling climate, energy, or social impact.
>
> Award Categories: Organisational Excellence Awards (including Best Circular Economy Initiative, for organizations championing waste minimization, recycling, reuse, and material circularity) · Emerging & New-Age Enterprise Awards · Tech & AI for Sustainability Awards · Individual Impact Awards.
>
> ### Nomination Process
> **Nomination Status: Nominations Are Closed Now.** Thank you for your interest in the BW Sustainable World Awards 2026.
> 1. Online Nomination Form
> 2. Screening & Shortlisting
> 3. Jury Interaction Round
> 4. Final Selection & Recognition
>
> Nomination Fee: INR 8,000 + Taxes. **Nominations are currently closed.**
>
> ### How to Nominate
> **Nomination Status: Nominations Are Closed Now.** The nomination window is currently closed.

**This is primarily a Stage 3 (Discovery Agent) example, not a Stage 2 one.** Discovery is where closed-vs-open should be judged, before `extract()` is ever called on this page at all, per CLAUDE.md's architecture. Correct Discovery behaviour: reads this page, recognizes "Nominations Are Closed Now," and never calls `extract()` on it. That's the primary check, and it's the one that matters most, since a keyword scan for "who should apply" or the category names alone would say yes, this page has every surface feature of an open call.

**Secondary Stage 2 use:** if Discovery gets this wrong and calls `extract()` anyway, `extract()` should still catch it and return `typed_failure: opportunity_closed`, not a valid record. This is the second line of defense, not the primary one, don't over-invest in making extraction catch what Discovery should have already filtered.

**What this example is for:** the hardest realistic case in the whole set. A page can carry every surface feature of an open call, categories, eligibility language, a nomination process description, and still be closed. This is exactly the trap a page-structure or keyword-only check falls into.

---

### Example 3 — deadline already elapsed, international, year inferred from context

**Source:** https://circulareconomy.europa.eu/node/9802 (Navarra Circular Economy Awards 2026)

**Saved page content (trimmed, substantive content preserved verbatim):**

> # Navarra Circular Economy Awards 2026: call for students' projects
> Date: 10 Apr 2026 | Sector: Construction, Buildings and Infrastructure; Energy and waste-to-energy; Plastics, Polymers and Rubber | Scope: EU | Country: Spain
>
> This call aims to identify final cycle projects, Bachelor's Final Projects, Degree Final Projects, Master's Final Projects, doctoral theses or similar, developed by students from universities and vocational training centres across Europe.
>
> Projects must demonstrate innovation in business models, products, services or industrial processes under circular economy criteria, and have real potential to develop new business opportunities. Applications may relate to any field or sector, provided they offer solutions aligned with circularity principles. Extra points will be awarded to projects touching on: Electric and connected mobility, Healthy and sustainable food, Green energy industry, Personalised medicine, Sustainable tourism, Sustainable construction, Plastics industry.
>
> **The deadline for submissions is 19 June.** Selected projects will receive a financial award as well as a technical-economic feasibility study, supporting their potential transition towards market implementation.
>
> The Navarra Circular Economy Awards are promoted by the Regional Development Agency of Navarre with the support of the Industry Association of Navarre and the Government of Navarre.

**Correct extraction:**
```
title: "Navarra Circular Economy Awards 2026"
organizing_body: "Regional Development Agency of Navarre"
base_title: "Navarra Circular Economy Awards"
cycle_year: 2026
category: "award"   # the source presents this as an award competition, even though the prize funds project development
eligibility_criteria: [
  "Open to students from universities and vocational training centres across Europe",
  "Projects must be final-cycle projects, Bachelor's/Degree/Master's final projects, or doctoral theses",
  "Must demonstrate innovation in business models, products, services, or industrial processes under circular economy criteria"
]
submission_deadline: "2026-06-19"
deadline_note: null
deadline_verified: true   # day and month "19 June" appear verbatim near deadline language; year 2026 is inferred from the page title and the "Date: 10 Apr 2026" metadata, not stated adjacent to the day/month — that's a valid inference under the corrected grounding rule, not a hallucination
event_date: null
source_url: "https://circulareconomy.europa.eu/node/9802"
```

Deadline of June 19, 2026 has already passed as of today. Correct pipeline behaviour: not surfaced as a current opportunity, the extracted fields are all accurate, but a past deadline makes it inactionable regardless, a separate concern from whether extraction did its job correctly.

**What this example is for:** three things at once, the first genuinely international source in the set, the case that exercises the corrected `deadline_verified` rule (year inferred from context, not stated next to the day/month), and a page where every field extracts correctly but the opportunity still isn't actionable, for a reason extraction alone can't catch.

---

### Example 4 — title available only through page metadata

**Source:** https://sustainability-awards.me

**Browser title:** Sustainability Innovation Awards 2026

**Target:** Sustainability Innovation Awards 2026

**Saved page content (title deliberately omitted to reproduce image/hero-title pages):**

> Nomination Deadline: 18 August 2026
>
> Sofitel The Palm Dubai
>
> The awards celebrate trailblazers in sustainability, recognizing exceptional corporate initiatives and transformative projects shaping a greener, more resilient future in the Middle East.
>
> The programme is brought to you by BNC Publishing.
>
> Submit your nominations by completing the company or individual details, answering all required questions, and supplying supporting documents as a single PDF.

**Correct extraction:**
```
title: "Sustainability Innovation Awards 2026"
organizing_body: "BNC Publishing"
base_title: "Sustainability Innovation Awards"
cycle_year: 2026
category: "award"
eligibility_criteria: []
submission_deadline: "2026-08-18"
deadline_note: null
deadline_verified: true
event_date: null
source_url: "https://sustainability-awards.me"
```

**What this example is for:** verifies that browser metadata is valid evidence when the rendered hero contains the name but Firecrawl's main-content markdown omits it.

---

### Example 5 — multi-page bundle with event and embedded award

**Source:** https://ic-ce.com/icef2026-ace-awards-enterprise

**Browser title:** ACE Awards | ICEF2026 | Enterprise Awards

**Target:** ACE Awards 2026

**Saved page content (two official pages combined as one evidence bundle):**

> === SOURCE PAGE: https://ic-ce.com/icef-2026 ===
>
> India Circular Economy Forum 2026 is an annual forum bringing together industry, startups, academia and policymakers.
>
> ## Awards
>
> The International Council for Circular Economy presents the 5th Edition of ACE, recognizing excellence in circular economy initiatives across India. ACE is open to organizations of any kind, including companies large, small, medium and micro, charities, social enterprises, NGOs and government departments.
>
> === SOURCE PAGE: https://ic-ce.com/icef2026-ace-awards-enterprise ===
>
> ## Enterprise Awards
>
> These awards are for companies large, small, medium and micro, think tanks, charities, not-for-profits, social enterprises, NGOs, membership and accreditation organizations and government departments.
>
> Applicants should demonstrate commitment to circularity, waste reduction, closed-loop systems, ESG or sustainability reporting, and leadership support.

**Correct extraction:**
```
title: "ACE Awards 2026"
organizing_body: "International Council for Circular Economy"
base_title: "ACE Awards"
cycle_year: 2026
category: "award"
eligibility_criteria: [
  "Open to companies of any size, think tanks, charities, not-for-profits, social enterprises, NGOs, membership or accreditation organizations, and government departments",
  "Applicant must demonstrate a circular-economy approach through commitments or practices such as waste reduction, closed-loop systems, sustainability reporting, or leadership support"
]
submission_deadline: null
deadline_note: null
deadline_verified: false
event_date: null
source_url: "https://ic-ce.com/icef2026-ace-awards-enterprise"
```

**What this example is for:** verifies that research can target an embedded award inside a bundle without turning the parent forum into the award record.

---

## Part 2 — Eligibility criteria sets (Stage 4)

Written by hand against `BusinessProfile.md`, covering all three verdict paths plus the qualitative case, per CLAUDE.md's Stage 4 requirement.

**Set 1 — expect `met`**
> Criterion: "Applicant must have been operating for at least 5 years."
> Expected: met. Recykal was founded in 2016, over 5 years as of any 2026 evaluation, stated plainly in the business profile's Identity section.

**Set 2 — expect `not_met`**
> Criterion: "Applicant must be a registered non-profit organisation or NGO."
> Expected: not_met. The business profile states Recykal is a private company, Rapidue Technologies Pvt. Ltd., a for-profit entity, directly contradicting this criterion.

**Set 3 — expect `not_met`, international**
> Criterion: "Applicant must have operated in Saudi Arabia for at least 3 years."
> Expected: not_met. The business profile's International Operations section states the Aramco Digital partnership began February/March 2025, and explicitly instructs treating extended-local-history criteria as not_met rather than unclear, since the timeline is actually known, just short of the bar.

**Set 4 — expect `unclear`**
> Criterion: "Applicant must hold ISO 14001 environmental management certification."
> Expected: unclear. The business profile states ISO certifications are unknown, not confirmed and not denied. This should never resolve to met or not_met on a guess.

**Set 5 — expect a qualitative note, not a score**
> Criterion: "Applicant demonstrates innovative leadership in advancing circular economy practices."
> Expected: a contextual note, referencing something like the CircularNet-based technology stack, IoT traceability work, or the Kedarnath DRS project, shown as supporting context. Must not appear in `criteria_results`, must not affect `score` or `confidence`. If this comes back with a met/not_met verdict instead of a qualitative note, that's the exact failure mode Stage 4's design is meant to prevent.