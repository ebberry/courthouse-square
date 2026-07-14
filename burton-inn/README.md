# The Burton Inn — lease working folder

Deal-specific lease for **The Burton Inn** (Burton, Vashon Island, WA), drafted from the tenant's
**"Rent Basis & Owner Return" prospectus (July 2026)**. This folder is intentionally separate from
`lease/` (the Courthouse Square standard multi-tenant office lease): the Burton Inn deal is a
whole-building, single-tenant, triple-net lease with percentage rent — a different animal.

It follows the **same three-part template** as the Courthouse Square documents (see the Bob's
Bakery lease for the reference format) — a deal-specific Lease Terms Sheet with nine numbered
sections and a signature page, a Standard Lease Terms boilerplate in numbered Articles, and a
Definitions & Glossary, executed and read together, with the Terms Sheet controlling on conflict.
It does **not** reuse the `lease/` boilerplate text — that form is built for multi-tenant office
(CAM, proportionate share, common areas, relocation, no percentage rent) and names a different
landlord entity. So the Burton Inn has its own parametric boilerplate, pruned to what the deal
needs, in the same house format.

> **Not public.** `netlify.toml` force-redirects `/burton-inn/*` away from the deployed site, so
> committing these files does not publish them on courthousesquarevashon.com. (The standard lease
> in `lease/` remains public by design; this one is a confidential draft between two parties.)

## Files

Three source documents — the three parts of the Lease (all Markdown, edit directly), Draft v0.6,
July 14, 2026:

- `terms-sheet.md` → `terms-sheet.pdf` — **Part 1, Lease Terms Sheet**: the deal page, laid out in
  the same nine numbered sections as the Courthouse Square template (1 Parties · 2 Premises · 3 Term
  · 4 Financial Obligations · 5 Operations & Special Conditions · 6 Additional Terms · 7 Notices ·
  8 Incorporation & Merger · 9 Index of Exhibits), then a signature block with DocuSign/Adobe
  e-sign anchors (`/sn1/`, `/ds1/`, `/sn2/`, `/ds2/`), then the four Exhibits (A legal description,
  B tenant's work, C landlord systems). Every deal-specific value lives here and nowhere else.
- `standard-terms.md` → `standard-terms.pdf` — **Part 2, Standard Lease Terms**: the operating/legal
  boilerplate (Articles 2–23), written parametrically so it refers to the numbers "stated in the
  Lease Terms Sheet" rather than hardcoding them.
- `definitions.md` → `definitions.pdf` — **Part 3, Definitions & Glossary**: the defined terms used
  across Parts 1 and 2. Terms defined on the Terms Sheet control where they differ.
- `lease.pdf` — the three parts merged into one signable package (Terms Sheet, Standard Terms,
  Definitions), each starting on a fresh page, with continuous page numbering. Generated only.
- `lease.docx` — the same combined document as an **editable Word file for redlining** (real Word
  heading styles, so Track Changes and the navigation pane work). Generated only; regenerate after
  any Markdown edit. Round-trip: hand this out → receive the redlined `.docx` back → apply the
  accepted changes to the Markdown source (the Markdown stays the source of truth).

Rebuild the PDFs: `python3 tools/build_burton_lease.py` (stamps each footer from the
`**Draft v0.6 — …**` version line in `terms-sheet.md`, so bump that line when revising).
Rebuild the Word file: `python3 tools/build_burton_docx.py`.

**Terms Sheet controls on conflict.** All three parts carry the applicability note; where they
disagree, the Terms Sheet governs. To change a deal number, edit only `terms-sheet.md`.

## How the prospectus maps into the lease

| Prospectus term | Lease provision |
|---|---|
| Triple-net from day one: taxes ($8,500) + insurance ($6,500) + routine maintenance ($375/mo) ≈ $19,500/yr, at actuals, incl. Year 1; tenant carries utilities | Art. 6 (and Art. 4.5 net-lease intent) |
| Fixed base rent $19,800/yr ($1,650/mo), abated Year 1, flat thereafter (no escalators — the % rent is the escalator) | Art. 4 |
| Percentage rent: 10% of gross revenue over $198,000 natural breakpoint, receipts-based; monthly statements, quarterly remittance, annual certified reconciliation, owner audit vs POS (tenant pays audit cost if understatement >10%); live in Year 1 above the breakpoint | Art. 5 |
| Tenant-funded fit-out ~$98,000 (flooring, paint, kitchen retrofit & permits, furnishings); owner keeps improvements however the tenancy evolves | Art. 8, Exhibit B |
| Owner scope: fire suppression + HVAC (~$50,000), roof & structure | Art. 9.2, Exhibit C |
| (The prospectus's optional $50k tenant loan for the owner's capital systems is **not** in the lease — removed entirely at v0.6; if the parties want it, it is a standalone loan agreement between them, wholly separate from this Lease) | — |
| Phased opening: rooms first (Year 1 begins), kitchen/bar ~3 months later; base rent begins Year 2 | Art. 3.3–3.4, 4.2 |
| Liability & liquor-liability insurance, owner additional insured | Art. 10 |
| Year-10 purchase is a goal, **not** a lease term | Art. 19 |
| Lease is a single obligation of the operating company (line-of-business rent allocation is illustrative) | Art. 4.6 |

## Confirmed deal points (v0.2, answered July 11, 2026)

1. **Parties**: Landlord **The Burton Landing LLC**; Tenant **eBerry LLC** (both drafted as WA
   LLCs — confirm The Burton Landing LLC's state/type against its Secretary of State registration).
2. **Premises**: 24007 Vashon Hwy SW, Vashon, WA 98070; abbreviated legal in Exhibit A
   (S 100 FT OF N 130 FT OF W 150 FT OF E 180 FT OF GOVT LOT 2 IN NE QTR STR 19-22-03), with the
   vesting deed controlling if the full legal differs.
3. **Term**: 10 Lease Years, July 1, 2026 – June 30, 2036, plus **one 5-year option** (same terms,
   same flat base and breakpoint, notice 9–15 months out) — Art. 3.5.
4. **Commencement July 1, 2026** (possession already delivered); **NNN + utilities start
   August 1, 2026**, with July 2026 carried by the landlord; annual costs prorated per diem.
5. **Lease Years are July 1–June 30**; Year 1 abatement ends June 30, 2027 and base rent starts
   July 1, 2027 regardless of fit-out pace (no opening-date abatement machinery needed).
6. **No security deposit, no guaranty** (Art. 20 records the reasoning: the fit-out that attaches
   to the building + NNN structure serve that function).
7. **Operating covenant**: 6 weeks/year seasonal-closure allowance, running from the Opening Date.
8. **Alterations consent threshold**: $5,000 (matches the Courthouse Square standard).
9. **Audit threshold kept at 10%** as the prospectus proposed (market is 2–5%; owner's counsel may
   push down — flagged, accepted).
10. **No capital-systems loan in the lease.** The prospectus's optional $50k tenant→owner loan
    (former Exhibit D) is removed entirely as of v0.6 per owner request — no Exhibit D, no
    borrower/lender language. If the parties want it, it lives in a wholly separate loan agreement
    with no reference in this Lease. Exhibit C still puts the fire-suppression/HVAC scope on the
    owner; how the owner funds it is off-document.
11. **No purchase rights** — Art. 19 keeps the Year-10 purchase as a goal only, per the prospectus.
12. **Notices**: Landlord at the property (24007 Vashon Hwy SW); Tenant at 9405 SW Gorsuch Rd.

## Standing drafting notes

- **Percentage rent in default damages** (Art. 14.2): deemed at trailing 36-month average — a
  standard solution the prospectus doesn't address.
- **SNDA** (Art. 15.1): future lenders must non-disturb the abatement + percentage structure.
- **Notarization/recording** (Art. 23.2): Washington requires acknowledgment for a lease over two
  years; signing should happen before a notary, memorandum recordable on request.
- **Capital-systems loan**: entirely out of the lease as of v0.6 (no Exhibit D). If the owner and
  tenant paper one, keep it a standalone agreement — do not reintroduce it or any borrower/lender
  language into these three documents.

## Publishing / next steps

- Both parties review → bump to v1.0 and regenerate the PDFs.
- Bump the `**Draft v… — …**` line in `terms-sheet.md` (and match it in `standard-terms.md`) when
  revising; the build script reads the version from the Terms Sheet.
