#!/usr/bin/env python3
"""Sanity checks for the Courthouse Square site.

Guards the invariants that have historically drifted: suite pricing math,
data-file shape, version stamps, and download links. Stdlib-only so the owner
can run it anywhere; the PDF content checks activate only if pypdf is present.

Run:  python3 tools/check_site.py     (exit 0 = all good, 1 = problems)
      python3 tools/build_pages.py --check   (separately: generated pages and sitemap.xml are fresh)
"""

import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
problems = []
checks = 0

def check(ok, msg):
    global checks
    checks += 1
    if not ok:
        problems.append(msg)

def read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()

# ---------------- data/vacancies.json ----------------
vac_raw = json.loads(read('data/vacancies.json'))
# Accept both shapes: bare array (legacy) or {"asOf": ..., "suites": [...]}.
if isinstance(vac_raw, dict):
    suites = vac_raw.get('suites', [])
    as_of = vac_raw.get('asOf', '')
    check(re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(as_of)) is not None,
          f"vacancies.json: asOf {as_of!r} is not YYYY-MM-DD")
    bsq = vac_raw.get('buildingSqft')
    check(isinstance(bsq, (int, float)) and 1000 <= bsq <= 100000,
          f"vacancies.json: buildingSqft {bsq!r} missing or implausible")
    if isinstance(bsq, (int, float)):
        for s in vac_raw.get('suites', []):
            if isinstance(s.get('sqft'), (int, float)):
                check(s['sqft'] < bsq,
                      f"vacancies.json {s.get('unit')}: sqft {s['sqft']} >= buildingSqft {bsq}")
else:
    suites = vac_raw

check(len(suites) > 0, "vacancies.json: no suites listed")
for s in suites:
    unit = s.get('unit', '<missing>')
    for fld in ('unit', 'building', 'sqft', 'rent', 'cam', 'utilities', 'allIn'):
        check(fld in s, f"vacancies.json {unit}: missing field {fld!r}")
    if all(k in s for k in ('rent', 'cam', 'utilities', 'allIn')):
        total = s['rent'] + s['cam'] + s['utilities']
        check(abs(total - s['allIn']) <= 0.5,
              f"vacancies.json {unit}: rent+cam+utilities = {total:.2f} but allIn = {s['allIn']}")
    check(re.fullmatch(r'[A-Z]\d+', str(unit)) is not None,
          f"vacancies.json {unit}: unit should look like N101")
    check(s.get('building') in ('North', 'South'),
          f"vacancies.json {unit}: building {s.get('building')!r} not North/South")
    check(isinstance(s.get('sqft'), (int, float)) and 50 <= s['sqft'] <= 5000,
          f"vacancies.json {unit}: implausible sqft {s.get('sqft')!r}")

# ---------------- data/tenants.json ----------------
tenants = json.loads(read('data/tenants.json'))
check(isinstance(tenants, list), "tenants.json: top level must be an array")
for t in tenants if isinstance(tenants, list) else []:
    check(bool(t.get('name')), f"tenants.json: entry missing required 'name': {t}")

# ---------------- identity & version stamps (single source: data/identity.json) ----------------
ident = json.loads(read('data/identity.json'))
for fld in ('entity', 'entityLong', 'building', 'buildingAddress', 'noticeAddress',
            'noticeCareOf', 'email', 'version', 'versionDate'):
    check(bool(ident.get(fld)), f"identity.json: missing field {fld!r}")
version, vdate = ident.get('version', ''), ident.get('versionDate', '')
form_version, form_vdate = version, vdate   # single version track since v1.5

build = read('tools/build_lease_docs.py')
check("data/identity.json" in build,
      "build script does not load data/identity.json (identity drift risk)")

lease_page = read('lease/index.html')
check(f"{version}, {vdate}" in lease_page or f"{version.replace('Version ', 'v')} ({vdate})" in lease_page,
      f"lease/index.html: version line does not carry '{version}, {vdate}'")

lease_md = read('lease/lease.md')
check(f"{version}, {vdate}" in lease_md,
      f"lease/lease.md: header does not carry '{version}, {vdate}'")
check(ident['entity'] in lease_md,
      f"lease/lease.md: does not name the entity {ident['entity']!r}")

# The builder's offline fallback identity must match identity.json.
bjs_src = read('js/lease-builder.js')
for key, expect in (('version', version), ('versionDate', vdate),
                    ('entity', ident['entity']), ('noticeAddress', ident['noticeAddress'])):
    m = re.search(rf"{key}:\s*'([^']*)'", bjs_src)
    check(m and m.group(1) == expect,
          f"lease-builder.js fallback {key} ({m.group(1) if m else None!r}) != identity.json ({expect!r})")

# ---------------- download links resolve to real files ----------------
for m in re.finditer(r'href="(/lease/[^"]+\.pdf)"', lease_page):
    rel = m.group(1).lstrip('/')
    check(os.path.exists(os.path.join(ROOT, rel)),
          f"lease/index.html links to {m.group(1)} but the file does not exist")

# ---------------- head assets referenced by index.html exist ----------------
index = read('index.html')
for pat in (r'rel="icon"[^>]*href="(/[^"]+)"',):
    for m in re.finditer(pat, index):
        rel = m.group(1).lstrip('/')
        check(os.path.exists(os.path.join(ROOT, rel)),
              f"index.html references {m.group(1)} but the file does not exist")
m = re.search(r'property="og:image" content="https://(?:eberryvashon|courthousesquarevashon)\.com(/[^"]+)"', index)
if m:
    check(os.path.exists(os.path.join(ROOT, m.group(1).lstrip('/'))),
          f"index.html og:image points at {m.group(1)} but the file does not exist")

# ---------------- shared typefaces ----------------
for f in ('Jost-400.ttf', 'Jost-500.ttf', 'Jost-600.ttf',
          'LibreBaskerville-400.ttf', 'LibreBaskerville-700.ttf', 'LibreBaskerville-Italic.ttf'):
    check(os.path.exists(os.path.join(ROOT, 'fonts', f)),
          f"fonts/{f} missing (required by the PDF build and the Lease Builder)")

# ---------------- lease builder (staff tool) ----------------
if os.path.exists(os.path.join(ROOT, 'lease/builder.html')):
    builder = read('lease/builder.html')
    for m in re.finditer(r'<script src="(/[^"]+)"', builder):
        rel = m.group(1).lstrip('/')
        check(os.path.exists(os.path.join(ROOT, rel)),
              f"builder.html loads {m.group(1)} but the file does not exist")
    check('noindex' in builder, "builder.html: missing robots noindex meta")
    tw = read('tailwind.config.js')
    check('lease/builder.html' in tw,
          "tailwind.config.js content[] does not include lease/builder.html")
    # Additional-terms flow: the checklist textarea, the LOI notes field, and
    # the import mapping between them must all exist together.
    check('f-addl-notes' in builder, "builder.html: missing #f-addl-notes textarea")
    check("'f-addl-notes'" in bjs_src, "lease-builder.js: f-addl-notes not in FIELD_IDS")
    check("loi_notes" in bjs_src, "lease-builder.js: LOI import does not map loi_notes")
    check("'loi_notes'" in build, "build_lease_docs.py: LOI form has no loi_notes field")
    m = re.search(r"CLAUDE_MODEL = '([^']+)'", bjs_src)
    check(m and m.group(1) == 'claude-opus-4-8',
          f"lease-builder.js: CLAUDE_MODEL is {m.group(1) if m else None!r}, expected 'claude-opus-4-8'")

# ---------------- optional: PDF stamps (needs pypdf) ----------------
try:
    from pypdf import PdfReader
    def pdf_text(path):
        return "\n".join((p.extract_text() or "") for p in PdfReader(os.path.join(ROOT, path)).pages)
    if version:
        check(version in pdf_text('lease/lease.pdf'),
              f"lease.pdf does not carry '{version}'")
    if form_version:
        for p in ('lease/lease-terms-sheet.pdf', 'lease/letter-of-intent.pdf'):
            check(form_version in pdf_text(p), f"{p} does not carry '{form_version}'")
        for p in ('lease/lease-terms-sheet.pdf', 'lease/letter-of-intent.pdf'):
            n = len(PdfReader(os.path.join(ROOT, p)).get_fields() or {})
            check(n > 0, f"{p}: no fillable form fields found")
except ImportError:
    print("note: pypdf not installed; skipping PDF content checks")

# =====================================================================
# E. Berry listings site (Phase 1): feed, buildings, cross-checks, build config
# =====================================================================
FEED_KEYS = ('id', 'type', 'title', 'address', 'lat', 'lng', 'rent', 'beds', 'baths',
             'sqft', 'available', 'photos', 'summary', 'features')
OPTIONAL_KEYS = ('buildingId',)
BUILDING_FIELD_COLORS = {'berry', 'tangerine', 'sky', 'mustard', 'sage', 'sand'}
BUILDING_REQUIRED = ('id', 'name', 'shortName', 'address', 'lat', 'lng', 'fieldColor',
                     'tagline', 'description', 'featureBullets', 'gallery', 'leaseUrl',
                     'neighborWall', 'addressMatch')

def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)

# ---------------- data/listings.json ----------------
listings_doc = json.loads(read('data/listings.json'))
check(isinstance(listings_doc, dict) and set(listings_doc) == {'updated', 'listings'},
      "listings.json: envelope must be exactly {updated, listings}")
listings = listings_doc.get('listings', []) if isinstance(listings_doc, dict) else []
check(re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(listings_doc.get('updated', ''))) is not None,
      f"listings.json: updated {listings_doc.get('updated')!r} is not YYYY-MM-DD")
check(isinstance(listings, list) and len(listings) > 0, "listings.json: no listings")

seen_ids = set()
for L in listings:
    lid = L.get('id', '<missing>')
    keys = set(L)
    check(set(FEED_KEYS) <= keys and keys <= set(FEED_KEYS) | set(OPTIONAL_KEYS),
          f"listings.json {lid}: keys must be the 14 feed keys (+ optional buildingId); "
          f"missing={sorted(set(FEED_KEYS) - keys)} extra={sorted(keys - set(FEED_KEYS) - set(OPTIONAL_KEYS))}")
    check(isinstance(lid, str) and re.fullmatch(r'[a-z0-9-]+', lid) is not None,
          f"listings.json {lid}: id must match ^[a-z0-9-]+$")
    check(lid not in seen_ids, f"listings.json {lid}: duplicate id")
    seen_ids.add(lid)
    check(L.get('type') in ('residential', 'commercial'),
          f"listings.json {lid}: type {L.get('type')!r} not residential/commercial")
    check(is_num(L.get('rent')) and L['rent'] > 0,
          f"listings.json {lid}: rent {L.get('rent')!r} must be > 0")
    lat, lng = L.get('lat'), L.get('lng')
    if lat is None or lng is None:
        check(lat is None and lng is None,
              f"listings.json {lid}: lat and lng must both be null or both be numbers")
    else:
        check(isinstance(lat, float) and isinstance(lng, float)
              and 47.2 <= lat <= 47.6 and -122.6 <= lng <= -122.3,
              f"listings.json {lid}: lat/lng ({lat!r}, {lng!r}) not floats within 47.2-47.6 / -122.6--122.3")
    av = L.get('available')
    check(av is None or (isinstance(av, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', av) is not None),
          f"listings.json {lid}: available {av!r} must be null or YYYY-MM-DD")
    photos = L.get('photos')
    check(isinstance(photos, list), f"listings.json {lid}: photos must be an array")
    for ph in photos if isinstance(photos, list) else []:
        check(isinstance(ph, str) and os.path.exists(os.path.join(ROOT, ph.lstrip('/'))),
              f"listings.json {lid}: photo {ph!r} does not exist in the repo")

# ---------------- data/buildings.json ----------------
buildings_doc = json.loads(read('data/buildings.json'))
buildings = buildings_doc.get('buildings', []) if isinstance(buildings_doc, dict) else []
check(isinstance(buildings, list) and len(buildings) > 0, "buildings.json: no buildings")
building_ids = set()
for B in buildings:
    bid = B.get('id', '<missing>')
    building_ids.add(bid)
    for fld in BUILDING_REQUIRED:
        check(fld in B, f"buildings.json {bid}: missing field {fld!r}")
    check(B.get('fieldColor') in BUILDING_FIELD_COLORS,
          f"buildings.json {bid}: fieldColor {B.get('fieldColor')!r} not in {sorted(BUILDING_FIELD_COLORS)}")
for L in listings:
    if 'buildingId' in L:
        check(L['buildingId'] in building_ids,
              f"listings.json {L.get('id')}: buildingId {L['buildingId']!r} not found in buildings.json")

# ---------------- cross-check: vacancies.json <-> listings.json ----------------
listing_by_id = {L.get('id'): L for L in listings}
suite_ids = set()
for s in suites:
    lid = 'chs-' + str(s.get('unit', '')).lower()
    suite_ids.add(lid)
    L = listing_by_id.get(lid)
    check(L is not None, f"listings.json: no listing {lid!r} for vacancies.json suite {s.get('unit')}")
    if L is not None:
        check(L.get('sqft') == s.get('sqft'),
              f"listings.json {lid}: sqft {L.get('sqft')!r} != vacancies.json {s.get('sqft')!r}")
        check(is_num(L.get('rent')) and is_num(s.get('allIn')) and abs(L['rent'] - s['allIn']) <= 0.01,
              f"listings.json {lid}: rent {L.get('rent')!r} != vacancies.json allIn {s.get('allIn')!r}")
for lid in listing_by_id:
    if isinstance(lid, str) and lid.startswith('chs-'):
        check(lid in suite_ids, f"listings.json {lid}: no matching suite in vacancies.json")

# ---------------- tailwind content globs for the listings pages ----------------
tw_cfg = read('tailwind.config.js')
for glob_ in ('./listings/**/*.html', './js/listings.js'):
    check(glob_ in tw_cfg, f"tailwind.config.js content[] does not include {glob_}")

# =====================================================================
# E. Berry homepage (Phase 2): social card, firm-ID line, inquiry form, flat brand
# =====================================================================
og_path = os.path.join(ROOT, 'images/og-card-eberry.png')
check(os.path.exists(og_path), "images/og-card-eberry.png is missing (homepage og:image)")
if os.path.exists(og_path):
    check(os.path.getsize(og_path) <= 300 * 1024,
          f"images/og-card-eberry.png is {os.path.getsize(og_path)} bytes; keep it under 300KB")
check(re.search(r'property="og:image" content="https://eberryvashon\.com/images/og-card-eberry\.png"', index) is not None,
      "index.html: og:image must be https://eberryvashon.com/images/og-card-eberry.png")
# Washington firm-identification rule: the co-brand line must be on the page.
check('A PART OF WINDERMERE VASHON' in index,
      "index.html: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
check('name="inquiry"' in index, 'index.html: Netlify form name="inquiry" is missing')
check('id="inquire"' in index, 'index.html: id="inquire" anchor is missing (lease pages deep-link to /#inquire)')
# Flat brand: no gradients, shadows, pure white or pure black on the homepage.
for label, pat in (('gradient', r'gradient'), ('shadow', r'shadow'),
                   ('pure white', r'#fff\b|#ffffff\b|\bbg-white\b|\btext-white\b'),
                   ('pure black', r'#000\b|#000000\b|\bbg-black\b|\btext-black\b')):
    check(re.search(pat, index, re.I) is None, f"index.html: contains {label} (E. Berry brand is flat, Berry/Cream only)")
robots = read('robots.txt')
check('Sitemap: https://eberryvashon.com/sitemap.xml' in robots,
      "robots.txt: Sitemap line must point at https://eberryvashon.com/sitemap.xml")

# =====================================================================
# E. Berry building pages (Phase 3): generated pages, sitemap, wall script
#   The pages are written by tools/build_pages.py. These checks assert what must be true of the committed
#   output; `python3 tools/build_pages.py --check` (separate CI step) proves it is not stale.
# =====================================================================
SITE_URL = 'https://eberryvashon.com'
RERUN = "run `python3 tools/build_pages.py` and commit the result"

for rel in ('tools/build_pages.py', 'tools/templates/building.tmpl.html', 'tools/templates/building.parts.tmpl.html',
            'js/building.js'):
    check(os.path.exists(os.path.join(ROOT, rel)), f"{rel} is missing")
for glob_ in ('./buildings/**/*.html', './js/building.js', './tools/templates/*.html'):
    check(glob_ in tw_cfg, f"tailwind.config.js content[] does not include {glob_}")

def shell_block(text, name, end=None):
    """A canonical shell block from index.html or a generated page, or None."""
    end = end or rf'<!-- /EB:{name} -->'
    m = re.search(rf'<!-- EB:{name}[^>]*-->.*?{end}', text, re.S)
    return m.group(0) if m else None

FLAT_BRAND = (('gradient', r'gradient'), ('shadow', r'shadow'),
              ('pure white', r'#fff\b|#ffffff\b|\bbg-white\b|\btext-white\b'),
              ('pure black', r'#000\b|#000000\b|\bbg-black\b|\btext-black\b'))

wall_js = read('js/building.js') if os.path.exists(os.path.join(ROOT, 'js/building.js')) else ''
for label, pat in FLAT_BRAND:
    check(re.search(pat, wall_js, re.I) is None, f"js/building.js: contains {label} (E. Berry brand is flat)")
for token in ('LISTINGS_URL', '/data/tenants.json', 'dataset.building', 'dataset.addressMatch'):
    check(token in wall_js, f"js/building.js: must read {token} (neighbor wall inputs)")

# The "Download the PDFs" link lands on this id in the (frozen) lease page; there is no #downloads anchor.
check('id="lease-pdf-link"' in lease_page,
      'lease/index.html: id="lease-pdf-link" is gone (the building pages\' "Download the PDFs" link targets it)')

for B in buildings:
    bid = B.get('id', '<missing>')
    rel = f'buildings/{bid}/index.html'
    path = os.path.join(ROOT, rel)
    check(os.path.exists(path), f"{rel}: not generated for buildings.json entry {bid!r} ({RERUN})")
    if not os.path.exists(path):
        continue
    page = read(rel)
    check('A PART OF WINDERMERE VASHON' in page, f"{rel}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    for anchor in ('id="location"', 'id="inquire"', 'name="inquiry"'):
        check(anchor in page, f"{rel}: missing {anchor}")
    if B.get('neighborWall'):
        check('id="suites"' in page and 'id="neighbor-wall"' in page,
              f"{rel}: neighborWall is true but the page has no id=\"suites\" / id=\"neighbor-wall\"")
    check(f'data-building="{bid}"' in page, f'{rel}: <body> is missing data-building="{bid}"')
    check(f'name="building" value="{bid}"' in page, f'{rel}: inquiry form is missing the hidden building field')
    check(f'<link rel="canonical" href="{SITE_URL}/buildings/{bid}/" />' in page, f"{rel}: canonical URL is not {SITE_URL}/buildings/{bid}/")
    check(f"<title>{B.get('name', '')} — E. Berry Property Management</title>" in page,
          f"{rel}: <title> is not '{B.get('name')} — E. Berry Property Management'")
    check('src="/js/building.js"' in page and 'src="/js/site-config.js"' in page,
          f"{rel}: must load /js/site-config.js and /js/building.js")
    # Social image: absolute URL, and the file behind it exists.
    m = re.search(r'property="og:image" content="https://eberryvashon\.com(/[^"]+)"', page)
    check(m is not None, f"{rel}: og:image must be an absolute https://eberryvashon.com/... URL")
    if m:
        check(os.path.exists(os.path.join(ROOT, m.group(1).lstrip('/'))),
              f"{rel}: og:image points at {m.group(1)} but the file does not exist")
    # Structured data parses and carries the postal address.
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    try:
        ld = json.loads(m.group(1)) if m else None
    except ValueError:
        ld = None
    check(isinstance(ld, dict) and ld.get('@type') == 'LocalBusiness'
          and ld.get('address', {}).get('streetAddress') == str(B.get('address', '')).split(',')[0]
          and ld.get('geo', {}).get('latitude') == B.get('lat') and ld.get('geo', {}).get('longitude') == B.get('lng'),
          f"{rel}: JSON-LD is missing/invalid or its address/geo do not match buildings.json")
    # The shell must be the homepage's, byte for byte (header, footer, shell styles).
    for name, end in (('HEADER', None), ('FOOTER', None), ('SHELL-STYLES', r'</style>')):
        a, b = shell_block(index, name, end), shell_block(page, name, end)
        check(a is not None and a == b, f"{rel}: EB:{name} block differs from index.html ({RERUN})")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, page, re.I) is None, f"{rel}: contains {label} (E. Berry brand is flat, Berry/Cream only)")

# ---------------- sitemap.xml ----------------
import xml.etree.ElementTree as ET
try:
    sm = ET.fromstring(read('sitemap.xml'))
    SM = '{http://www.sitemaps.org/schemas/sitemap/0.9}'
    sm_entries = sm.findall(f'{SM}url')
    sm_urls = {u.findtext(f'{SM}loc'): u.findtext(f'{SM}lastmod') for u in sm_entries if u.findtext(f'{SM}loc')}
except (ET.ParseError, OSError):
    sm_entries, sm_urls = [], None
check(sm_urls is not None, "sitemap.xml: missing or not valid XML")
if sm_urls is not None:
    check(len(sm_urls) == len(sm_entries), "sitemap.xml: a <url> entry has no <loc> or a URL is listed twice")
    wanted = [f'{SITE_URL}/', f'{SITE_URL}/listings/']
    wanted += [f"{SITE_URL}/listings/{L.get('id')}/" for L in listings]
    wanted += [f"{SITE_URL}/buildings/{B.get('id')}/" for B in buildings]
    for u in wanted:
        check(u in sm_urls, f"sitemap.xml: missing {u} ({RERUN})")
        check(sm_urls.get(u) == listings_doc.get('updated'),
              f"sitemap.xml: {u} lastmod {sm_urls.get(u)!r} != listings.json updated {listings_doc.get('updated')!r}")
    check(all(u.startswith(SITE_URL + '/') for u in sm_urls), "sitemap.xml: every URL must be on https://eberryvashon.com")

# ---------------- verdict ----------------
if problems:
    print(f"FAIL: {len(problems)} problem(s) out of {checks} checks")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print(f"OK: {checks} checks passed")
print("note: generated pages are verified separately; run `python3 tools/build_pages.py --check` (also a CI step) to prove buildings/ and sitemap.xml are not stale")
