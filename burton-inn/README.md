# The Burton Inn — lease working folder

Deal-specific lease for **The Burton Inn** (24007 Vashon Highway SW, Burton, Vashon Island, WA):
a whole-building, single-tenant **Two-Tier Value-Sharing Lease©** between The Burton Landing LLC
(Landlord) and eBerry LLC (Tenant), with an **Option to Purchase**.

> **Not public.** `netlify.toml` force-redirects `/burton-inn/*` (and `/forms/*`) away from the
> deployed site, so committing these files does not publish them.

## Workbook (current focus)

`workbook.md` → `workbook.pdf` / `workbook.docx` (`python3 tools/build_burton_workbook.py`): the
terms to agree or discuss with the Landlord, one item at a time (proposed · why · discuss ·
Landlord's view · agreed). It is safe to share with the Landlord: it holds Tenant's proposals but
no fallback positions. Once the terms are agreed, they go into `terms-sheet.md` (Section 1/3).

## Prospectus

`prospectus.md` → `prospectus.pdf` (`python3 tools/build_burton_prospectus.py`): "A Five-Year Lease
and a Path to Purchase", v3.0 (November 13, 2026), for the owner. It leads with the five-year path
(appraisal at signing, Years 1–3 to build the record, a value review in spring 2030, Years 4–5 to
close), then the rent, what the owner receives, the capped-share price method, the two purchase
scenarios (inn alone, or with the Yellow House), and the case for a short extension. Revenue detail
and sources are appendices. It has ruled space to write in every section.

## Structure (three sections; only Section 1/3 varies)

- **Section 1/3** — `terms-sheet.md`. Articles 1–9 (Parties · Premises · Term · Rent and Financial
  Obligations · Use · Notices and Payment · Special Provisions · Incorporation and Exhibits ·
  Execution), signatures with e-sign anchors (`/sn1/`…`/ds2/`), and Exhibits **A** Legal
  Description · **B** Site Plan · **C** Unit Allocations (omitted) · **D** Annual Budget (Tier One) ·
  **E** Landlord Work Letter · **F** Guaranty (omitted) · **G** Additional Site Rules (omitted) ·
  **H** Addendum · **I** Option to Purchase · **J** Shared Septic, Alley, and Yellow House.
  **Every deal-specific term lives in this one file.** Draft v0.14, November 13, 2026.
- **Sections 2/3 & 3/3** — `forms/two-tier-v2.1.md` (Standard Lease Terms + Definitions & Glossary
  Terms, Version 2.1, September 19, 2026), transcribed word-for-word from the Courthouse Square
  Two-Tier Lease v2.2 and attached **unchanged**. Do not edit it for this deal. Every departure is
  made in **Exhibit H (Addendum)**, and each item names the Section 2/3 Article it modifies (listed
  in Article 7.01). That way Sections 2/3 and 3/3 stay identical across leases.

## The economics

- **Tier One (operating costs, NNN):** Tenant pays taxes, Landlord's building insurance, and routine
  upkeep at actual cost (about $19,500/yr; Exhibit D), plus all utilities directly. There is no
  management fee and no escrow account.
- **Tier Two (Landlord Investment):** the greater of **$1,650/month** (from Jan 1, 2028; none in
  Lease Year 1) or **10% of Gross Revenue** for the Lease Year. The minimum is paid monthly. The
  percentage is paid quarterly by Apr 30 / Jul 31 / Oct 31 / Jan 31, with a true-up by March 31.
- **Term:** five years, signing through Dec 31, 2031. Lease Years are calendar years, except that
  Lease Year 1 runs from signing through Dec 31, 2027. A short extension (up to two years) is proposed
  only if the purchase has not closed.
- **Option to Purchase (Exhibit I):** price = as-is appraisal at signing, adjusted for inflation at a
  spring-2030 value review, plus half of any excess of rent-based value, capped at 10% ("capped
  share"). Tenant may include the Yellow House parcel. Rate, cap, and appraiser are still blank.

## Build

- `python3 tools/build_burton_lease.py` → `terms-sheet.pdf` (Section 1/3 with its Exhibits) and
  `lease.pdf` (the full package: Section 1/3, then Sections 2/3 & 3/3). The footer version comes
  from the `**Draft v0.14 — …**` line.
- `python3 tools/build_burton_docx.py` → `lease.docx` for redlining. **Redline Section 1/3 only.**

## Open before signing

- Side Agreement date (Article 8.01); King County tax parcel number (Exhibit A); site plan (Exhibit B).
- Exhibit J details: septic split and agreement, alley description, Yellow House operating standards.
- Zoning: Mark Rowe (King County) feedback; the B&B-as-operator-residence path; the sunroom violation.
- Exhibit I blanks: appraiser, conversion rate, cap, inflation measure, last exercise date, closing terms.
- Extension (Article 3.06) and how the Side Agreement refund works under a five-year term.
- Tom's acceptance of the 10% / $1,650 Tier Two terms.
