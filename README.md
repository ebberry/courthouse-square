# Courthouse Square website

Static marketing site for **Courthouse Square**, a professional office building at 19001 Vashon Hwy SW, Vashon, WA 98070. Owned by Courthouse Square LLC. Managed by Bangasser & Associates (bangasser.com).

The site exists for one job: turn prospective tenants into people who fill out the inquiry form.

## Stack

- Plain HTML + a **prebuilt Tailwind stylesheet** (`css/tailwind.css`, generated from `tailwind.config.js`; no CDN, no runtime compile). Rebuild only when you add new Tailwind classes — see "Rebuilding the stylesheet" below.
- Vanilla JS for the few dynamic pieces (suite cards, form prefill, lease Markdown rendering).
- [marked.js](https://github.com/markedjs/marked) **vendored locally** (`js/vendor/marked.min.js`, v12.0.2), used only on the lease page to render `lease.md` to HTML in the browser. No third-party scripts anywhere.
- [Netlify Forms](https://docs.netlify.com/forms/setup/) for the inquiry form. No server required.
- A GitHub Action (`checks.yml`) that runs `tools/check_site.py` sanity checks on every push.

## File layout

```
/
├── index.html                    Landing page
├── README.md                     This file
├── robots.txt / sitemap.xml      Search-engine plumbing
├── netlify.toml                  Security headers for the Netlify deploy
├── tailwind.config.js            Shared Tailwind theme (single source for both pages)
├── css/
│   └── tailwind.css              Prebuilt stylesheet (generated; commit it)
├── js/
│   ├── lease-builder.js          Lease Builder generation engine (staff tool)
│   └── vendor/
│       ├── marked.min.js         Vendored Markdown renderer for the lease page
│       ├── pdf-lib.min.js        Vendored PDF library for the Lease Builder
│       └── fontkit.umd.min.js    Vendored font engine (custom TTFs in builder PDFs)
├── data/
│   ├── identity.json             Entity, addresses, version stamp (single source of truth)
│   ├── vacancies.json            Source of truth for available suites ({asOf, buildingSqft, suites})
│   └── tenants.json              Tenant roster for the Your Neighbors wall
├── images/
│   ├── README.md                 What photos go where
│   ├── favicon.svg               Browser-tab icon
│   ├── og-card.png               Social-share preview card (1200×630)
│   └── (sculpture.jpg, gallery-*.jpg, ...)   ← owner drops files here
├── lease/
│   ├── index.html                Leasing process + standard lease (renders lease.md)
│   ├── builder.html              Lease Builder: staff checklist → signed-ready lease (unlinked, noindex)
│   ├── lease.md                  Standard Lease Terms + Definitions (Markdown). Edit this directly.
│   ├── lease.pdf                 "Read the full standard lease" download (generated)
│   ├── lease-terms-sheet.pdf     Fillable Lease Terms Sheet example (generated)
│   ├── letter-of-intent.pdf      Fillable Letter of Intent & Application (generated)
│   └── archive/
│       ├── v2026.05.31/ ... v2026.06.12/   Prior versions (internal record)
│       └── v2026.06.29/          Current version snapshot (v1.5)
├── fonts/                        Jost + Libre Baskerville TTFs (PDF build + Lease Builder)
├── tools/
│   ├── build_lease_docs.py       Regenerates all lease PDFs (reportlab + pypdf; byte-reproducible)
│   ├── check_site.py             Sanity checks: pricing math, version stamps, links (run in CI)
│   ├── test_builder.py           Lease Builder end-to-end test (playwright + pypdf)
│   ├── release_lease.py          One-step lease version bump (identity, rebuild, archive, checks)
│   └── tailwind.src.css          Source for the generated css/tailwind.css
├── review/                       Internal only, git-ignored (NOT deployed):
│                                   the full consolidated review PDF (all parts merged)
└── .github/workflows/
    ├── checks.yml                Runs tools/check_site.py on every push/PR
    └── builder-e2e.yml           Lease Builder browser test (runs when builder files change)
```

## Rebuilding the stylesheet

`css/tailwind.css` is a committed, prebuilt artifact (like the lease PDFs), so the deploy still has no build step. Rebuild it only when you add a Tailwind class that isn't already used somewhere in the two HTML files:

```sh
npx tailwindcss@3 -c tailwind.config.js -i tools/tailwind.src.css -o css/tailwind.css --minify
```

If a new class ever seems to have no effect, this rebuild is the first thing to try.

## The "Your Neighbors" card wall

The landing page has one unified card wall (the `#suites` section) that merges the old "Current tenants" and "Available suites" sections. It reads from **both** data files and renders two kinds of cards on the same masonry wall:

- **Occupied cards** come from `data/tenants.json` (the businesses already leasing).
- **Open cards** come from `data/vacancies.json` (suites available to lease), with a warm tint, a breathing glow, an "OPEN" ribbon, the all-in monthly price framed as a starting point, and a "you'd be next to ..." line naming the nearest neighbors.

**The wall is adaptive.** With at least one tenant in `tenants.json`, it presents as "Meet the neighbors you'd be keeping," with a tally (`X suites / Y neighbors / Z open`), category filter tags, and a "See what's open" toggle. With `tenants.json` empty (`[]`), it gracefully shows just the open suites as a polished available-suites wall, no empty tally or filters. It blooms into the full treatment the moment you add tenants. No code change needed either way.

### Editing tenants (`data/tenants.json`)

Each entry is an object. Only `name` is required; everything else gracefully omits if missing.

```json
{
  "name":     "Smith Family Dental",                     // displayed business name (required)
  "suite":    "N101",                                    // suite number, shown on the card (optional)
  "category": "Dental",                                  // drives the filter tag + accent color (optional)
  "blurb":    "General dentistry, cosmetic, pediatric.", // 1 to 2 sentence description (optional)
  "website":  "https://smithfamilydental.com",           // tenant's site (optional)
  "phone":    "(206) 555-0100",                          // optional, shown small on the card
  "email":    "hello@smithfamilydental.com",             // optional, shown small on the card
  "logo":     "/images/tenants/smith-family-dental.png"  // optional, see images/tenants/README.md
}
```

**Category vocabulary.** The `category` value both creates a filter tag and sets the card's left accent-stripe color. Recognized values (case-insensitive) include: `professional`, `medical`, `dental`, `wellness`, `therapy`, `bodywork`, `legal`, `accounting`, `tutoring`, `creative`, `retail`, `food`. Any other value still works (it just uses a neutral accent). To add or recolor categories, edit the `CATEGORY_ACCENTS` map in the script block of `index.html`.

### Editing vacancies (`data/vacancies.json`)

The file is an object: `asOf` (the date the prices were set, shown as "Pricing snapshot as of ..." under the wall — update it whenever you change prices) and `suites`, the array of open suites:

```json
{
  "asOf": "2026-05-21",
  "suites": [
    {
      "unit": "N101",        // suite identifier, shown on the card and in the form dropdown
      "building": "North",   // "North" or "South" (only North is currently shown)
      "sqft": 259,           // square footage
      "rent": 815.85,        // monthly base rent
      "cam": 198.19,         // monthly common-area maintenance share
      "utilities": 166.97,   // monthly utilities share
      "allIn": 1181,         // rent + cam + utilities, rounded (the headline figure)
      "fit": "Room for a small practice with a waiting area."  // "who'd thrive here" line (optional)
    }
  ]
}
```

`tools/check_site.py` (run automatically in CI) verifies that `rent + cam + utilities` matches `allIn` for every suite, so a typo in the math fails the check rather than reaching the site.

The "you'd be next to ..." line on each open card is derived automatically from the nearest occupied tenants (same building letter, closest suite number), so you don't maintain it by hand. It simply doesn't appear until there are tenants to name.

> **Note:** South-building suites are intentionally omitted from the public site for now. To list them publicly, add their objects to `vacancies.json` with `"building": "South"`.

> **To make the wall come alive:** add the real tenant roster to `data/tenants.json`. Each business submits its own content (blurb, optional phone/email/photo, website); the owner places it. Until then the wall shows the open suites only.

## The lease document set (Version 1.6, July 23, 2026)

The lease is split into plain-named pieces rather than numbered "Parts":

- **Standard Lease Terms** + **Definitions & Glossary** — the standard terms that apply to every tenant. Source of truth: `lease/lease.md`. Rendered on `/lease/` and downloadable as `lease/lease.pdf`.
- **Lease Terms Sheet** — the deal-specific terms a tenant fills in and signs (this merges what used to be Parts II and III). A blank **fillable PDF** (real AcroForm fields + checkboxes) is published at `lease/lease-terms-sheet.pdf`.
- **Letter of Intent & Application** — a **fillable PDF** form (applicant intake). Published at `lease/letter-of-intent.pdf` and linked from `/lease/`. Its fields are also offered as optional fields on the homepage inquiry form.

**One version track, one identity source.** All documents are at **Version 1.6, July 23, 2026**, which makes the Standard Lease Terms + Definitions a **neutral form**: it names no entity or property (the header points to the Lease Terms Sheet for the parties and Property), so other properties can incorporate the identical form verbatim — the Burton Inn lease (`burton-inn/`) is the first to do so — and `tools/check_site.py` now fails CI if any entity/address string from `identity.json` appears in the form text. v1.6 carries forward v1.5's June 28, 2026 attorney redlines (J. Sayre): a full commercial remedies article (termination damages with acceleration, re-entry/reletting with defined Reletting Expenses, waiver of redemption, property-removal procedure), landlord default-and-cure with a sole-remedy cap, mutual Industrial Insurance Act immunity waiver, landlord assignment without consent, tightened holdover language, notice-service rules with the landlord notice address at **20704 Vashon Highway SW** (the building itself remains 19001), Exhibit A repurposed as the **Legal Description**, and an Experian credit-application step in the LOI. Entity, addresses, and version stamps live in **`data/identity.json`** — the single source consumed by `tools/build_lease_docs.py` and `js/lease-builder.js` and enforced by `tools/check_site.py`. Prior published versions are snapshotted in `lease/archive/` (v2026.05.31, v2026.06.08, v2026.06.12, v2026.06.29 = v1.5, v2026.07.23 = v1.6).

### The Lease Builder (electronic lease preparation)

**`/lease/builder.html`** is a staff tool (not linked from the public nav, `noindex`) that turns a
filled-in checklist into the actual lease documents, entirely in the browser — no server, nothing
uploaded anywhere. Open it, pick the suite (numbers prefill from `data/vacancies.json` and stay
editable), fill in the deal, and click **Generate**. Two PDFs download:

1. **The signature-ready lease package** — a filled Lease Terms Sheet followed by the full posted
   standard lease text. Optional items left blank are treated as *not applicable* and are omitted
   entirely (no guarantor → no guarantor signature block and no Exhibit B; no tenant work → no
   Exhibit C; CAM lease → no Exhibit D; and so on). The document reflows around what's omitted.
2. **A two-page record** — the completed checklist on page one (including exactly what was
   omitted and why), and the suite's full CAM & cost calculations on page two: proportionate
   share (suite ÷ building sq ft), monthly/annual/per-sq-ft cost table, CAM rate detail, and the
   total due at signing (first month + deposit − the $100 Good Faith Deposit credit).

Beyond the basics, the builder also:

- **Imports**: drop a filled Letter of Intent PDF, a previously generated record PDF, or a saved
  `.json` deal file onto the page and the checklist prefills. Every record PDF carries its deal
  data as an embedded `deal.json`, so any past deal can be reloaded and regenerated (e.g. after a
  lease version bump).
- **Prorates** mid-month starts (per-diem on rent + CAM + shared utilities) and prints the
  proration math on the record.
- **Auto-saves** a draft to the browser's localStorage ("Reset form & clear draft" to discard).
- **Attaches exhibits**: upload PDFs for Exhibit A (Legal Description — or drop one at
  `lease/exhibits/exhibit-a-legal-description.pdf` to auto-attach), Exhibit B (guaranty rider),
  and Exhibit D (NNN amendment); each gets a styled cover page in the package.
- **Handles South-building / unlisted suites** via "Other / manual entry" in the suite dropdown.
- **Embeds invisible e-sign anchors** (`/sn1/`…`/ds3/`) at the signature lines so DocuSign/Adobe
  Sign auto-place fields when staff upload the package.
- **Guarantees the two-page record**: type sizes step down and long free-text clips rather than
  spilling to a third page.
- Prints a **projected rent schedule** on the CAM page when the escalation text contains a
  percentage and the term is 2+ years.
- **Interprets natural-language requests** (section 6, "Additional Terms & Requests"). Staff type
  each tenant request on its own line — *"Can have a dog"* — and click **Interpret with Claude**:
  the browser sends the request lines plus the full posted lease text directly to the Anthropic
  API (`claude-opus-4-8`), which returns a structured disposition per request — **covered** (the
  lease already permits it; the exact article is cited), **granted** (a drafted, lease-ready term),
  or **needs attorney review**. Every suggestion appears as an editable review card; nothing enters
  the lease unapproved. Approved terms render as a numbered **Additional Terms** section on the
  Terms Sheet (with clause references, e.g. *"already provided for under Article 3.5"*), later
  sections renumber around it, and the record documents every request and its disposition. The
  staff member's API key is stored only in their browser (localStorage) and sent only to
  api.anthropic.com. **Add as written (no AI)** is the offline path: each line becomes a verbatim
  editable term. The Letter of Intent has a matching "additional requests" field (`loi_notes`)
  that imports into the checklist.

The document design is the midcentury house style — Jost (Futura revival) display type and Libre
Baskerville text, shared with the Python-built PDFs via the TTFs in `fonts/`. Powered by the
vendored `js/vendor/pdf-lib.min.js` + `fontkit.umd.min.js` + `js/lease-builder.js`. Identity
(entity, addresses, version) comes from `data/identity.json` at runtime, with fallback literals
cross-checked by `tools/check_site.py` in CI. The **building total rentable square footage** used
for proportionate-share math lives in `data/vacancies.json` (`buildingSqft`).

`tools/test_builder.py` is the end-to-end test (maximal deal, omission matrix, record-import
round-trip, LOI import, additional terms against a mocked Anthropic API, and a layout scan that
fails on margin overruns or overlapping text; set `ANTHROPIC_API_KEY` to also exercise the live
Claude path); `.github/workflows/builder-e2e.yml` runs it in CI when builder files change. `tools/release_lease.py --version "Version 1.6" --date "July 20, 2026"` automates a
version bump: identity.json, the lease-page version line, rebuild, archive snapshot, checks.

### Regenerating the lease PDFs

The PDFs are generated locally from `lease/lease.md` plus the form/LOI content embedded in the build script. One-time setup: `pip install reportlab pypdf`. Then:

```sh
python3 tools/build_lease_docs.py
```

This writes:
- `lease/lease.pdf` (Standard Lease Terms + Definitions — v1.2)
- `lease/lease-terms-sheet.pdf` (fillable Lease Terms Sheet — v1.3)
- `lease/letter-of-intent.pdf` (fillable Letter of Intent & Application, public — v1.3)
- `review/CourthouseSquare_FullLease_v<date>.pdf` (the full consolidated package, for deep review; form fields preserved via `PdfWriter.append`)

### Publishing a new version

1. Bump `version` / `versionDate` in `data/identity.json` (single source for all documents and the Lease Builder).
2. Edit `lease/lease.md` (and the Terms Sheet / LOI content in the script) as needed.
3. Run `python3 tools/build_lease_docs.py`.
4. Snapshot the new public docs into `lease/archive/v<YYYY.MM.DD>/` (copy `lease.md`, `lease.pdf`, `lease-terms-sheet.pdf`, `letter-of-intent.pdf`).
5. Update the small "Version X, date" line in `lease/index.html` near the download buttons.
6. Commit and push. Netlify redeploys automatically.

> **Legacy GitHub Action:** retired. The old `lease-pdf.yml` (which rendered a plain pandoc PDF on `lease-v*` tag pushes and could overwrite the curated `lease.pdf`) has been deleted; the local build script is the only PDF pipeline. The remaining workflow, `checks.yml`, only runs read-only sanity checks.

> **Public versioning UI:** still off, per your earlier request. The documents are version-stamped and archived internally, but there's no public version banner or history page. Easy to resurface later.

> **The Letter of Intent & Application** is now published: a fillable PDF at `lease/letter-of-intent.pdf`, linked from `/lease/`, and its fields are also available as optional fields on the homepage inquiry form. Prospects can apply online, download the PDF, or just send the short inquiry and we follow up.

## Swapping in real photos

See `images/README.md` for the full list of filenames and recommended sizes. Quick version:

- Drop files into `/images/` using the exact filenames listed there.
- The site picks them up automatically — no code change needed.
- If a file is missing, the page falls back to a muted evergreen placeholder so nothing breaks visually.

## Deploying to Netlify

1. Create a new site on [Netlify](https://app.netlify.com/start) and connect this repository.
2. Build settings:
   - **Build command:** *(leave blank)*
   - **Publish directory:** *(leave blank or set to `/`)*
3. Click Deploy. That's it.

### Netlify Forms (inquiry form delivery)

Netlify automatically detects the `<form name="inquiry" data-netlify="true">` block in `index.html` on first deploy and starts capturing submissions.

To have submissions emailed to **leasing@courthousesquarevashon.com**:

1. Open the deployed site's Netlify dashboard → **Forms** → click the `inquiry` form.
2. Go to **Settings & usage** → **Form notifications** → **Add notification** → **Email notification**.
3. Enter `leasing@courthousesquarevashon.com` and save.

Submissions also remain visible in the Netlify dashboard as a backup.

### Custom domain

Once a domain is registered, add it under **Domain management** in the Netlify dashboard and follow the prompts. Netlify provisions a free TLS certificate automatically.

## Deploying to GitHub Pages (alternative)

If you'd rather host on GitHub Pages:

1. Push the repo to GitHub.
2. Repository **Settings** → **Pages** → set source to the default branch, root folder.
3. Wait ~1 minute for Pages to build. Your site will be available at `https://<owner>.github.io/<repo>/`.

> **Heads up:** GitHub Pages doesn't include a form backend. If you go this route, swap the inquiry form to a third-party service (e.g. Formspree, Basin, or Web3Forms) by changing the form's `action` attribute. Netlify Forms is recommended primarily because it requires zero extra setup.

## Things the owner still needs to provide

- Real building photos (see `images/README.md`).

> **Already in place:** the domain (courthousesquarevashon.com, live on Netlify), the Courthouse Square wordmark (`images/logo.svg`), and the standard lease language v1.1 (`lease/lease.md` + matching PDF in `lease/archive/v2026.05.31/`).
>
> The site uses a muted evergreen + warm neutral palette (plus a rust accent on the suites wall) by default. If you want brand-color tweaks, adjust the Tailwind config block at the top of `index.html` and `lease/index.html`.

## Email routing

A single address handles all contact for this site:

- **`leasing@courthousesquarevashon.com`** — the building's own leasing inbox. This is the Netlify inquiry-form notification target, the address shown in every footer, the LOI-submission address in the lease text and the Part I LOI PDF, and where completed Letters of Intent + Good Faith Deposits are sent.

> **Setup reminder:** this address must exist as a real mailbox (or alias/forward) on the courthousesquarevashon.com domain, and the Netlify Forms email notification must be pointed at it (Forms → `inquiry` → Settings & usage → Form notifications). Until both are done, inquiries won't reach anyone.

## Accessibility &amp; performance notes

- Semantic HTML throughout (`<header>`, `<main>`, `<section>`, `<article>`, `<address>`, `<nav>`, `<footer>`).
- All images carry descriptive `alt` text.
- Color contrast targets WCAG AA against the evergreen / sand palette.
- No third-party scripts at all: Tailwind is a prebuilt ~17 KB stylesheet, and marked.js is vendored locally (lease page only).
- Gallery images lazy-load with explicit dimensions (no layout shift); Google Fonts are preconnected for faster first paint.
- Keyboard focus is visibly indicated (rust outline) on links, buttons, and summaries.

## Local preview

For quick edits, open `index.html` directly in a browser. The vacancies and lease-rendering features need an HTTP origin to work (because `fetch()` won't load `file://` URLs in most browsers), so to test those features serve the directory:

```sh
# any one of these will do
python3 -m http.server 8080
# or
npx serve .
```

Then visit `http://localhost:8080/`.
