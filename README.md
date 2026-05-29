# Courthouse Square website

Static marketing site for **Courthouse Square**, a professional office building at 19001 Vashon Hwy SW, Vashon, WA 98070. Owned by Courthouse Square Vashon LLC. Managed by Bangasser & Associates (bangasser.com).

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
│   └── vacancies.json            Source of truth for available suites
├── images/
│   ├── README.md                 What photos go where
│   └── (hero.jpg, gallery-*.jpg, ...)   ← owner drops files here
├── lease/
│   ├── index.html                Leasing process + standard lease (renders lease.md)
│   ├── lease.md                  Current lease text (Markdown). Edit this directly.
│   ├── letter-of-intent.pdf      LOI template — owner uploads
│   ├── lease.pdf                 Convenience pointer to latest archived PDF (auto-generated)
│   ├── history/
│   │   └── index.html            Reverse-chronological list of all versions
│   └── archive/
│       └── v2026.05.28/
│           ├── lease.md          Frozen Markdown copy at the time of the tag
│           └── lease.pdf         Auto-generated PDF (committed by the workflow)
└── .github/workflows/
    └── lease-pdf.yml             Renders lease.md to PDF on every "lease-v*" tag
```

## Editing vacancies

All available suites come from `data/vacancies.json`. To add, remove, or change a suite:

1. Open `data/vacancies.json`.
2. Each entry is an object with these fields:
   ```json
   {
     "unit": "N101",        // suite identifier shown on the card and in the form dropdown
     "building": "North",   // "North" or "South" (only North is currently shown)
     "sqft": 259,           // square footage
     "rent": 815.85,        // monthly base rent
     "cam": 198.19,         // monthly common-area maintenance share
     "utilities": 166.97,   // monthly utilities share
     "allIn": 1181          // rent + cam + utilities, rounded to nearest dollar (headline number)
   }
   ```
3. Save and deploy. The landing page re-renders the suite cards and the form dropdown automatically.

> **Note:** South-building suites are intentionally omitted from the public site for now. To list them publicly, just add their objects to the JSON file with `"building": "South"`.

## Publishing a new lease version

The lease lives in `lease/lease.md`. To publish a new version:

1. **Edit** `lease/lease.md` with your changes.
2. **Commit** the change. Use a descriptive message — it'll show up in `git log` and helps when writing the summary in step 4.
3. **Tag** the commit using the format `lease-vYYYY.MM.DD`:
   ```sh
   git tag lease-v2026.07.15
   git push origin main
   git push origin lease-v2026.07.15
   ```
4. The `.github/workflows/lease-pdf.yml` workflow will:
   - Snapshot `lease/lease.md` to `lease/archive/v2026.07.15/lease.md`
   - Render it to `lease/archive/v2026.07.15/lease.pdf`
   - Copy the PDF to `lease/lease.pdf` (the convenience pointer used by the "Download current lease" button)
   - Commit those files back to the default branch
5. **Update the history page**. Open `lease/history/index.html` and:
   - Copy the existing `<article>` block at the top of the list.
   - Edit the version tag, effective date, and one-line change summary.
   - Update the two `href` paths to point at the new version folder.
   - Move the `Current` badge from the previous entry to the new one.
6. **Update the version banner on the lease page**. Open `lease/index.html` and update:
   - The text inside `<span id="current-version">…</span>` to the new tag.
   - The `href` on the `#lease-pdf-link` button to the new PDF path.

Steps 5 and 6 are intentionally manual so the owner can write a thoughtful change summary at publishing time.

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

To have submissions emailed to **CHSLeasing@bangasser.com**:

1. Open the deployed site's Netlify dashboard → **Forms** → click the `inquiry` form.
2. Go to **Settings & usage** → **Form notifications** → **Add notification** → **Email notification**.
3. Enter `CHSLeasing@bangasser.com` and save.

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
- A registered domain name.

> **Already in place:** the Courthouse Square wordmark (`images/logo.svg`), the standard lease language (`lease/lease.md` + matching PDF in `lease/archive/v2026.05.28/`), and the LOI PDF (`lease/letter-of-intent.pdf`).
>
> The site uses a muted evergreen + warm neutral palette by default. If you want brand-color tweaks, adjust the Tailwind config block at the top of `index.html`, `lease/index.html`, and `lease/history/index.html`.

## Email routing

A single address handles all contact for this site:

- **`CHSLeasing@bangasser.com`** — Bangasser & Associates' inbox for Courthouse Square. This is the Netlify inquiry-form notification target, the address shown in every footer, and where completed Letters of Intent + Good Faith Deposits are sent.

> **Heads up about the LOI PDF.** `lease/letter-of-intent.pdf` is the original Part I document supplied by the prior management. If it still names a `@jtsheffield.com` address inside the PDF itself, replace it with a corrected version when convenient.

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
