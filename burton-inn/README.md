# The Burton Inn — lease working folder

Deal-specific lease for **The Burton Inn** (Burton, Vashon Island, WA), drafted from the tenant's
**"Rent Basis & Owner Return" prospectus (July 2026)**. This folder is intentionally separate from
`lease/` (the Courthouse Square standard multi-tenant office lease): the Burton Inn deal is a
whole-building, single-tenant, triple-net lease with percentage rent — a different animal — so it
gets a standalone document rather than the Terms Sheet + Standard Terms stack.

> **Not public.** `netlify.toml` force-redirects `/burton-inn/*` away from the deployed site, so
> committing these files does not publish them on courthousesquarevashon.com. (The standard lease
> in `lease/` remains public by design; this one is a confidential draft between two parties.)

## Files

- `lease.md` — the full lease draft (source of truth). Draft v0.2, July 11, 2026.
- `lease.pdf` — generated, house document style. Rebuild: `python3 tools/build_burton_lease.py`.

## How the prospectus maps into the lease

| Prospectus term | Lease provision |
|---|---|
| Triple-net from day one: taxes ($8,500) + insurance ($6,500) + routine maintenance ($375/mo) ≈ $19,500/yr, at actuals, incl. Year 1; tenant carries utilities | Art. 6 (and Art. 4.5 net-lease intent) |
| Fixed base rent $19,800/yr ($1,650/mo), abated Year 1, flat thereafter (no escalators — the % rent is the escalator) | Art. 4 |
| Percentage rent: 10% of gross revenue over $198,000 natural breakpoint, receipts-based; monthly statements, quarterly remittance, annual certified reconciliation, owner audit vs POS (tenant pays audit cost if understatement >10%); live in Year 1 above the breakpoint | Art. 5 |
| Tenant-funded fit-out ~$98,000 (flooring, paint, kitchen retrofit & permits, furnishings); owner keeps improvements however the tenancy evolves | Art. 8, Exhibit B |
| Owner scope: fire suppression + HVAC (~$50,000), roof & structure | Art. 9.2, Exhibit C |
| Optional $50k tenant loan at Prime+3 (9.75% today), Option A rent credits / Option B 20-yr note (~$474/mo), separable from the lease | Exhibit D |
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
10. **Exhibit D loan election left open** for the owner to initial at signing.
11. **No purchase rights** — Art. 19 keeps the Year-10 purchase as a goal only, per the prospectus.
12. **Notices**: both parties at the property address.

## Standing drafting notes

- **Percentage rent in default damages** (Art. 14.2): deemed at trailing 36-month average — a
  standard solution the prospectus doesn't address.
- **SNDA** (Art. 15.1): future lenders must non-disturb the abatement + percentage structure.
- **Notarization/recording** (Art. 23.2): Washington requires acknowledgment for a lease over two
  years; signing should happen before a notary, memorandum recordable on request.
- **Option B loan rate** is drafted as *fixed at funding* (the prospectus's $474/mo math assumes a
  fixed 9.75%); Option A accrues at floating Prime+3.

## Publishing / next steps

- Both parties review → bump to v1.0 and regenerate the PDF.
- The build script stamps the footer from the version line in `lease.md`, so update the
  `**Draft v0.2 — …**` line when revising.
