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

- `lease.md` — the full lease draft (source of truth). Draft v0.1, July 11, 2026.
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

## Drafting decisions to confirm (not in the prospectus)

1. **Term = 10 years.** The prospectus never states a term; it shows a 10-year owner-return arc and
   a Year-10 purchase goal, so the draft uses ten Lease Years. Renewal options left as a bracket.
2. **Abatement cap.** Lease Year 1 (and the base-rent clock) starts on the *earlier of* the Opening
   Date or **120 days** after possession — otherwise a slow fit-out would silently extend the free
   year. The 120 days is bracketed; adjust to the real construction schedule.
3. **Operating covenant (Art. 5.7).** Percentage rent is meaningless if the business goes dark, so
   the draft adds a continuous-operation covenant with up to [6] weeks/year of seasonal closure.
   Tenant may want this looser; owner may want it tighter.
4. **Audit threshold.** The prospectus says the tenant bears audit cost if understatement exceeds
   **10%** — drafted as proposed, but note that 2–5% is the customary market threshold; an owner-side
   reviewer will likely push this down.
5. **Percentage rent in default damages** (Art. 14.2): deemed at trailing 36-month average — a
   standard solution the prospectus doesn't address.
6. **Security deposit and guaranty**: prospectus is silent; both left bracketed in Art. 20.
7. **SNDA** (Art. 15.1): future lenders must non-disturb the abatement + percentage structure —
   protects the tenant's Year-1 economics; owners' lenders sometimes resist.
8. **Notarization/recording** (Art. 23.2): Washington requires acknowledgment for a lease over two
   years to be fully effective against third parties — the CS standard lease never needed this
   (short office terms), but a 10-year lease does.
9. **Option B loan rate** is drafted as *fixed at funding* (the prospectus's $474/mo math assumes a
   fixed 9.75%); Option A accrues at floating Prime+3. Confirm intent.
10. **Placeholders throughout**: party names, premises address, legal description (Exhibit A),
    commencement date, alteration-consent threshold, deposit, notice addresses.

## Publishing / next steps

- Fill brackets → attorney review (both sides) → bump to v1.0 and regenerate the PDF.
- The build script stamps the footer from the version line in `lease.md`, so update the
  `**Draft v0.1 — …**` line when revising.
