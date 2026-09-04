# The Burton Inn — lease working folder

Deal-specific lease for **The Burton Inn** (Burton, Vashon Island, WA), drafted from the tenant's
**"Rent Basis & Owner Return" prospectus (July 2026)**. It is a whole-building, single-tenant,
triple-net lease with percentage rent.

**It reuses the shared standard form — unchanged — as Parts 2 & 3.** The vetted
**Standard Lease Terms + Definitions & Glossary (Version 1.6, neutral)** live in `lease/lease.md`; the Burton
package attaches that file **verbatim** rather than keeping its own copy, so the boilerplate cannot
drift and never has to be re-reviewed. Everything deal-specific lives in **Part 1** — the Lease
Terms Sheet and its Exhibits, chiefly **Exhibit D**, the *Triple-Net, Percentage Rent & Single-Tenant
Amendment* that modifies and supplements the v1.5 form for this deal. This is exactly the extension
mechanism the v1.5 form is built for: its Article 1.7 ("NNN Variation") reserves Exhibit D for the
NNN amendment, and its Article 2.3 reserves Exhibit C for the Tenant Work Letter — so the Burton
exhibit lettering (A Legal, B Guaranty, C Tenant Work, D Amendment) makes every v1.5 cross-reference
resolve with zero edits to the form.

> **Why:** the goal is that Parts 2 & 3 stay identical across every lease so they're never
> relitigated. Deal changes land in Part 1 only.

> **Not public.** `netlify.toml` force-redirects `/burton-inn/*` away from the deployed site, so
> committing these files does not publish them on courthousesquarevashon.com. (The standard lease
> in `lease/` remains public by design; this one is a confidential draft between two parties.)

## Files

**One** Burton-specific source file (Part 1), plus the shared v1.5 form (Parts 2 & 3):

- `terms-sheet.md` → `terms-sheet.pdf` — **Part 1**: the Lease Terms Sheet in the nine numbered
  Courthouse Square sections (1 Parties · 2 Premises · 3 Term · 4 Financial Obligations · 5 Operations
  & Special Conditions · 6 Additional Terms · 7 Notices · 8 Incorporation & Merger · 9 Index of
  Exhibits), a signature block with DocuSign/Adobe e-sign anchors (`/sn1/`…`/ds2/`), and the four
  Exhibits: **A** Legal Description, **B** Guaranty (none), **C** Tenant Work Letter (the ~$98k
  fit-out), **D** Triple-Net, Percentage Rent & Single-Tenant Amendment (the deal engine — NNN,
  percentage rent, whole-building adaptations, phased opening, capital systems). **Every
  deal-specific term lives in this one file.** Draft v0.9, July 24, 2026.
- `lease/lease.md` (not in this folder) — **Parts 2 & 3**, the v1.5 Standard Lease Terms +
  Definitions & Glossary, attached verbatim. Do **not** copy it here; the build reads it in place.
- `lease.pdf` — the full signable package: Part 1, then the v1.5 form, continuous page numbering.
  Generated only.
- `lease.docx` — the same combined document as an **editable Word file for redlining** (real Word
  heading styles). Generated only. **Redline Part 1 only** — the v1.5 form (Parts 2 & 3) is the
  frozen master and should not be edited here; changing it would defeat the whole point. Round-trip:
  hand out → receive redlined `.docx` → apply accepted Part-1 changes back to `terms-sheet.md`.

Rebuild the PDFs: `python3 tools/build_burton_lease.py` (stamps the Part-1 footer from the
`**Draft v0.9 — …**` line in `terms-sheet.md`; Parts 2 & 3 carry their own "Version 1.6" stamp).
Rebuild the Word file: `python3 tools/build_burton_docx.py`. The standalone v1.5 PDF is
`lease/lease.pdf` (built by `tools/build_lease_docs.py`); the Burton package doesn't duplicate it.

**Order of precedence:** Terms Sheet → Exhibits (Exhibit D controls over the other Exhibits and over
the Standard Lease Terms) → Standard Lease Terms → Definitions. To change a deal term, edit
`terms-sheet.md` only.

## How the prospectus maps into the lease

All deal-specific terms live in Part 1 (Terms Sheet + Exhibit D). Parts 2 & 3 are the unchanged
v1.5 form; "Art." below refers to that form's articles.

| Prospectus term | Where it lives |
|---|---|
| Triple-net at actuals incl. Year 1; tenant carries utilities | Terms Sheet §4 + **Exhibit D §D.3** (supersedes v1.5 Art 1 CAM, per Art 1.7) |
| Fixed base rent $1,650/mo, abated Year 1, flat (% rent is the escalator) | Terms Sheet §4 + **Exhibit D §D.4** |
| Percentage rent: 10% over $198,000 breakpoint; monthly Gross Revenue statements, paid/reconciled quarterly on a **calendar-quarter** basis with a **1-month payment window** (Q1 Jan–Mar due Apr 30; Q2 Apr–Jun due Jul 31; Q3 Jul–Sep due Oct 31; Q4 Oct–Dec due Jan 31), annual certified reconciliation, POS audit (tenant pays audit cost if understatement >10%) | Terms Sheet §4 + **Exhibit D §D.5(d)** |
| Tenant-funded fit-out ~$98,000; owner keeps improvements | **Exhibit C** (Tenant Work Letter) + v1.5 **Art 4.5** (permanent Alterations remain Landlord's) |
| Owner scope: fire suppression + HVAC (~$50,000), roof & structure | **Exhibit D §§D.7–D.8** + v1.5 **Art 4.2** |
| Phased opening; base rent begins Year 2 | **Exhibit D §D.6** |
| Whole building, single tenant — no CAM / Proportionate Share / relocation | **Exhibit D §D.2** (disapplies v1.5 Art 12 etc.) |
| Liquor-liability + business-income insurance, owner additional insured | **Exhibit D §D.10** (supplements v1.5 Art 6) |
| Year-10 purchase is a goal, **not** a lease term | **Exhibit D §D.12** |
| Alterations consent over $5,000 | v1.5 **Art 4.3** as-is (already $5,000 — no override needed) |
| (Optional $50k capital-systems loan is **not** in the lease — a standalone agreement if the parties want it) | — |

## Confirmed deal points (v0.2, answered July 11, 2026)

1. **Parties**: Landlord **The Burton Landing LLC**; Tenant **eBerry LLC** (both drafted as WA
   LLCs — confirm The Burton Landing LLC's state/type against its Secretary of State registration).
2. **Premises**: 24007 Vashon Hwy SW, Vashon, WA 98070; abbreviated legal in Exhibit A
   (S 100 FT OF N 130 FT OF W 150 FT OF E 180 FT OF GOVT LOT 2 IN NE QTR STR 19-22-03), with the
   vesting deed controlling if the full legal differs.
3. **Term**: **5-year Initial Term**, July 1, 2026 – June 30, 2031, so the parties can assess
   performance on the first term before committing further, plus **one 5-year extension option**
   (Lease Years 6–10, same flat base and breakpoint, notice 9–15 months out) — Exhibit D §D.6. The
   Year-10 purchase goal (D.12) is unaffected: reachable if the option is exercised.
4. **Commencement July 1, 2026** (possession already delivered); **NNN + utilities start
   August 1, 2026**, with July 2026 carried by the landlord; annual costs prorated per diem.
5. **Lease Years are July 1–June 30**; Year 1 abatement ends June 30, 2027 and base rent starts
   July 1, 2027 regardless of fit-out pace (no opening-date abatement machinery needed).
6. **No security deposit, no guaranty** (Terms Sheet §4; Exhibit B is "none").
7. **Operating covenant**: 6 weeks/year seasonal-closure allowance from the Opening Date — Exhibit D §D.5(f).
8. **Alterations consent threshold**: $5,000 — already the v1.5 standard (Art 4.3), so no override.
9. **Audit threshold kept at 10%** as the prospectus proposed (market is 2–5%; owner's counsel may
   push down — flagged, accepted) — Exhibit D §D.5(e).
10. **No capital-systems loan in the lease** — if the parties want it, it's a standalone agreement,
    not referenced here.
11. **No purchase rights** — Year-10 purchase is a goal only — Exhibit D §D.12.
12. **Notices**: Landlord at the property (24007 Vashon Hwy SW); Tenant at 9405 SW Gorsuch Rd.

## Standing drafting notes

- **Parts 2 & 3 are the shared standard form, adopted verbatim** (Option A). As of **Version 1.6
  (July 23, 2026)** the form is fully **neutral** — it names no entity or property; the header says
  the Landlord, Tenant, and Property are identified in the Lease Terms Sheet. `check_site.py` now
  *enforces* neutrality (fails CI if any identity.json entity/address string appears in the form),
  so the only variables in any lease built on it are in Part 1. The Courthouse Square suite-lease
  documents incorporate the same v1.6 form.
- **Deal overrides all live in Exhibit D.** Percentage-rent-in-default-damages (§D.13), SNDA (§D.14),
  and notarization/recording for a 10-year term (§D.15) are there too — the prospectus didn't
  address them.
- **Casualty**: kept the v1.5 form's 180-day repair window (Art 7) rather than overriding to 270;
  raise it in Exhibit D if the tenant wants longer.

## Publishing / next steps

- Both parties review (Part 1 / Exhibit D is what gets negotiated) → bump to v1.0 and regenerate.
- Bump the `**Draft v… — …**` line in `terms-sheet.md` when revising; the build reads the Part-1
  version from there. Parts 2 & 3 keep their own "Version 1.6" stamp and don't change per deal.
