# Courthouse Square website

Static marketing site for **Courthouse Square**, a professional office building at 19001 Vashon Hwy SW, Vashon, WA 98070. Owned by Courthouse Square LLC. Managed by Bangasser & Associates (bangasser.com).

The site exists for one job: turn prospective tenants into people who fill out the inquiry form.

## Stack

- Plain HTML + [Tailwind CSS via CDN](https://tailwindcss.com/docs/installation/play-cdn). No build step.
- Vanilla JS for the few dynamic pieces (suite cards, form prefill, lease Markdown rendering).
- [marked.js](https://github.com/markedjs/marked) via CDN, used only on the lease page to render `lease.md` to HTML in the browser.
- [Netlify Forms](https://docs.netlify.com/forms/setup/) for the inquiry form. No server required.
- A GitHub Action that renders each tagged lease version to PDF.

## File layout

```
/
├── index.html                    Landing page
├── README.md                     This file
├── data/
│   ├── vacancies.json            Source of truth for available suites
│   └── tenants.json              Tenant roster for the Your Neighbors wall
├── images/
│   ├── README.md                 What photos go where
│   └── (sculpture.jpg, gallery-*.jpg, ...)   ← owner drops files here
├── lease/
│   ├── index.html                Leasing process + standard lease (renders lease.md)
│   ├── lease.md                  Standard Lease Terms + Definitions (Markdown). Edit this directly.
│   ├── lease.pdf                 "Read the full standard lease" download (generated)
│   ├── lease-terms-sheet.pdf     Fillable Lease Terms Sheet example (generated)
│   └── archive/
│       ├── v2026.05.31/          Prior version (internal record)
│       └── v2026.06.08/          Current version: lease.md, lease.pdf, lease-terms-sheet.pdf
├── tools/
│   └── build_lease_docs.py       Regenerates all lease PDFs (run with reportlab + pypdf)
├── review/                       Internal only, git-ignored (NOT deployed):
│                                   letter-of-intent.pdf + the full consolidated review PDF
└── .github/workflows/
    └── lease-pdf.yml             Legacy tag-based PDF render (superseded; see note below)
```

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

```json
{
  "unit": "N101",        // suite identifier, shown on the card and in the form dropdown
  "building": "North",   // "North" or "South" (only North is currently shown)
  "sqft": 259,           // square footage
  "rent": 815.85,        // monthly base rent
  "cam": 198.19,         // monthly common-area maintenance share
  "utilities": 166.97,   // monthly utilities share
  "allIn": 1181,         // rent + cam + utilities, rounded (the headline figure)
  "fit": "Room for a small practice with a waiting area, such as therapy or bodywork."  // "who'd thrive here" line (optional)
}
```

The "you'd be next to ..." line on each open card is derived automatically from the nearest occupied tenants (same building letter, closest suite number), so you don't maintain it by hand. It simply doesn't appear until there are tenants to name.

> **Note:** South-building suites are intentionally omitted from the public site for now. To list them publicly, add their objects to `vacancies.json` with `"building": "South"`.

> **To make the wall come alive:** add the real tenant roster to `data/tenants.json`. Each business submits its own content (blurb, optional phone/email/photo, website); the owner places it. Until then the wall shows the open suites only.

## The lease document set (standard terms v1.2 · intake forms v1.3)

The lease is split into plain-named pieces rather than numbered "Parts":

- **Standard Lease Terms** + **Definitions & Glossary** — the standard terms that apply to every tenant. Source of truth: `lease/lease.md`. Rendered on `/lease/` and downloadable as `lease/lease.pdf`.
- **Lease Terms Sheet** — the deal-specific terms a tenant fills in and signs (this merges what used to be Parts II and III). A blank **fillable PDF** (real AcroForm fields + checkboxes) is published at `lease/lease-terms-sheet.pdf`.
- **Letter of Intent** — an internal intake **fillable PDF** form. Lives only in the git-ignored `review/` folder; it is not deployed.

**Two version tracks.** The Standard Lease Terms + Definitions are at **Version 1.2, June 8, 2026** (`VERSION` / `VDATE` in `tools/build_lease_docs.py`), held there pending the attorneys' redlines. The two intake forms (Letter of Intent + Lease Terms Sheet) are at **Version 1.3, June 12, 2026** (`FORM_VERSION` / `FORM_VDATE`), reflecting the assembled package: entity **Courthouse Square Vashon LLC**, building address **19001 Vashon Hwy SW**, and updated field labels. The two stamps move independently so the forms could advance without restamping the un-redlined standard terms.

### Regenerating the lease PDFs

The PDFs are generated locally from `lease/lease.md` plus the form/LOI content embedded in the build script. One-time setup: `pip install reportlab pypdf`. Then:

```sh
python3 tools/build_lease_docs.py
```

This writes:
- `lease/lease.pdf` (Standard Lease Terms + Definitions — v1.2)
- `lease/lease-terms-sheet.pdf` (fillable Lease Terms Sheet — v1.3)
- `review/letter-of-intent.pdf` (fillable Letter of Intent, internal — v1.3)
- `review/CourthouseSquare_FullLease_v<date>.pdf` (the full consolidated package, for deep review; form fields preserved via `PdfWriter.append`)

### Publishing a new version

1. Bump `VERSION` / `VDATE` at the top of `tools/build_lease_docs.py`.
2. Edit `lease/lease.md` (and the Terms Sheet / LOI content in the script) as needed.
3. Run `python3 tools/build_lease_docs.py`.
4. Snapshot the new public docs into `lease/archive/v<YYYY.MM.DD>/` (copy `lease.md`, `lease.pdf`, `lease-terms-sheet.pdf`).
5. Update the small "Version X, date" line in `lease/index.html` near the download buttons.
6. Commit and push. Netlify redeploys automatically.

> **Legacy GitHub Action:** `.github/workflows/lease-pdf.yml` renders `lease.md` to a plain pandoc PDF on `lease-v*` tag pushes. It is **superseded** by the local build script (which also produces the branded styling and the fillable form). Do not push `lease-v*` tags, or it will overwrite the curated `lease.pdf`. Tell me if you'd like it retired.

> **Public versioning UI:** still off, per your earlier request. The documents are version-stamped and archived internally, but there's no public version banner or history page. Easy to resurface later.

> **The Letter of Intent** is internal: no public button, not deployed. Prospects reach out via the form/email; the LOI is handled internally from there.

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
- No heavyweight libraries — only Tailwind via CDN and (on the lease page only) marked.js.
- Google Fonts are preconnected for faster first paint.

## Local preview

For quick edits, open `index.html` directly in a browser. The vacancies and lease-rendering features need an HTTP origin to work (because `fetch()` won't load `file://` URLs in most browsers), so to test those features serve the directory:

```sh
# any one of these will do
python3 -m http.server 8080
# or
npx serve .
```

Then visit `http://localhost:8080/`.
