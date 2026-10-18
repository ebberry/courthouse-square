#!/usr/bin/env python3
"""Sanity checks for the Courthouse Square site and the E. Berry site (including the Phase 8 owners section, the
Phase 9 technology page and Courthouse Square de-emphasis, and the Phase 13 legal pages, EHO mark and footer legal row).

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

def check_shell(rel, page, fix):
    """The page's EB:HEADER, EB:FOOTER and EB:SHELL-STYLES blocks must equal index.html's, byte for byte."""
    for name, end in (('HEADER', None), ('FOOTER', None), ('SHELL-STYLES', r'</style>')):
        a, b = shell_block(index, name, end), shell_block(page, name, end)
        check(a is not None and a == b, f"{rel}: EB:{name} block differs from index.html ({fix})")

FLAT_BRAND = (('gradient', r'gradient'), ('shadow', r'shadow'),
              ('pure white', r'#fff\b|#ffffff\b|\bbg-white\b|\btext-white\b'),
              ('pure black', r'#000\b|#000000\b|\bbg-black\b|\btext-black\b'))

# The only images the owners and technology pages may show: the E. Berry brand marks, and the one Windermere co-brand
# logo (images/brand/windermere-vashon-island.png, Phase 10). Nothing else: no screenshots, no stock photos.
WM_LOGO = '/images/brand/windermere-vashon-island.png'
WM_ALT = 'Windermere Real Estate, Vashon Island'
EB_BRAND_SVGS = tuple(f'/images/brand/{n}.svg' for n in ('wordmark-berry', 'wordmark-cream', 'wordmark-tangerine', 'monogram-tangerine-bare',
                                                         'monogram-tangerine-badge', 'lockup-friend-to-vashon'))
BRAND_IMAGES = frozenset(EB_BRAND_SVGS) | {WM_LOGO}

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
    check_shell(rel, page, RERUN)
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
    wanted = [f'{SITE_URL}/', f'{SITE_URL}/listings/', f'{SITE_URL}/owners/', f'{SITE_URL}/technology/',
              f'{SITE_URL}/fair-housing/', f'{SITE_URL}/privacy/', f'{SITE_URL}/accessibility/']
    wanted += [f"{SITE_URL}/listings/{L.get('id')}/" for L in listings]
    wanted += [f"{SITE_URL}/buildings/{B.get('id')}/" for B in buildings]
    for u in wanted:
        check(u in sm_urls, f"sitemap.xml: missing {u} ({RERUN})")
        check(sm_urls.get(u) == listings_doc.get('updated'),
              f"sitemap.xml: {u} lastmod {sm_urls.get(u)!r} != listings.json updated {listings_doc.get('updated')!r}")
    check(all(u.startswith(SITE_URL + '/') for u in sm_urls), "sitemap.xml: every URL must be on https://eberryvashon.com")

# =====================================================================
# E. Berry listings index (Phase 4): /listings/, the filter bar, and the brand MapLibre map (Phase 7a: self-hosted PMTiles basemap)
#   listings/index.html is hand-maintained (not generated): its shell is copied from index.html, and the
#   byte-identity check below is what tells you to copy it again when the shell changes.
# =====================================================================
LIST_REL = 'listings/index.html'
MAPLIBRE_VERSION = '5.24.0'
PMTILES_VERSION = '4.4.1'

def exists(rel):
    return os.path.exists(os.path.join(ROOT, rel))

for rel in (LIST_REL, 'js/listings.js', 'js/eb-map.js', 'css/eb-map.css',
            'js/vendor/maplibre-gl.js', 'js/vendor/maplibre-gl-LICENSE.md', 'css/vendor/maplibre-gl.css',
            'js/vendor/pmtiles.js', 'js/vendor/pmtiles-LICENSE.md',
            'map/style.json', 'map/vashon.pmtiles', 'map/README.md',
            'tools/extract_pmtiles.py', 'tools/make_fixture_pmtiles.py', 'tools/test_extract_pmtiles.py',
            'tools/test_listings.py', '.github/workflows/listings-e2e.yml'):
    check(exists(rel), f"{rel} is missing")

# Leaflet is gone, root and branch.
for rel in ('js/vendor/leaflet.js', 'js/vendor/leaflet-LICENSE.md', 'css/vendor/leaflet.css', 'css/vendor/images'):
    check(not exists(rel), f"{rel} is the old Leaflet map and must be deleted")

# Vendored MapLibre GL and PMTiles: exact version, its license, and nothing else at the end of the stylesheet's reach.
if exists('js/vendor/maplibre-gl.js'):
    ml_js = read('js/vendor/maplibre-gl.js')
    check(f'/blob/v{MAPLIBRE_VERSION}/LICENSE.txt' in ml_js[:400] and 'MapLibre GL JS' in ml_js[:400],
          f"js/vendor/maplibre-gl.js is not MapLibre GL JS {MAPLIBRE_VERSION}")
if exists('js/vendor/maplibre-gl-LICENSE.md'):
    lic = read('js/vendor/maplibre-gl-LICENSE.md')
    check(lic.splitlines()[0] == f'# MapLibre GL JS {MAPLIBRE_VERSION}' and 'BSD-3-Clause' in lic and 'MapLibre contributors' in lic,
          "js/vendor/maplibre-gl-LICENSE.md: header must name the exact version and carry the BSD-3-Clause text")
if exists('css/vendor/maplibre-gl.css'):
    ml_css = read('css/vendor/maplibre-gl.css')
    check('.maplibregl-map' in ml_css and '.maplibregl-popup' in ml_css, "css/vendor/maplibre-gl.css is not the MapLibre GL stylesheet")
    check(re.search(r'url\((?!["\']?data:)', ml_css) is None, "css/vendor/maplibre-gl.css points at a file; the stock stylesheet inlines every image")
if exists('js/vendor/pmtiles.js'):
    pm_js = read('js/vendor/pmtiles.js')
    check(pm_js.startswith('"use strict";var pmtiles=(()=>{') and 'getZxy' in pm_js and 'Protocol' in pm_js,
          "js/vendor/pmtiles.js is not the PMTiles IIFE build (it must define the `pmtiles` global with Protocol)")
if exists('js/vendor/pmtiles-LICENSE.md'):
    lic = read('js/vendor/pmtiles-LICENSE.md')
    check(lic.splitlines()[0] == f'# PMTiles (JavaScript) {PMTILES_VERSION}' and 'BSD 3-Clause' in lic and 'pmtiles@' + PMTILES_VERSION in lic,
          "js/vendor/pmtiles-LICENSE.md: header must name the exact version and carry the BSD-3-Clause text")

# The brand map wrapper and its skin.
if exists('js/eb-map.js'):
    ebmap = read('js/eb-map.js')
    for token in ("'/map/style.json'", 'MIN_ZOOM = 11, MAX_ZOOM = 15.5', 'maxBounds: ISLAND_BOUNDS', '[[-122.62, 47.28], [-122.30, 47.57]]',
                  'dragRotate: false', 'pitchWithRotate: false', 'touchPitch: false', 'maxPitch: 0', 'disableRotation()', 'renderWorldCopies: false',
                  'customAttribution: ATTRIBUTION', 'https://www.openstreetmap.org/copyright', 'https://protomaps.com', 'compact: false',
                  'pmtiles.Protocol', 'addProtocol', 'map.scrollZoom.disable()', "setAttribute('role', 'region')", "setAttribute('aria-label'",
                  'new gl.Marker', 'new gl.Popup', 'eb-pin--muted', 'eb-map-label', 'PLACE_LABELS', 'window.EBMap', 'groupPoints', 'supported',
                  'fmtMoney', "'/listings/'", 'popups', 'map.ebSetPoints', 'map.ebFit'):
        check(token in ebmap, f"js/eb-map.js: expected {token!r}")
    for name in ('Vashon', 'Burton', 'Dockton', 'Maury Island', 'Vashon Heights ferry', 'Tahlequah ferry'):
        check(f"name: '{name}'" in ebmap, f"js/eb-map.js: the place-name overlay is missing {name!r}")
    check('tile.openstreetmap.org' not in ebmap and 'leaflet' not in ebmap.lower(),
          "js/eb-map.js: remote tiles and Leaflet are gone; the basemap is map/vashon.pmtiles")
    hosts_in_js = set(re.findall(r'https?://([^/\'"\s)<]+)', ebmap))
    check(hosts_in_js <= {'www.openstreetmap.org', 'protomaps.com'}, f"js/eb-map.js: unexpected hosts {sorted(hosts_in_js)}; only the attribution links may leave the site")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, ebmap, re.I) is None, f"js/eb-map.js: contains {label} (E. Berry brand is flat)")
if exists('css/eb-map.css'):
    mapcss = read('css/eb-map.css')
    for token in ('.maplibregl-popup-content', '.maplibregl-popup-tip', '.maplibregl-ctrl-attrib', '.maplibregl-ctrl-group', '.eb-pin--muted', '.eb-map-label',
                  'border-radius: 24px', 'border: 1.5px solid'):
        check(token in mapcss, f"css/eb-map.css: expected {token!r}")
    check('leaflet' not in mapcss.lower() and 'sepia' not in mapcss and 'filter:' not in mapcss, "css/eb-map.css: no Leaflet selectors and no filters on the map (the basemap is already in brand colors)")
    check(re.search(r'gradient|#fff\b|#ffffff\b|#000\b|#000000\b|(?<![-\w])(?:white|black)(?![-\w])', mapcss, re.I) is None,
          "css/eb-map.css: contains a gradient, pure white or pure black (E. Berry brand is flat)")
    shadows = re.findall(r'(?:box|text|drop)-shadow\s*:\s*([^;}]+)', mapcss)
    check(all(v.strip() == 'none' for v in shadows),
          f"css/eb-map.css: the only shadow value allowed is none (found {[v for v in shadows if v.strip() != 'none']})")

# ---- the basemap: map/style.json and map/vashon.pmtiles ----
BRAND = {'#670A2F', '#F1ECE9', '#F36E30', '#E8C450', '#8DC8E8', '#98B286', '#F1DDB7'}            # the style guide's palette
MAP_TINTS = {'#A7C8D8', '#CBD5BE', '#DCCFC8'}                                                    # water, greenspace, minor roads: tints of Sky, Sage and Berry-on-Cream
MAP_COLORS = BRAND | MAP_TINTS
PROTOMAPS_LAYERS = {'earth', 'landuse', 'landcover', 'water', 'roads', 'buildings', 'boundaries'}     # source layers of @protomaps/basemaps 5.x that map/style.json may read
STYLE_REL, ARCHIVE_REL = 'map/style.json', 'map/vashon.pmtiles'
placeholder_note = None
if exists(STYLE_REL):
    style_text = read(STYLE_REL)
    try:
        style = json.loads(style_text)
    except ValueError as e:
        style = None
        check(False, f"{STYLE_REL} is not valid JSON ({e})")
    if isinstance(style, dict):
        check(style.get('version') == 8, f"{STYLE_REL}: version must be 8")
        check('glyphs' not in style and 'sprite' not in style and '"glyphs"' not in style_text and '"sprite"' not in style_text and 'text-field' not in style_text,
              f"{STYLE_REL}: no glyphs, no sprite, no text-field (there are no font or icon files; place names are HTML labels in js/eb-map.js)")
        src = style.get('sources', {})
        check(list(src) == ['vashon'] and src['vashon'].get('type') == 'vector' and src['vashon'].get('url') == 'pmtiles:///map/vashon.pmtiles',
              f"{STYLE_REL}: the only source must be `vashon`, a vector source with url pmtiles:///map/vashon.pmtiles")
        layers = style.get('layers', [])
        ids = [l.get('id') for l in layers]
        check(len(ids) == len(set(ids)) and len(ids) >= 8, f"{STYLE_REL}: layer ids must be unique ({len(ids)} layers)")
        for l in layers:
            lid = l.get('id')
            check(l.get('type') in ('background', 'fill', 'line'), f"{STYLE_REL} {lid}: type {l.get('type')!r}; only background, fill and line (no symbol, raster, hillshade)")
            if l.get('type') != 'background':
                check(l.get('source') == 'vashon' and l.get('source-layer') in PROTOMAPS_LAYERS,
                      f"{STYLE_REL} {lid}: must read source `vashon` and a Protomaps source-layer {sorted(PROTOMAPS_LAYERS)} (got {l.get('source-layer')!r})")
            check(not any(k.startswith('text-') or k.startswith('icon-') for k in list(l.get('layout', {})) + list(l.get('paint', {}))), f"{STYLE_REL} {lid}: text and icon properties need glyphs and sprites")
        colors = set(c.upper() for c in re.findall(r'#[0-9A-Fa-f]{6}\b', style_text))
        check(colors <= MAP_COLORS, f"{STYLE_REL}: colors outside the brand palette: {sorted(colors - MAP_COLORS)}")
        check(re.search(r'rgba?\(|hsla?\(|#[0-9A-Fa-f]{3}\b|#[0-9A-Fa-f]{8}\b', style_text) is None, f"{STYLE_REL}: write colors as #RRGGBB palette values")
        for label, pat in FLAT_BRAND:
            check(re.search(pat, style_text, re.I) is None, f"{STYLE_REL}: contains {label} (E. Berry brand is flat)")
        by_id = {l.get('id'): l for l in layers}
        paint = lambda i, k: (by_id.get(i, {}).get('paint') or {}).get(k)
        check(paint('background', 'background-color') == '#F1ECE9' and paint('earth', 'fill-color') == '#F1ECE9', f"{STYLE_REL}: the background and the land are Cream")
        check(paint('water', 'fill-color') == '#A7C8D8', f"{STYLE_REL}: water is #A7C8D8")
        check(paint('landuse_park', 'fill-color') == '#CBD5BE' and paint('landuse_beach', 'fill-color') == '#F1DDB7', f"{STYLE_REL}: parks are #CBD5BE and beaches are Sand")
        check(paint('roads_minor', 'line-color') == '#DCCFC8' and paint('roads_major', 'line-color') == '#670A2F' and paint('roads_highway', 'line-color') == '#670A2F',
              f"{STYLE_REL}: minor roads are #DCCFC8 and major roads and highways are Berry")
        check(paint('roads_ferry', 'line-color') == '#670A2F' and paint('roads_ferry', 'line-opacity') == 0.4 and bool(paint('roads_ferry', 'line-dasharray')),
              f"{STYLE_REL}: ferry routes are dashed Berry at 40% opacity")
        check(not any(l.get('layout', {}).get('line-cap') == 'butt' for l in layers) and all('line-gap-width' not in (l.get('paint') or {}) for l in layers),
              f"{STYLE_REL}: flat roads: no casings")

# The archive: the PMTiles v3 magic, a header that matches the file, and a note while it is still the placeholder.
if exists(ARCHIVE_REL):
    import gzip as _gzip, struct as _struct
    with open(os.path.join(ROOT, ARCHIVE_REL), 'rb') as f:
        blob = f.read(16384)
    size = os.path.getsize(os.path.join(ROOT, ARCHIVE_REL))
    check(blob[:7] == b'PMTiles' and blob[7:8] == b'\x03', f"{ARCHIVE_REL}: does not start with the PMTiles v3 magic bytes (PMTiles + 0x03)")
    if len(blob) >= 127 and blob[:7] == b'PMTiles':
        u64 = lambda o: int.from_bytes(blob[o:o + 8], 'little')
        i32 = lambda o: int.from_bytes(blob[o:o + 4], 'little', signed=True)
        root_off, root_len, meta_off, meta_len, tile_off, tile_len = u64(8), u64(16), u64(24), u64(32), u64(56), u64(64)
        check(root_off + root_len <= 16384 and size >= tile_off + tile_len > 0, f"{ARCHIVE_REL}: header does not match the file (truncated or damaged?)")
        check(blob[99] == 1 and blob[98] in (1, 2) and blob[97] in (1, 2), f"{ARCHIVE_REL}: expected vector tiles (MVT) with none/gzip compression")
        check(blob[100] <= 11 and blob[101] >= 11, f"{ARCHIVE_REL}: zoom range z{blob[100]}..z{blob[101]} must cover the map's minimum zoom 11")
        check(i32(102) <= -1226200000 and i32(106) <= 472800000 and i32(110) >= -1223000000 and i32(114) >= 475700000,
              f"{ARCHIVE_REL}: header bounds do not cover the island box -122.62,47.28,-122.30,47.57")
        try:
            meta_blob = open(os.path.join(ROOT, ARCHIVE_REL), 'rb').read()[meta_off:meta_off + meta_len]
            meta = json.loads(_gzip.decompress(meta_blob) if blob[97] == 2 else meta_blob)
            if (meta.get('eberry') or {}).get('placeholder') is True:
                placeholder_note = f"{ARCHIVE_REL} is the PLACEHOLDER; replace it with the real extract (python3 tools/extract_pmtiles.py, see map/README.md)"
        except (OSError, ValueError):
            check(False, f"{ARCHIVE_REL}: metadata is unreadable")
if exists('map/README.md'):
    mr = read('map/README.md')
    check('placeholder' in mr.lower() and 'tools/extract_pmtiles.py' in mr and 'tools/make_fixture_pmtiles.py' in mr and 'build.protomaps.com' in mr,
          "map/README.md: must explain the placeholder and give the extract command")

# The listings script.
if exists('js/listings.js'):
    ljs = read('js/listings.js')
    for token in ('LISTINGS_URL', 'history.replaceState', 'URLSearchParams', "'residential'", "'commercial'", 'aria-pressed',
                  'hasCoords', 'IntersectionObserver', 'data-clear', '/#inquire', 'listing-card-link'):
        check(token in ljs, f"js/listings.js: expected {token!r}")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, ljs, re.I) is None, f"js/listings.js: contains {label} (E. Berry brand is flat)")

# The page.
if exists(LIST_REL):
    lp = read(LIST_REL)
    check('A PART OF WINDERMERE VASHON' in lp, f"{LIST_REL}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    check_shell(LIST_REL, lp, "copy the EB:HEADER / EB:FOOTER / EB:SHELL-STYLES blocks from index.html")
    check("<title>What's open — E. Berry Property Management</title>" in lp, f"{LIST_REL}: <title> is not \"What's open — E. Berry Property Management\"")
    check(f'<link rel="canonical" href="{SITE_URL}/listings/" />' in lp, f"{LIST_REL}: canonical URL is not {SITE_URL}/listings/")
    check('name="description"' in lp and 'property="og:title"' in lp and f'property="og:url" content="{SITE_URL}/listings/"' in lp,
          f"{LIST_REL}: missing meta description or Open Graph tags")
    m = re.search(r'property="og:image" content="https://eberryvashon\.com(/[^"]+)"', lp)
    check(m is not None and exists(m.group(1).lstrip('/')), f"{LIST_REL}: og:image must be an absolute eberryvashon.com URL of a file that exists")
    check('application/ld+json' not in lp, f"{LIST_REL}: no JSON-LD here (listing detail pages carry it)")
    check(len(re.findall(r'<h1[ >]', lp)) == 1 and "What's open on Vashon" in lp, f"{LIST_REL}: needs exactly one h1, \"What's open on Vashon\"")
    # Everything local except Google Fonts: the map, its tiles and its libraries are all ours.
    check(re.search(r'cdn', lp, re.I) is None and 'leaflet' not in lp.lower(), f"{LIST_REL}: mentions a CDN or Leaflet; vendor it instead")
    hosts = set()
    for tag in re.findall(r'<(?:script|link)\b[^>]*>', lp):
        mh = re.search(r'\b(?:src|href)="https?://([^/"]+)', tag)
        if mh and 'rel="canonical"' not in tag:
            hosts.add(mh.group(1))
    check(hosts <= {'fonts.googleapis.com', 'fonts.gstatic.com'}, f"{LIST_REL}: external script/stylesheet hosts {sorted(hosts)}; only Google Fonts allowed")
    # Load order: MapLibre and PMTiles before the wrapper before the page script; MapLibre's CSS before the skin.
    order = [lp.find(f'src="{u}"') for u in ('/js/vendor/maplibre-gl.js', '/js/vendor/pmtiles.js', '/js/eb-map.js', '/js/site-config.js', '/js/listings.js')]
    check(all(i >= 0 for i in order) and order == sorted(order),
          f"{LIST_REL}: scripts must load maplibre-gl.js, pmtiles.js, eb-map.js, site-config.js, listings.js in that order")
    css_order = [lp.find(f'href="{u}"') for u in ('/css/tailwind.css', '/css/vendor/maplibre-gl.css', '/css/eb-map.css')]
    check(all(i >= 0 for i in css_order) and css_order == sorted(css_order),
          f"{LIST_REL}: stylesheets must load tailwind.css, vendor/maplibre-gl.css, eb-map.css in that order")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, lp, re.I) is None, f"{LIST_REL}: contains {label} (E. Berry brand is flat, Berry/Cream only)")
    # The controls the script and the test drive.
    for anchor in ('id="filter-bar"', 'id="type-group"', 'id="f-beds"', 'id="f-price"', 'id="f-sqft"', 'id="clear-filters"',
                   'id="result-count"', 'id="split"', 'id="listing-grid"', 'id="empty-state"', 'id="map-pane"', 'id="map"',
                   'id="mobile-toggle"', 'data-type="all"', 'data-type="residential"', 'data-type="commercial"'):
        check(anchor in lp, f"{LIST_REL}: missing {anchor}")
    for sel_id, values in (('f-beds', ['', '1', '2', '3']), ('f-price', ['', '750', '1000', '1500', '2000', '3000']),
                           ('f-sqft', ['', '150', '300', '600', '1000'])):
        m = re.search(rf'<select id="{sel_id}".*?</select>', lp, re.S)
        got = re.findall(r'<option value="([^"]*)"', m.group(0)) if m else None
        check(got == values, f"{LIST_REL}: #{sel_id} options are {got}, expected {values}")
    check('class="eb-btn ' in lp and 'id="mobile-toggle"' in lp, f"{LIST_REL}: the Map/List pill must be an .eb-btn (>=19px bold)")
    # <noscript>: a plain link to every listing and to the building.
    noscript_text = ' '.join(re.findall(r'<noscript>(.*?)</noscript>', lp, re.S))
    for L in listings:
        check(f'href="/listings/{L.get("id")}/"' in noscript_text, f"{LIST_REL}: <noscript> has no link to /listings/{L.get('id')}/")
    check('href="/buildings/courthouse-square/"' in noscript_text, f"{LIST_REL}: <noscript> has no link to /buildings/courthouse-square/")
    # The homepage and header deep-link here; both filters must be understood.
    for q in ('/listings/?type=residential', '/listings/?type=commercial'):
        check(f'href="{q}"' in index and f'href="{q}"' in lp, f"{q} must be linked from the homepage and from the listings header")
    # css/tailwind.css must have been rebuilt for the classes this page and script use.
    tw_css = read('css/tailwind.css')
    for cls in ('line-clamp-2', r'aria-pressed\:bg-eb-mustard', r'lg\:col-span-3', r'lg\:col-span-2', r'lg\:grid-cols-5', r'disabled\:opacity-50'):
        check(cls in tw_css, f"css/tailwind.css has no .{cls}; rebuild it (see README, 'Rebuilding the stylesheet')")

if exists('.github/workflows/listings-e2e.yml'):
    wf = read('.github/workflows/listings-e2e.yml')
    for token in ("'listings/**'", "'js/listings.js'", "'js/eb-map.js'", "'js/vendor/maplibre-gl.js'", "'js/vendor/pmtiles.js'", "'map/**'", "'data/listings.json'",
                  "'tools/test_listings.py'", 'python3 tools/test_listings.py'):
        check(token in wf, f".github/workflows/listings-e2e.yml: expected {token}")

# =====================================================================
# E. Berry listing detail pages (Phase 5): generated /listings/<id>/ pages, the /listing.html fallback, the rewrite
#   The pages are written by tools/build_pages.py (listing.tmpl.html); `python3 tools/build_pages.py --check`
#   (separate CI step) proves they are not stale. These checks assert what must be true of the committed output.
# =====================================================================
import html as _html

def money_fmt(n):
    return f'${n:,.0f}'

LISTING_PAGE_FILES = ('tools/templates/listing.tmpl.html', 'tools/templates/listing.parts.tmpl.html',
                      'tools/templates/listing-fallback.tmpl.html', 'js/listing-detail.js', 'listing.html')
for rel in LISTING_PAGE_FILES:
    check(exists(rel), f"{rel} is missing")
for glob_ in ('./listings/**/*.html', './listing.html', './js/listing-detail.js'):
    check(glob_ in tw_cfg, f"tailwind.config.js content[] does not include {glob_}")

# The set of generated pages is exactly the set of listings: none missing, none left over from a removed listing.
listing_ids = {str(L.get('id')) for L in listings}
folders = sorted(d for d in os.listdir(os.path.join(ROOT, 'listings')) if os.path.isdir(os.path.join(ROOT, 'listings', d)))
with_page = {d for d in folders if exists(f'listings/{d}/index.html')}
for lid in sorted(listing_ids - with_page):
    check(False, f"listings/{lid}/index.html: not generated for listings.json entry {lid!r} ({RERUN})")
for d in sorted(with_page - listing_ids):
    check(False, f"listings/{d}/index.html: orphan, no listing {d!r} in listings.json (delete the folder, or restore the listing)")
for d in sorted(set(folders) - with_page):
    check(False, f"listings/{d}/: folder has no index.html (every folder under listings/ is a listing slug)")
check(listing_ids == with_page, "listings/<id>/ pages do not match listings.json ids exactly")

MAP_SCRIPTS = ('/js/vendor/maplibre-gl.js', '/js/vendor/pmtiles.js', '/js/eb-map.js')
for L in listings:
    lid = str(L.get('id'))
    rel = f'listings/{lid}/index.html'
    if not exists(rel):
        continue
    page = read(rel)
    canonical = f'{SITE_URL}/listings/{lid}/'
    rent = L.get('rent')
    title = f"{L.get('title')} — {money_fmt(rent)}/mo on Vashon — E. Berry Property Management"
    check('A PART OF WINDERMERE VASHON' in page, f"{rel}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    check_shell(rel, page, RERUN)
    check(f'<title>{_html.escape(title, quote=True)}</title>' in page, f"{rel}: <title> is not {title!r}")
    check(f'<link rel="canonical" href="{canonical}" />' in page, f"{rel}: canonical URL is not {canonical}")
    check('name="description"' in page and f'property="og:url" content="{canonical}"' in page and 'property="og:title"' in page
          and 'name="twitter:card"' in page, f"{rel}: missing meta description or Open Graph / Twitter tags")
    m = re.search(r'property="og:image" content="https://eberryvashon\.com(/[^"]+)"', page)
    check(m is not None and exists(m.group(1).lstrip('/')), f"{rel}: og:image must be an absolute eberryvashon.com URL of a file that exists")
    check('name="robots"' not in page, f"{rel}: generated listing pages are indexable (no robots meta)")
    check(len(re.findall(r'<h1[ >]', page)) == 1 and 'id="listing-title"' in page, f"{rel}: needs exactly one h1 (id=listing-title)")
    check(f'data-listing="{lid}"' in page, f'{rel}: <body> is missing data-listing="{lid}"')
    # The rent is the page's one huge figure.
    check(re.search(r'id="listing-rent"[^>]*>\s*<span[^>]*>' + re.escape(money_fmt(rent)) + r'</span>', page) is not None,
          f"{rel}: #listing-rent does not show {money_fmt(rent)}")
    # Structured data parses and says the right things.
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    try:
        ld = json.loads(m.group(1)) if m else None
    except ValueError:
        ld = None
    ok = isinstance(ld, dict) and ld.get('@type') == 'RealEstateListing' and '"RealEstateListing"' in page
    ok = ok and ld.get('url') == canonical and ld.get('name') == L.get('title') and ld.get('datePosted') == listings_doc.get('updated')
    offers = ld.get('offers', {}) if ok else {}
    ok = ok and offers.get('@type') == 'Offer' and offers.get('price') == rent and offers.get('priceCurrency') == 'USD'
    ok = ok and offers.get('availability') == 'https://schema.org/InStock' \
        and offers.get('businessFunction') == 'http://purl.org/goodrelations/v1#LeaseOut'
    about = ld.get('about', {}) if ok else {}
    ok = ok and about.get('@type') == ('Residence' if L.get('type') == 'residential' else 'Place')
    ok = ok and about.get('address', {}).get('@type') == 'PostalAddress' and bool(about.get('address', {}).get('streetAddress')) \
        and about['address'].get('addressRegion') == 'WA'
    if L.get('lat') is None or L.get('lng') is None:
        ok = ok and 'geo' not in about
    else:
        ok = ok and about.get('geo', {}).get('latitude') == L.get('lat') and about['geo'].get('longitude') == L.get('lng')
    check(ok, f"{rel}: JSON-LD is missing/invalid, or its type/url/name/datePosted/price/address/geo do not match listings.json")
    # The inquiry form: this listing, this building (empty when it has none).
    check('name="listing-inquiry"' in page and 'data-netlify="true"' in page and 'netlify-honeypot="bot-field"' in page and 'id="inquire"' in page,
          f"{rel}: missing the Netlify form name=\"listing-inquiry\" in #inquire")
    check('<input type="hidden" name="form-name" value="listing-inquiry" />' in page, f"{rel}: missing the hidden form-name field")
    check(f'<input type="hidden" name="listing" value="{lid}" />' in page, f"{rel}: hidden listing input is not {lid!r}")
    bid = L.get('buildingId') or ''
    check(f'<input type="hidden" name="building" value="{bid}" />' in page, f"{rel}: hidden building input is not {bid!r}")
    check('name="timeframe"' in page and 'Ask about this space' in page and 'Anything I should know?' in page, f"{rel}: form fields are incomplete")
    # Gallery: photos or the one placeholder band, never both.
    if L.get('photos'):
        check('id="listing-photos"' in page and 'id="listing-photos-placeholder"' not in page, f"{rel}: has photos, so a photo grid and no placeholder")
    else:
        check('id="listing-photos-placeholder"' in page and 'id="listing-photos"' not in page, f"{rel}: no photos, so exactly the placeholder band")
    # Map: only when there are coordinates, and then with MapLibre and PMTiles loaded in order.
    has_map = L.get('lat') is not None and L.get('lng') is not None
    if has_map:
        order = [page.find(f'src="{u}"') for u in MAP_SCRIPTS]
        check(all(i >= 0 for i in order) and order == sorted(order), f"{rel}: has coordinates, so it must load maplibre-gl.js, pmtiles.js, then eb-map.js")
        css_order = [page.find(f'href="{u}"') for u in ('/css/tailwind.css', '/css/vendor/maplibre-gl.css', '/css/eb-map.css')]
        check(all(i >= 0 for i in css_order) and css_order == sorted(css_order), f"{rel}: stylesheets must load tailwind.css, vendor/maplibre-gl.css, eb-map.css in that order")
        check('id="listing-map"' in page and f'data-lat="{L.get("lat")}"' in page and f'data-lng="{L.get("lng")}"' in page and 'EBMap.create' in page,
              f"{rel}: the #listing-map div (with data-lat/data-lng) or its init script is missing")
    else:
        check('id="listing-map"' not in page and 'maplibre' not in page.lower() and 'pmtiles' not in page.lower() and 'leaflet' not in page.lower() and 'eb-map' not in page,
              f"{rel}: no coordinates, so it must carry no map markup and load no map library")
        check('openstreetmap.org/search?query=' in page, f"{rel}: no coordinates, so the OpenStreetMap search link must remain")
    check('listing-detail.js' not in page and 'LISTINGS_URL' not in page, f"{rel}: generated pages are static and must not use the fallback script or the feed")
    check(re.search(r'cdn', page, re.I) is None, f"{rel}: mentions a CDN; vendor it instead")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, page, re.I) is None, f"{rel}: contains {label} (E. Berry brand is flat, Berry/Cream only)")

# The client-side fallback (the safety net behind the rewrite).
FB_REL = 'listing.html'
if exists(FB_REL):
    fb = read(FB_REL)
    check('A PART OF WINDERMERE VASHON' in fb, f"{FB_REL}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    check_shell(FB_REL, fb, RERUN)
    check('<meta name="robots" content="noindex" />' in fb, f"{FB_REL}: missing the robots noindex meta")
    check('rel="canonical"' not in fb and 'application/ld+json' not in fb, f"{FB_REL}: a noindex fallback has no canonical and no structured data")
    order = [fb.find(f'src="{u}"') for u in ('/js/vendor/maplibre-gl.js', '/js/vendor/pmtiles.js', '/js/eb-map.js', '/js/site-config.js', '/js/listing-detail.js')]
    check(all(i >= 0 for i in order) and order == sorted(order),
          f"{FB_REL}: scripts must load maplibre-gl.js, pmtiles.js, eb-map.js, site-config.js, listing-detail.js in that order")
    css_order = [fb.find(f'href="{u}"') for u in ('/css/tailwind.css', '/css/vendor/maplibre-gl.css', '/css/eb-map.css')]
    check(all(i >= 0 for i in css_order) and css_order == sorted(css_order), f"{FB_REL}: stylesheets must load tailwind.css, vendor/maplibre-gl.css, eb-map.css in that order")
    check('id="main"' in fb and 'id="listing-loading"' in fb, f"{FB_REL}: needs <main id=\"main\"> with the loading line the script replaces")
    check(re.search(r'cdn', fb, re.I) is None, f"{FB_REL}: mentions a CDN; vendor it instead")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, fb, re.I) is None, f"{FB_REL}: contains {label} (E. Berry brand is flat, Berry/Cream only)")
if exists('js/listing-detail.js'):
    ldjs = read('js/listing-detail.js')
    for token in ('LISTINGS_URL', '/data/buildings.json', 'location.pathname', 'URLSearchParams', 'listing-inquiry', 'name="listing"',
                  'name="building"', 'EBMap.create', 'IntersectionObserver', "That one isn't on my list just now.", 'href="/listings/"'):
        check(token in ldjs, f"js/listing-detail.js: expected {token!r}")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, ldjs, re.I) is None, f"js/listing-detail.js: contains {label} (E. Berry brand is flat)")

# netlify.toml: the non-forced /listings/* -> /listing.html rewrite, AFTER every host-scoped redirect.
nt = read('netlify.toml')
redirects = []
for blk in re.split(r'^\[\[redirects\]\]\s*$', nt, flags=re.M)[1:]:
    blk = re.split(r'^\[\[', blk, flags=re.M)[0]                     # up to the next table
    f = lambda key: (re.search(rf'^\s*{key}\s*=\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', blk, re.M) or [None, None])[1]
    redirects.append({'from': f('from'), 'to': f('to'), 'status': f('status'), 'force': (f('force') or 'false').lower() == 'true'})
rw = [i for i, r in enumerate(redirects) if r['from'] == '/listings/*']
check(len(rw) == 1 and redirects[rw[0]]['to'] == '/listing.html' and redirects[rw[0]]['status'] == '200',
      'netlify.toml: needs exactly one [[redirects]] /listings/* -> /listing.html with status = 200')
check(rw and not redirects[rw[0]]['force'], 'netlify.toml: the /listings/* rewrite must NOT be forced (generated pages must win)')
hosts = [i for i, r in enumerate(redirects) if str(r['from']).startswith(('http://', 'https://'))]
check(len(hosts) >= 4 and rw and rw[0] > max(hosts, default=-1),
      'netlify.toml: the /listings/* rewrite must come AFTER the host-scoped redirects (first match wins)')
check(rw and rw[0] == len(redirects) - 1, 'netlify.toml: the /listings/* rewrite should be the last [[redirects]] block')

# netlify.toml: the basemap. Netlify serves byte ranges natively, so /map/* needs headers only, never a redirect.
header_blocks = {}
for blk in re.split(r'^\[\[headers\]\]\s*$', nt, flags=re.M)[1:]:
    blk = re.split(r'^\[\[redirects\]\]', blk, flags=re.M)[0]
    m_for = re.search(r'^\s*for\s*=\s*"([^"]+)"', blk, re.M)
    if m_for:
        header_blocks[m_for.group(1)] = dict(re.findall(r'^\s*([A-Za-z-]+)\s*=\s*"([^"]*)"', blk.split('[headers.values]', 1)[-1], re.M))
check(header_blocks.get('/map/*', {}).get('Cache-Control') == 'public, max-age=3600', 'netlify.toml: [[headers]] for /map/* must set Cache-Control = "public, max-age=3600"')
check(header_blocks.get('/*.pmtiles', {}).get('Content-Type') == 'application/octet-stream', 'netlify.toml: [[headers]] for /*.pmtiles must set Content-Type = "application/octet-stream"')
check(not any(str(r['from']).startswith('/map') or str(r['to']).startswith('/map') for r in redirects), 'netlify.toml: no redirects for /map (Range requests must reach the file)')

# sitemap: the fallback is noindex and must not be listed.
if sm_urls is not None:
    check(not any(u.rstrip('/').endswith('listing.html') for u in sm_urls), 'sitemap.xml: /listing.html is noindex and must not be listed')
    check(len([u for u in sm_urls if u.startswith(f'{SITE_URL}/listings/') and u != f'{SITE_URL}/listings/']) == len(listings),
          'sitemap.xml: it must list exactly one /listings/<id>/ URL per listing')

# css/tailwind.css must have been rebuilt for the classes the detail pages and the fallback script use.
tw_css = read('css/tailwind.css')
for cls in (r'sm\:col-span-2', r'sm\:aspect-\[16\/9\]', r'lg\:min-h-\[26rem\]', r'min-h-\[60vh\]', r'min-h-\[15rem\]', r'md\:min-h-\[20rem\]',
            r'bg-eb-sand', r'bg-eb-mustard', r'rounded-card', r'sm\:h-\[24rem\]', r'lg\:grid-cols-\[6fr_7fr\]'):
    check(cls in tw_css, f"css/tailwind.css has no .{cls}; rebuild it (see README, 'Rebuilding the stylesheet')")

if exists('.github/workflows/map-tools.yml'):
    wf = read('.github/workflows/map-tools.yml')
    for token in ("'tools/extract_pmtiles.py'", "'tools/make_fixture_pmtiles.py'", "'tools/test_extract_pmtiles.py'", "'map/**'",
                  'pip install pmtiles==3.8.1 mapbox-vector-tile==2.2.0 shapely==2.2.0', 'python3 tools/test_extract_pmtiles.py'):
        check(token in wf, f".github/workflows/map-tools.yml: expected {token}")
else:
    check(False, ".github/workflows/map-tools.yml is missing (it runs tools/test_extract_pmtiles.py)")

if exists('.github/workflows/listings-e2e.yml'):
    wf = read('.github/workflows/listings-e2e.yml')
    for token in ("'listing.html'", "'js/listing-detail.js'", "'tools/build_pages.py'", "'tools/templates/**'"):
        check(token in wf, f".github/workflows/listings-e2e.yml: expected {token} (the detail pages are covered by the same E2E)")

# =====================================================================
# E. Berry polish (Phase 6): the 404 page, per-building location copy, listing feature tags, and the accessibility
#   basics every page type must keep. (The computed-style half, contrast and focus rings included, is part Q of
#   tools/test_listings.py.)
# =====================================================================
import difflib
from html.parser import HTMLParser

# ---------------- data/buildings.json: optional per-building location copy ----------------
BUILDING_OPTIONAL = ('directions', 'nearby')
for B in buildings:
    bid = B.get('id', '<missing>')
    rel = f'buildings/{bid}/index.html'
    extra = sorted(set(B) - set(BUILDING_REQUIRED) - set(BUILDING_OPTIONAL))
    check(not extra, f"buildings.json {bid}: unknown field(s) {extra} (required: {list(BUILDING_REQUIRED)}; optional: {list(BUILDING_OPTIONAL)})")
    directions, nearby = B.get('directions'), B.get('nearby')
    if 'directions' in B:
        check(isinstance(directions, list) and len(directions) > 0
              and all(isinstance(d, dict) and set(d) == {'name', 'note'}
                      and all(isinstance(d[k], str) and d[k].strip() for k in d) for d in directions),
              f"buildings.json {bid}: directions must be a non-empty list of {{name, note}} objects with non-empty text")
    if 'nearby' in B:
        check(isinstance(nearby, list) and len(nearby) > 0 and all(isinstance(t, str) and t.strip() for t in nearby),
              f"buildings.json {bid}: nearby must be a non-empty list of non-empty strings")
    # The page shows exactly what the data says: the block when the field is there, every line escaped, nothing when it is not.
    if os.path.exists(os.path.join(ROOT, rel)):
        bpage = read(rel)
        check(('From the ferries' in bpage) == bool(directions),
              f"{rel}: the 'From the ferries' block must appear exactly when buildings.json has directions ({RERUN})")
        check(('<h3 class="font-serif text-2xl font-medium leading-[1.2]">Nearby</h3>' in bpage) == bool(nearby),
              f"{rel}: the 'Nearby' block must appear exactly when buildings.json has nearby ({RERUN})")
        for d in (directions if isinstance(directions, list) else []):
            if isinstance(d, dict) and {'name', 'note'} <= set(d):
                check(f"<strong class=\"font-semibold\">{_html.escape(str(d['name']), quote=True)}:</strong> {_html.escape(str(d['note']), quote=True)}" in bpage,
                      f"{rel}: direction {d.get('name')!r} is not on the page as written in buildings.json ({RERUN})")
        for t in (nearby if isinstance(nearby, list) else []):
            check(f'<li>{_html.escape(str(t), quote=True)}</li>' in bpage, f"{rel}: nearby line {t!r} is not on the page as written in buildings.json ({RERUN})")
check('LOCATION_COPY' not in read('tools/build_pages.py'), "tools/build_pages.py: location copy lives in data/buildings.json now; no LOCATION_COPY table")

# ---------------- data/listings.json: a feature tag must add something to the summary ----------------
_STOP = {'a', 'an', 'the', 'for', 'of', 'with', 'to', 'and', 'or', 'in', 'on', 'by', 'that', 'such', 'as', 'at', 'who', 'is'}

def _tokens(text):
    text = re.sub(r'[^a-z0-9 ]+', '', str(text).lower().replace('-', '').replace('—', ' '))
    return [w[:-1] if len(w) > 3 and w.endswith('s') else w for w in text.split() if w not in _STOP]

def repeats_summary(feature, summary):
    """True when the tag just restates the summary's first sentence (a prefix of it, or nearly every content word is in it)."""
    first = re.split(r'(?<=[.!?])\s+', ' '.join(str(summary or '').split()))[0]
    f, s_ = _tokens(feature), set(_tokens(first))
    if not f:
        return False
    return ' '.join(_tokens(first)).startswith(' '.join(f)) or sum(w in s_ for w in f) / len(f) >= 0.8

for L in listings:
    for f in L.get('features', []):
        check(not repeats_summary(f, L.get('summary')),
              f"listings.json {L.get('id')}: feature {f!r} just repeats the summary's first sentence; drop it")
    check(any(str(f).lower().startswith('all-in pricing') for f in L.get('features', [])) or L.get('type') != 'commercial',
          f"listings.json {L.get('id')}: a commercial listing keeps its 'All-in pricing' feature (it feeds the fact tile)")

# ---------------- accessibility basics on every page type ----------------
class Facts(HTMLParser):
    """What a static page promises before any script runs: landmarks, headings, names, ids, the skip link."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1 = self.main = self.footer = self.header = 0
        self.navs_unnamed = 0
        self.imgs_no_alt = []
        self.ids = []
        self.unlabeled = []
        self.first_body_anchor = None
        self.in_body = False
        self.label_depth = 0
        self.html_attrs = {}
        self.metas = []
        self.links = []
        self.title = ''
        self._in_title = False
        self.headings = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html': self.html_attrs = a
        if tag == 'meta': self.metas.append(a)
        if tag == 'link': self.links.append(a)
        if tag == 'title': self._in_title = True
        if tag == 'body': self.in_body = True
        if a.get('id'): self.ids.append(a['id'])
        if tag == 'h1': self.h1 += 1
        if tag in ('h1', 'h2', 'h3', 'h4'): self.headings.append(int(tag[1]))
        if tag == 'main': self.main += 1
        if tag == 'footer': self.footer += 1
        if tag == 'header': self.header += 1
        if tag == 'nav' and not (a.get('aria-label') or a.get('aria-labelledby')): self.navs_unnamed += 1
        if tag == 'img' and 'alt' not in a: self.imgs_no_alt.append(a.get('src'))
        if tag == 'label': self.label_depth += 1
        if tag in ('input', 'select', 'textarea') and a.get('type') != 'hidden':
            if not (self.label_depth or a.get('aria-label') or a.get('aria-labelledby')):
                self.unlabeled.append(f"<{tag} name={a.get('name')!r}>")
        if tag == 'a' and self.in_body and self.first_body_anchor is None: self.first_body_anchor = a
    def handle_endtag(self, tag):
        if tag == 'label': self.label_depth -= 1
        if tag == 'title': self._in_title = False
    def handle_data(self, data):
        if self._in_title: self.title += data

def facts_of(rel):
    f = Facts()
    f.feed(read(rel))
    return f

SKIP_LINK_CLASSES = ('sr-only', 'focus:not-sr-only', 'focus:font-bold', 'focus:text-[1.1875rem]')   # Berry on Tangerine is 4.26:1: large text only
A11Y_PAGES = (['index.html', LIST_REL, 'listing.html', '404.html', 'owners/index.html', 'technology/index.html',
               'fair-housing/index.html', 'privacy/index.html', 'accessibility/index.html']
              + [f'buildings/{B.get("id")}/index.html' for B in buildings]
              + [f'listings/{L.get("id")}/index.html' for L in listings])
for rel in A11Y_PAGES:
    if not exists(rel):
        continue
    f = facts_of(rel)
    check(f.html_attrs.get('lang') == 'en', f'{rel}: <html lang="en"> is missing')
    check(any(m.get('name') == 'theme-color' and m.get('content') == '#670A2F' for m in f.metas), f'{rel}: <meta name="theme-color" content="#670A2F"> is missing')
    check(any(m.get('name') == 'viewport' for m in f.metas) and f.title.strip(), f'{rel}: needs a viewport meta and a non-empty <title>')
    check(any(l.get('rel') == 'icon' and l.get('href') == '/images/brand/monogram-tangerine-badge.svg' for l in f.links),
          f'{rel}: favicon must be /images/brand/monogram-tangerine-badge.svg (every page the same)')
    check(f.h1 == 1, f'{rel}: needs exactly one <h1> (found {f.h1})')
    check(f.main == 1 and 'id="main"' in read(rel) and f.footer == 1 and f.header >= 1, f'{rel}: needs one <main id="main">, one <footer> and a <header>')
    check(f.navs_unnamed == 0, f'{rel}: every <nav> needs an aria-label')
    skip = f.first_body_anchor or {}
    check(skip.get('href') == '#main' and all(c in str(skip.get('class')).split() for c in SKIP_LINK_CLASSES),
          f'{rel}: the first link in <body> must be the skip link to #main, with classes {SKIP_LINK_CLASSES}')
    check(not f.imgs_no_alt, f'{rel}: <img> without an alt attribute: {f.imgs_no_alt}')
    check(not f.unlabeled, f'{rel}: form control(s) without a label: {f.unlabeled}')
    check(len(f.ids) == len(set(f.ids)), f'{rel}: duplicate id(s): {sorted({i for i in f.ids if f.ids.count(i) > 1})}')
    jumps = [(a, b) for a, b in zip(f.headings, f.headings[1:]) if b - a > 1]
    check(not jumps, f'{rel}: heading levels skip ({jumps})')

# ---------------- hover/focus states: no small text on Tangerine, no Tangerine small text on Berry (both 4.26:1, AA only for large text) ----------------
for rel in A11Y_PAGES[1:] + ['tools/templates/building.tmpl.html', 'tools/templates/building.parts.tmpl.html', 'tools/templates/listing.tmpl.html',
                              'tools/templates/listing.parts.tmpl.html', 'tools/templates/listing-fallback.tmpl.html', 'tools/templates/404.tmpl.html',
                              'tools/templates/owners.tmpl.html', 'tools/templates/technology.tmpl.html', 'tools/templates/fair-housing.tmpl.html',
                              'tools/templates/privacy.tmpl.html', 'tools/templates/accessibility.tmpl.html', 'tools/templates/legal.parts.tmpl.html',
                              'js/building.js', 'js/listings.js', 'js/listing-detail.js']:
    if exists(rel):
        t = read(rel)
        check('hover:text-eb-tangerine' not in t and 'hover:bg-eb-tangerine' not in t,
              f'{rel}: hover:text-eb-tangerine / hover:bg-eb-tangerine make small text 4.26:1; swap the underline colour (hover:decoration-*) or fill Berry instead')
for blk in ('HEADER', 'FOOTER'):
    sh = shell_block(index, blk) or ''
    check('hover:text-eb-tangerine' not in sh and 'hover:bg-eb-tangerine' not in sh, f'index.html EB:{blk}: small text must not turn Tangerine, or sit on Tangerine, on hover')

# ---------------- motion: the shell opts out of smooth scrolling, and the scripts follow ----------------
check('@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }' in (shell_block(index, 'SHELL-STYLES', r'</style>') or ''),
      'index.html EB:SHELL-STYLES: must switch scroll-behavior back to auto under prefers-reduced-motion')
for rel in ('js/building.js', 'js/listings.js', 'js/listing-detail.js', 'js/eb-map.js'):
    for line in read(rel).splitlines():
        if re.search(r'smooth|\banimate:\s*true', line):
            check('reduce' in line, f'{rel}: smooth/animated motion must be guarded by prefers-reduced-motion: {line.strip()[:80]}')
ebm = read('js/eb-map.js')
check('prefers-reduced-motion: reduce' in ebm and all(t in ebm for t in ('fadeDuration: calm ? 0 : 200', 'animate: !calm', 'map.ebCalm = calm')),
      'js/eb-map.js: the map must drop its tile fade and animated pans under prefers-reduced-motion')
check('reduce || target <= 0' in read('js/building.js'), 'js/building.js: countUp must render the final number at once under prefers-reduced-motion')

# ---------------- /404.html ----------------
NF_REL = '404.html'
for rel in ('tools/templates/404.tmpl.html', NF_REL):
    check(exists(rel), f'{rel} is missing ({RERUN})')
if exists(NF_REL):
    nf = read(NF_REL)
    check_shell(NF_REL, nf, RERUN)
    check('A PART OF WINDERMERE VASHON' in nf, f"{NF_REL}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    check('<meta name="robots" content="noindex" />' in nf, f'{NF_REL}: missing the robots noindex meta')
    check('rel="canonical"' not in nf and 'application/ld+json' not in nf, f'{NF_REL}: a not-found page has no canonical and no structured data')
    check('Well, this is a dead end.' in nf and "The page you're after isn't here" in nf and "we'll find it." in nf, f'{NF_REL}: the headline or the warm line is missing')
    for href in ('/', '/listings/', '/buildings/courthouse-square/'):
        check(f'href="{href}"' in re.sub(r'<header.*?</header>|<footer.*?</footer>', '', nf, flags=re.S), f'{NF_REL}: the page body must link to {href}')
    check('monogram-tangerine-bare.svg' in nf, f'{NF_REL}: missing the monogram seal')
    check(not re.search(r'(?:src|href)="(?!https?:|mailto:|#|/)', nf), f'{NF_REL}: Netlify serves it at any depth, so every src/href must be absolute (/...)')
    check(re.search(r'cdn', nf, re.I) is None, f'{NF_REL}: mentions a CDN; vendor it instead')
    for label, pat in FLAT_BRAND:
        check(re.search(pat, nf, re.I) is None, f'{NF_REL}: contains {label} (E. Berry brand is flat, Berry/Cream only)')
if sm_urls is not None:
    check(not any(u.rstrip('/').endswith('404.html') or u.rstrip('/').endswith('/404') for u in sm_urls), 'sitemap.xml: the 404 page must not be listed')
check('./404.html' in tw_cfg, 'tailwind.config.js content[] does not include ./404.html')
tw_css = read('css/tailwind.css')
for cls in (r'focus\:font-bold', r'focus\:text-\[1\.1875rem\]', r'hover\:bg-eb-berry', r'hover\:text-eb-cream', r'hover\:decoration-eb-tangerine',
            r'hover\:decoration-2', r'max-w-\[10ch\]', r'text-\[length\:clamp\(3\.25rem\2c 13vw\2c 9rem\)\]'):
    check(cls in tw_css, f"css/tailwind.css has no .{cls}; rebuild it (see README, 'Rebuilding the stylesheet')")

# =====================================================================
# E. Berry owners section (Phase 8): /owners/, the homepage owners block, the "For owners" nav and footer links,
#   and the "owner-intro" form. The page is generated by tools/build_pages.py (owners.tmpl.html); `python3
#   tools/build_pages.py --check` (separate CI step) proves it is not stale.
#   CONTACT-FIRST: the site never quotes a management fee or rate. Every cost conversation starts with a note.
# =====================================================================
OWN_REL = 'owners/index.html'
OWN_TMPL = 'tools/templates/owners.tmpl.html'
OWN_TITLE = 'For Vashon property owners — E. Berry Property Management'
for rel in (OWN_TMPL, OWN_REL):
    check(exists(rel), f"{rel} is missing ({RERUN})")
check('./owners/**/*.html' in tw_cfg, "tailwind.config.js content[] does not include ./owners/**/*.html")

def visible_text(markup):
    """What a visitor can read in a page or template: scripts, styles, comments and tags removed, entities decoded."""
    t = re.sub(r'<!--.*?-->|<(script|style|noscript)\b.*?</\1>', ' ', markup, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', t))).strip()

# Words and shapes that would turn a conversation into a price list, or the page into a promise of an estimate.
CONTACT_FIRST = (
    ('a percentage ("8% of rent", "percent")', r'\d\s*%|%\s*of\b|\bper\s*cent|\bpercent'),
    ('a dollar amount', r'\$'),
    ('a per-period price ("/month", "per month", "per unit")',
     r'/\s*(?:mo|month|yr|year)\b|\bper\s+(?:month|year|unit|door|property)\b|\bmonthly\s+(?:fee|rate|charge)'),
    ('a fee, rate, price or commission', r'\b(?:fees?|rates?|pricing|prices?|priced|commissions?|retainers?|charges?)\b'),
    ('a promise of a free analysis / estimate', r'\b(?:analysis|estimates?|appraisals?|valuations?|assessments?)\b|\bfree\b'),
    ('corporate PM boilerplate', r'maximi[sz]e|\bROI\b|return on investment|turn-?key|hassle-free|stress-free'),
    ('a testimonial (none exist; never fabricate one)', r'testimonial|\bstars?\b|★|\bfive-star\b'),
)

def contact_first(label, text):
    for what, pat in CONTACT_FIRST:
        m = re.search(pat, text, re.I)
        check(m is None, f"{label}: contains {what}"
              + (f" ({m.group(0)!r} in ...{text[max(0, m.start() - 40):m.end() + 40]}...)" if m else '')
              + "; the site is contact-first")

# Nav and footer: "For owners" is in the header and the footer of every page (the shell is byte-identical, but say so
# explicitly so a removed link names itself instead of showing up as a generic shell mismatch).
for rel in A11Y_PAGES:
    if not exists(rel):
        continue
    pg_ = read(rel)
    for blk in ('HEADER', 'FOOTER'):
        sh = shell_block(pg_, blk) or ''
        check(re.search(r'<a href="/owners/"[^>]*>For owners</a>', sh) is not None,
              f'{rel}: EB:{blk} has no "For owners" link to /owners/ (edit index.html, then {RERUN})')
hdr = shell_block(index, 'HEADER') or ''
check(re.search(r'<nav id="site-nav".*?<a href="/owners/"[^>]*>For owners</a>.*?</nav>', hdr, re.S) is not None,
      'index.html: the header nav (#site-nav) must carry the "For owners" link to /owners/')

# The homepage owners block: a substantial band, not a footer whisper.
hb = re.search(r'<section id="owners".*?</section>', index, re.S)
hb = hb.group(0) if hb else ''
check(bool(hb), 'index.html: the owners block (<section id="owners">) is missing')
if hb:
    check('eb-field-mustard' in hb and 'eb-card' in hb, 'index.html: the owners block is a Mustard field carrying one Cream card')
    check(re.search(r'<h2 id="owners-heading"[^>]*>[^<]*Own a place on Vashon\?', hb) is not None,
          'index.html: the owners block needs its h2 statement "Own a place on Vashon?"')
    check(re.search(r'<a href="/owners/" class="eb-btn [^"]*">[^<]+</a>', hb) is not None,
          'index.html: the owners block needs one .eb-btn pill linking to /owners/')
    check('aria-labelledby="owners-heading"' in hb, 'index.html: the owners block must be labelled by its heading')
    # Courthouse Square is one of the properties, not the owners pitch: the body speaks of homes and storefronts around the island.
    hb_body = re.search(r'</h2>\s*<p[^>]*>(.*?)</p>', hb, re.S)
    hb_body = visible_text(hb_body.group(1)) if hb_body else ''
    check(bool(hb_body) and not hb_body.startswith('I manage Courthouse Square') and 'Courthouse Square' not in hb_body,
          f'index.html: the owners block body must not lead with (or name) Courthouse Square; it is one of the properties, not the pitch (found {hb_body!r})')
    check(hb_body == 'I manage homes and storefronts around the island, as part of Windermere Vashon. If you have a place that could use a steady, friendly hand, tell me about it.',
          f'index.html: the owners block body must read "I manage homes and storefronts around the island, as part of Windermere Vashon. ..." (found {hb_body!r})')
    contact_first('index.html owners block', visible_text(hb))
check(0 < index.find('id="buildings"') < index.find('id="owners"') < index.find('id="inquire"'),
      'index.html: the owners block belongs after the buildings teaser and before the inquiry form')
check('name="inquiry"' in index and 'name="owner-intro"' not in index,
      'index.html: the tenant form stays "inquiry"; the owner form lives on /owners/ only')

if exists(OWN_REL):
    op = read(OWN_REL)
    check('A PART OF WINDERMERE VASHON' in op, f"{OWN_REL}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    check_shell(OWN_REL, op, RERUN)
    check(f'<title>{OWN_TITLE}</title>' in op, f'{OWN_REL}: <title> is not {OWN_TITLE!r}')
    check(f'<link rel="canonical" href="{SITE_URL}/owners/" />' in op, f'{OWN_REL}: canonical URL is not {SITE_URL}/owners/')
    check('name="description"' in op and f'property="og:url" content="{SITE_URL}/owners/"' in op and 'property="og:title"' in op
          and 'name="twitter:card"' in op, f'{OWN_REL}: missing meta description or Open Graph / Twitter tags')
    m = re.search(r'property="og:image" content="https://eberryvashon\.com(/[^"]+)"', op)
    check(m is not None and exists(m.group(1).lstrip('/')),
          f'{OWN_REL}: og:image must be an absolute eberryvashon.com URL of a file that exists')
    check('name="robots"' not in op, f'{OWN_REL}: the owners page is indexable (no robots meta)')
    # Structured data: a Service by the RealEstateAgent; never an Offer, price or fee.
    mld = re.search(r'<script type="application/ld\+json">(.*?)</script>', op, re.S)
    try:
        ld = json.loads(mld.group(1)) if mld else None
    except ValueError:
        ld = None
    def keys_of(o):
        if isinstance(o, dict):
            return set(o) | {k for v in o.values() for k in keys_of(v)}
        if isinstance(o, list):
            return {k for v in o for k in keys_of(v)}
        return set()
    check(isinstance(ld, dict) and ld.get('@type') == 'Service' and ld.get('url') == f'{SITE_URL}/owners/'
          and ld.get('areaServed') == 'Vashon Island, WA' and isinstance(ld.get('provider'), dict)
          and ld['provider'].get('@type') == 'RealEstateAgent'
          and ld['provider'].get('parentOrganization', {}).get('name') == 'Windermere Vashon',
          f'{OWN_REL}: JSON-LD is missing/invalid (a Service, at /owners/, provided by the RealEstateAgent, part of Windermere Vashon)')
    check(not (keys_of(ld) & {'offers', 'price', 'priceSpecification', 'priceRange', 'priceCurrency'}),
          f'{OWN_REL}: JSON-LD must not carry offers or prices (the page is contact-first)')
    # Structure: one h1, the six blurbs, the proof, the Windermere explanation, four steps, then the form.
    h1 = re.findall(r'<h1[^>]*>(.*?)</h1>', op, re.S)
    check(len(h1) == 1 and visible_text(h1[0]) == 'Own a place on Vashon?',
          f'{OWN_REL}: the h1 is "Own a place on Vashon?" (found {[visible_text(x) for x in h1]})')
    check(re.search(r'<h1[^>]*>.*?<span class="eb-hl eb-hl-mustard">place</span>', op, re.S) is not None,
          f'{OWN_REL}: the h1 highlights "place" with the Mustard highlighted-word device')
    check(re.search(r'<a href="#tell-me" class="eb-btn[^"]*">[^<]+</a>', op) is not None
          and 0 < op.find('<a href="#tell-me" class="eb-btn') < op.find('id="what-i-do"'),
          f'{OWN_REL}: the hero carries one .eb-btn pill to #tell-me')
    order = [op.find(f'id="{i}"') for i in ('what-i-do', 'both', 'windermere', 'how', 'tell-me')]
    check(all(i > 0 for i in order) and order == sorted(order), f'{OWN_REL}: sections must run what-i-do, both, windermere, how, tell-me')
    what = re.search(r'<section id="what-i-do".*?</section>', op, re.S)
    titles = [visible_text(t) for t in re.findall(r'<h3[^>]*>(.*?)</h3>', what.group(0), re.S)] if what else []
    check(titles == ['Marketing & listing', 'Tenant screening', 'Leases done properly', 'Rent & monthly statements',
                     'Maintenance with island vendors', 'Regular walk-throughs'],
          f'{OWN_REL}: "What I take care of" needs its six blurbs, got {titles}')
    both = (re.search(r'<section id="both".*?</section>', op, re.S) or [''])[0]
    # The commercial card is generic and mirrors the residential card (badge, title, italic tagline, body, link); Courthouse
    # Square appears only as an inline link in the commercial body, so it is one of the properties and not the card's headline.
    cards = re.findall(r'<article class="eb-card.*?</article>', both, re.S)
    check(len(cards) == 2, f'{OWN_REL}: "Storefronts and homes, both" has two cards, commercial then residential (found {len(cards)})')
    if len(cards) == 2:
        com, res = cards
        def card_parts(c):
            badge = re.search(r'<span class="self-start[^>]*>(.*?)</span>', c, re.S)
            title = re.search(r'<h3[^>]*>(.*?)</h3>', c, re.S)
            tag = re.search(r'<p class="mt-2 italic">(.*?)</p>', c, re.S)
            ps = re.findall(r'<p\b[^>]*>(.*?)</p>', c, re.S)
            link = [(h, visible_text(t)) for h, t in re.findall(r'<a href="([^"]*)"[^>]*>([^<]*)</a>', ps[-1])] if ps else []
            return (visible_text(badge.group(1)) if badge else '', visible_text(title.group(1)) if title else '',
                    visible_text(tag.group(1)) if tag else '', re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', '', ps[1]))).strip() if len(ps) > 1 else '', link)   # (inline tags dropped without a space)
        cb, ct, cg, cbody, clink = card_parts(com)
        rb, rt, rg, rbody, rlink = card_parts(res)
        check(ct != 'Courthouse Square' and 'Courthouse Square' not in ct and 'Courthouse Square' not in cg,
              f'{OWN_REL}: the commercial card title/tagline must not be Courthouse Square; it is a generic card (found {ct!r} / {cg!r})')
        check((cb, ct, cg) == ('Commercial', 'Storefronts and offices', 'Room for the people who keep Vashon running.'),
              f'{OWN_REL}: the commercial card is Commercial / "Storefronts and offices" / "Room for the people who keep Vashon running." (found {(cb, ct, cg)})')
        check(cbody == 'From a one-room practice to a place with a front window, I manage commercial space with the same care as a home. '
                       'Courthouse Square, a multi-suite building on Vashon Hwy, is one of them. Its page shows how I work: the suites, the standard lease, and the neighbors, all out in the open.',
              f'{OWN_REL}: the commercial card body changed (found {cbody!r})')
        check(re.search(r'<a href="/buildings/courthouse-square/" class="[^"]*\bunderline\b[^"]*\bdecoration-eb-tangerine\b[^"]*">Courthouse Square</a>', com) is not None
              and com.count('/buildings/courthouse-square/') == 1,
              f'{OWN_REL}: "Courthouse Square" is one inline body link (Tangerine underline) to /buildings/courthouse-square/ in the commercial card')
        check(clink == [('/listings/?type=commercial', 'See commercial spaces →')],
              f'{OWN_REL}: the commercial card link is "See commercial spaces →" to /listings/?type=commercial (found {clink})')
        check((rb, rt, rg) == ('Residential', 'Homes and cottages', 'Houses, cottages, and apartments.') and rlink == [('#tell-me', 'Tell me about your home →')],
              f'{OWN_REL}: the residential card must stay as it was (found {(rb, rt, rg, rlink)})')
        check(len(re.findall(r'<p\b', com)) == len(re.findall(r'<p\b', res)) == 3,
              f'{OWN_REL}: the commercial card mirrors the residential card (same number of paragraphs: tagline, body, link)')
    check('I manage Courthouse Square' not in op and 'flagship' not in both.lower(),
          f'{OWN_REL}: no "I manage Courthouse Square" sentence anywhere, and never "flagship"')
    check('Residential' in both and 'Commercial' in both, f'{OWN_REL}: both commercial and residential are welcome')
    wind = (re.search(r'<section id="windermere".*?</section>', op, re.S) or [''])[0]
    check('>A part of Windermere Vashon</h2>' in wind and 'is a part of Windermere Vashon' in wind,
          f'{OWN_REL}: the Windermere Vashon block is missing')
    how = (re.search(r'<section id="how".*?</section>', op, re.S) or [''])[0]
    check(len(re.findall(r'<ol\b', how)) == 1 and len(re.findall(r'<li\b', how)) == 4, f'{OWN_REL}: "How it works" is one ordered list of four steps')
    check(op.count('bg-eb-mustard') >= 5, f'{OWN_REL}: Mustard (the Property Management accent) marks the step badges and the commercial badge')
    check('<blockquote' not in op, f'{OWN_REL}: no testimonials (none exist)')
    # The owner-intro form: same mechanism as the tenant form (static HTML, hidden form-name, honeypot, plain POST).
    form = (re.search(r'<form\b.*?</form>', op, re.S) or [''])[0]
    check(len(re.findall(r'<form\b', op)) == 1 and 'name="owner-intro"' in form and 'data-netlify="true"' in form
          and 'netlify-honeypot="bot-field"' in form and 'method="POST"' in form and 'id="owner-form"' in form,
          f'{OWN_REL}: one Netlify form name="owner-intro" (data-netlify, honeypot, POST) with id="owner-form"')
    check('<input type="hidden" name="form-name" value="owner-intro" />' in form, f'{OWN_REL}: missing the hidden form-name field')
    check(re.search(r'<p class="hidden">\s*<label>[^<]*<input name="bot-field"', form) is not None, f'{OWN_REL}: missing the hidden honeypot field')
    def field(name):
        return (re.search(rf'<(?:input|select|textarea)\b[^>]*\bname="{name}"[^>]*>', form) or [''])[0]
    check('required' in field('name') and 'required' in field('email') and 'type="email"' in field('email')
          and 'required' in field('property-address') and 'required' not in field('phone') and 'type="tel"' in field('phone'),
          f'{OWN_REL}: name, email and property address are required; email is typed; phone is optional and typed tel')
    check('<select' in field('property-type') and field('message').startswith('<textarea'),
          f'{OWN_REL}: the form needs a property-type select and a message textarea')
    opts = re.findall(r'<option value="([^"]*)"', (re.search(r'<select.*?</select>', form, re.S) or [''])[0])
    check(opts == ['', 'Residential', 'Commercial', 'Other'], f'{OWN_REL}: property-type options are {opts}')
    check(re.search(r'<button type="submit" class="eb-btn [^"]*">[^<]+</button>', form) is not None,
          f'{OWN_REL}: the submit pill must be an .eb-btn (>=19px bold)')
    check(re.search(r'cdn', op, re.I) is None, f'{OWN_REL}: mentions a CDN; vendor it instead')
    hosts = set()
    for tag in re.findall(r'<(?:script|link)\b[^>]*>', op):
        mh = re.search(r'\b(?:src|href)="https?://([^/"]+)', tag)
        if mh and 'rel="canonical"' not in tag:
            hosts.add(mh.group(1))
    check(hosts <= {'fonts.googleapis.com', 'fonts.gstatic.com'}, f'{OWN_REL}: external script/stylesheet hosts {sorted(hosts)}; only Google Fonts allowed')
    for label, pat in FLAT_BRAND:
        check(re.search(pat, op, re.I) is None, f'{OWN_REL}: contains {label} (E. Berry brand is flat, Berry/Cream only)')
    # Contact-first: nothing on the page, in its metadata or in its template quotes a fee, a rate or a price.
    metas = ' '.join(re.findall(r'<meta [^>]*\bcontent="([^"]*)"', op))
    contact_first(OWN_REL, ' '.join([visible_text(op), _html.unescape(metas), mld.group(1) if mld else '']))
if exists(OWN_TMPL):
    contact_first(OWN_TMPL, re.sub(r'\$[a-z_]+', ' ', visible_text(read(OWN_TMPL))))   # ($name placeholders are not dollar amounts)

# The form name belongs to exactly one page; the existing forms keep theirs.
form_names = {}
for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ('.git', '.claude', 'node_modules', 'lease', 'tools')]
    for fn in files:
        if fn.endswith('.html'):
            frel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
            for nm in re.findall(r'<form\b[^>]*\bname="([^"]+)"', read(frel)):
                form_names.setdefault(nm, []).append(frel)
check(form_names.get('owner-intro') == [OWN_REL], f'the Netlify form "owner-intro" must be on {OWN_REL} only (found {form_names.get("owner-intro")})')
check('index.html' in form_names.get('inquiry', []), 'the tenant form "inquiry" is gone from index.html')
check(bool(form_names.get('listing-inquiry')), 'the "listing-inquiry" form is gone from the listing pages')

# The E2E workflow runs when the owners page changes; css/tailwind.css has the classes the owners page and the nav use.
if exists('.github/workflows/listings-e2e.yml'):
    check("'owners/**'" in read('.github/workflows/listings-e2e.yml'),
          ".github/workflows/listings-e2e.yml: expected 'owners/**' (the owners page is covered by the same E2E)")
tw_css = read('css/tailwind.css')
for cls in (r'md\:grid-cols-2', r'lg\:grid-cols-2',r'max-w-\[20ch\]', r'lg\:grid-cols-4', r'lg\:px-1\.5', r'xl\:px-2', r'xl\:text-lg', r'lg\:text-base', r'xl\:gap-2',
            r'sm\:px-8', r'text-\[length\:clamp\(2\.25rem\2c 4\.5vw\2c 3\.5rem\)\]'):
    check(cls in tw_css, f"css/tailwind.css has no .{cls}; rebuild it (see README, 'Rebuilding the stylesheet')")


# =====================================================================
# E. Berry Phase 9: Courthouse Square is one of the properties (not the flagship), and the "Our technology" page (Ledger)
#   /technology/ is generated by tools/build_pages.py (technology.tmpl.html); `python3 tools/build_pages.py --check`
#   (separate CI step) proves it is not stale.
#   EVIDENCE RULE: every factual claim about Ledger on that page was verified in the Ledger source. These checks keep the
#   page free of the things that cannot be verified from here: statistics, security superlatives, pricing, testimonials.
# =====================================================================
TECH_REL = 'technology/index.html'
TECH_TMPL = 'tools/templates/technology.tmpl.html'
TECH_TITLE = 'Our technology — E. Berry Property Management'
for rel in (TECH_TMPL, TECH_REL):
    check(exists(rel), f"{rel} is missing ({RERUN})")
check('./technology/**/*.html' in tw_cfg, "tailwind.config.js content[] does not include ./technology/**/*.html")
if exists('.github/workflows/listings-e2e.yml'):
    check("'technology/**'" in read('.github/workflows/listings-e2e.yml'),
          ".github/workflows/listings-e2e.yml: expected 'technology/**' (the technology page is covered by the same E2E)")

# ---------------- the nav: Homes, Commercial, For owners, Technology (+ the Inquire pill); Courthouse Square is in the footer ----------------
EXPECTED_NAV = [('/listings/?type=residential', 'Homes'), ('/listings/?type=commercial', 'Commercial'),
                ('/owners/', 'For owners'), ('/technology/', 'Technology'), ('/#inquire', 'Inquire')]

def nav_links(page):
    """[(href, label)] of the header nav (#site-nav), or None."""
    hdr = shell_block(page, 'HEADER') or ''
    m = re.search(r'<nav id="site-nav".*?</nav>', hdr, re.S)
    return re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', m.group(0)) if m else None

for rel in A11Y_PAGES:
    if not exists(rel):
        continue
    pg_ = read(rel)
    got = nav_links(pg_)
    check(got == EXPECTED_NAV, f'{rel}: the header nav must be Homes, Commercial, For owners, Technology + Inquire (got {got}); edit index.html, then {RERUN}')
    hdr_ = shell_block(pg_, 'HEADER') or ''
    check('/buildings/courthouse-square/' not in hdr_ and 'Courthouse Square' not in hdr_,
          f'{rel}: EB:HEADER must not carry a Courthouse Square link (it is one of the properties, not a top-level destination)')
    ftr_ = shell_block(pg_, 'FOOTER') or ''
    check(re.search(r'<a href="/buildings/courthouse-square/"[^>]*>Courthouse Square</a>', ftr_) is not None,
          f'{rel}: EB:FOOTER must still link Courthouse Square to /buildings/courthouse-square/')
    check(re.search(r'<a href="/technology/"[^>]*>Technology</a>', ftr_) is not None, f'{rel}: EB:FOOTER has no "Technology" link to /technology/')
# The nav keeps P8's one-row type: 16px with tight gaps at lg, 18px at xl (tools/test_listings.py measures the header at 1024px).
nav_tag = re.search(r'<nav id="site-nav"[^>]*>', hdr, re.S)
check(nav_tag is not None and all(c in nav_tag.group(0) for c in ('lg:text-base', 'lg:gap-1', 'xl:gap-2', 'xl:text-lg', 'whitespace-nowrap')),
      'index.html: the header nav lost its lg:text-base / lg:gap-1 / xl:text-lg one-row classes')
check(all('lg:px-1.5 xl:px-2' in m for m in re.findall(r'<a href="(?!/#inquire)[^"]+" class="[^"]*"', hdr[hdr.find('<nav id="site-nav"'):])),
      'index.html: every header nav link keeps lg:px-1.5 xl:px-2 (tight at 1024px)')

# ---------------- Courthouse Square is not the flagship: no such word anywhere a visitor or the owner's sheet could meet it ----------------
FLAGSHIP_SKIP_DIRS = {'.git', '.claude', 'node_modules', 'vendor', 'fonts', 'images', 'map', '__pycache__'}
FLAGSHIP_SKIP_FILES = {'tools/check_site.py', 'tools/test_listings.py', 'README.md'}      # these name the word in order to forbid it
FLAGSHIP_EXT = ('.html', '.json', '.js', '.py', '.md', '.toml', '.xml', '.yml', '.css')
flagship_hits = []
for dirpath, dirs, files_ in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in FLAGSHIP_SKIP_DIRS]
    for fn in files_:
        frel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
        if fn.endswith(FLAGSHIP_EXT) and frel not in FLAGSHIP_SKIP_FILES and not frel.endswith('tailwind.css'):
            try:
                if 'flagship' in read(frel).lower():
                    flagship_hits.append(frel)
            except (OSError, UnicodeDecodeError):
                pass
check(not flagship_hits, f'"flagship" appears in {sorted(flagship_hits)}: Courthouse Square is one of the properties, not the flagship; reword it (pages, templates, data and code alike)')
for B in buildings:
    check('flagship' not in json.dumps(B).lower(), f"buildings.json {B.get('id')}: copy must not call the building a flagship")

# ---------------- the homepage: Courthouse Square is one modest strip, lighter than Homes, Commercial and Owners ----------------
cs = (re.search(r'<section id="buildings".*?</section>', index, re.S) or [''])[0]
check(bool(cs), 'index.html: the Courthouse Square strip (<section id="buildings">) is missing')
if cs:
    check(cs.count('<a ') == 1 and 'href="/buildings/courthouse-square/"' in cs, 'index.html: the Courthouse Square strip has exactly one link, to /buildings/courthouse-square/')
    check(re.search(r'bg-eb-(?:berry|mustard|tangerine|sky|sage|sand)|eb-field-|eb-btn|eb-card|min-h-|var\(--eb-h2-size\)', cs) is None,
          'index.html: the Courthouse Square strip must stay modest: no color field, no pill, no big heading, no tall card')
    check(len(visible_text(cs)) <= 150, f'index.html: the Courthouse Square strip is a sentence and a link, not a section ({len(visible_text(cs))} characters of text)')
    check('Courthouse Square' in visible_text(cs) and 'multi-suite' not in cs, 'index.html: the strip names Courthouse Square')
check('The buildings I look after' not in index and 'Visit Courthouse Square' not in index, 'index.html: the old full Courthouse Square band is gone')
hm = index.find('aria-label="Homes and commercial space"')
check(0 < hm < index.find('id="buildings"') < index.find('id="owners"'), 'index.html: the strip sits after Homes/Commercial and before the owners block')
check('<option value="Courthouse Square">Courthouse Square</option>' in index, 'index.html: the inquiry form still offers Courthouse Square')

# ---------------- /technology/ ----------------
approval_note = None
if exists(TECH_REL):
    tp = read(TECH_REL)
    check('A PART OF WINDERMERE VASHON' in tp, f"{TECH_REL}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    check_shell(TECH_REL, tp, RERUN)
    check(f'<title>{TECH_TITLE}</title>' in tp, f'{TECH_REL}: <title> is not {TECH_TITLE!r}')
    check(f'<link rel="canonical" href="{SITE_URL}/technology/" />' in tp, f'{TECH_REL}: canonical URL is not {SITE_URL}/technology/')
    check('name="description"' in tp and f'property="og:url" content="{SITE_URL}/technology/"' in tp and 'property="og:title"' in tp
          and f'property="og:title" content="{TECH_TITLE}"' in tp and 'name="twitter:card"' in tp, f'{TECH_REL}: missing meta description or Open Graph / Twitter tags')
    m = re.search(r'property="og:image" content="https://eberryvashon\.com(/[^"]+)"', tp)
    check(m is not None and exists(m.group(1).lstrip('/')), f'{TECH_REL}: og:image must be an absolute eberryvashon.com URL of a file that exists')
    check('name="robots"' not in tp, f'{TECH_REL}: the technology page is indexable (no robots meta)')
    # Structured data: a WebPage about Ledger; never an offer, price, rating or review.
    mld = re.search(r'<script type="application/ld\+json">(.*?)</script>', tp, re.S)
    try:
        ld = json.loads(mld.group(1)) if mld else None
    except ValueError:
        ld = None
    def keys_of_(o):
        if isinstance(o, dict):
            return set(o) | {k for v in o.values() for k in keys_of_(v)}
        if isinstance(o, list):
            return {k for v in o for k in keys_of_(v)}
        return set()
    check(isinstance(ld, dict) and ld.get('@type') == 'WebPage' and ld.get('url') == f'{SITE_URL}/technology/' and ld.get('name') == 'Our technology'
          and isinstance(ld.get('about'), dict) and ld['about'].get('name') == 'Ledger'
          and isinstance(ld.get('publisher'), dict) and ld['publisher'].get('@type') == 'RealEstateAgent'
          and ld['publisher'].get('parentOrganization', {}).get('name') == 'Windermere Vashon',
          f'{TECH_REL}: JSON-LD is missing/invalid (a WebPage "Our technology" at /technology/, about Ledger, published by the RealEstateAgent, part of Windermere Vashon)')
    check(not (keys_of_(ld) & {'offers', 'price', 'priceRange', 'priceCurrency', 'aggregateRating', 'review', 'ratingValue'}),
          f'{TECH_REL}: JSON-LD must not carry offers, prices, ratings or reviews (Ledger is not for sale and has no reviews)')
    # Structure: one h1 "Our technology" (technology highlighted), then the sections in order.
    h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', tp, re.S)
    check(len(h1s) == 1 and visible_text(h1s[0]) == 'Our technology', f'{TECH_REL}: the h1 is "Our technology" (found {[visible_text(x) for x in h1s]})')
    check(re.search(r'<h1[^>]*>.*?<span class="eb-hl eb-hl-mustard">technology</span>', tp, re.S) is not None, f'{TECH_REL}: the h1 highlights "technology" with the Mustard highlighted-word device')
    order = [tp.find(f'id="{i}"') for i in ('why', 'tenants', 'for-owners', 'private', 'this-site', 'closer')]
    check(all(i > 0 for i in order) and order == sorted(order), f'{TECH_REL}: sections must run why, tenants, for-owners, private, this-site, closer')
    n_h2 = len(re.findall(r'<h2\b', tp))
    check(n_h2 == 6, f'{TECH_REL}: six h2 sections (found {n_h2})')
    main_ = (re.search(r'<main id="main">.*?</main>', tp, re.S) or [''])[0]
    text_ = visible_text(main_)
    sec = lambda i: (re.search(rf'<section id="{i}".*?</section>', tp, re.S) or [''])[0]
    # The software is named. Stripe is still on the page (and in the meta description), but as an ordinary tenants tile: since P11 the
    # tenants section leads with easy visibility and easy issue reporting, not with paying rent.
    check('Ledger' in text_ and text_.count('Ledger') >= 5, f'{TECH_REL}: the page names the software "Ledger"')
    ten, own = sec('tenants'), sec('for-owners')
    tiles = lambda s_: re.findall(r'<li\b[^>]*>(.*?)</li>', s_, re.S)
    ten_tiles, own_tiles = tiles(ten), tiles(own)
    check('Stripe' in text_ and 'Stripe' in (re.search(r'name="description" content="([^"]*)"', tp) or ['', ''])[1], f'{TECH_REL}: "Stripe" must be on the page and in its meta description')
    check('Your card or bank details go to Stripe, not to me' in ten and 'never sees or stores your full card or bank account number' in ten,
          f'{TECH_REL}: the Stripe tile must say card and bank details go to Stripe and Ledger never sees or stores the full numbers (verified in Ledger: hosted Checkout, no card fields)')
    check('<article' not in ten and 'eb-card' not in ten, f'{TECH_REL}: the tenants section has no big featured card (rent through Stripe is an ordinary tile, not the hero)')
    ten_titles = [visible_text(m_.group(0)) if m_ else '' for m_ in (re.search(r'<h3[^>]*>.*?</h3>', t_, re.S) for t_ in ten_tiles)]
    stripe_tiles = [i for i, t_ in enumerate(ten_titles) if 'Stripe' in t_]
    check(len(stripe_tiles) == 1 and stripe_tiles[0] > 0 and 'eb-hl' not in ten_tiles[stripe_tiles[0]],
          f'{TECH_REL}: exactly one tenants tile is titled for Stripe, it is not the first tile, and it carries no highlighted word (it is no longer the hero)')
    check(len(ten_tiles) == 5 and len(own_tiles) == 6 and len(tiles(sec('why'))) == 3 and len(tiles(sec('private'))) == 4,
          f'{TECH_REL}: tiles: 3 in why, 5 under tenants, 6 for owners, 4 in private')
    # Tenants lead with easy issue submission: the FIRST tile is the report-a-problem tile (verified in Ledger: tenant/maintenance form,
    # up to 3 photos, the urgent checkbox "water, heat, safety", the status timeline, and the notices queued as a request moves).
    lead = visible_text(ten_tiles[0]) if ten_tiles else ''
    check(all(p_ in lead for p_ in ('Report a problem', 'up to three photos', 'urgent', 'water, heat or safety', 'received to done', "you're told as it moves")),
          f'{TECH_REL}: the first tenants tile must be the one about reporting a problem (up to three photos, urgent for water, heat or safety, followed from received to done, told as it moves); found {lead[:80]!r}')
    check(re.search(r'shouldn.t have to struggle to get an answer', visible_text(re.sub(r'<ul.*?</ul>', ' ', ten, flags=re.S))) is not None,
          f'{TECH_REL}: the tenants intro must carry "you shouldn\'t have to struggle to get an answer"')
    # Owners lead with seeing their repairs, then the repair-approval tile, whose copy the owner dictated word for word.
    APPROVAL_TITLE = 'Bigger repairs wait for your OK'
    APPROVAL_BODY = ("When a repair goes past the everyday, it comes to you first: what's wrong, what it should cost, and who'd do it. "
                     "You approve it from your owner login, then watch it through to done.")
    check(len(own_tiles) >= 2 and 'Repairs you can see' in visible_text(own_tiles[0]) and 'any open repairs?' in visible_text(own_tiles[0]),
          f'{TECH_REL}: the first owners tile must be "Repairs you can see" (activity as it happens, the cost on the statement, "any open repairs?")')
    check(len(own_tiles) >= 2 and visible_text(own_tiles[1]) == f'{APPROVAL_TITLE} {APPROVAL_BODY}',
          f'{TECH_REL}: the SECOND owners tile must be the approval tile with the owner-directed copy, exactly: "{APPROVAL_TITLE}" / "{APPROVAL_BODY}" (found {visible_text(own_tiles[1])[:90] if len(own_tiles) > 1 else None!r})')
    check(re.search(r'shouldn.t have to worry about your building', visible_text(re.sub(r'<ul.*?</ul>', ' ', own, flags=re.S))) is not None,
          f'{TECH_REL}: the owners intro must carry "you shouldn\'t have to worry about your building"')
    # Rent reaches the owner's bank account through Stripe: Ledger's own words (src/app/owner/payouts/page.tsx, "Rent paid by your tenants
    # goes to your bank account through Stripe."). The old "paid to your own Stripe account" wording, and any claim that the money never
    # passes through another account, are gone and must stay gone.
    own_text = visible_text(own)
    check('goes to your bank account through Stripe' in own_text, f'{TECH_REL}: the owners section must say rent goes to the owner\'s bank account through Stripe')
    check(re.search(r'own\s+Stripe\s+account|paid\s+to\s+your\s+own\b', visible_text(tp) + ' ' + (visible_text(read(TECH_TMPL)) if exists(TECH_TMPL) else ''), re.I) is None,
          f'{TECH_REL} (or its template): still says rent is paid to the owner\'s "own Stripe account"; Ledger says it goes to the owner\'s bank account through Stripe')
    check(re.search(r'never\s+(?:passes?|touch|goes through|moves? through)|doesn.t\s+(?:pass|touch)|bypass|no other account|any other account', own_text, re.I) is None,
          f'{TECH_REL}: the owners section must not claim the money never passes through any other account (Ledger does not say that)')
    # The approval tile describes owner repair approval, which Ledger does not have yet. While the tile is on the page, remind (do not fail).
    if APPROVAL_TITLE in tp:
        approval_note = (f'{TECH_REL} carries the owner-directed tile "{APPROVAL_TITLE}"; owner repair approval must be LIVE in Ledger before this site '
                         'goes to production. Remove or reword the tile if it is not (README, "Before launch")')
    # Links: the two audiences' calls to action, and the pill is >=19px bold (.eb-btn).
    check(re.search(r'<a href="/listings/" class="eb-btn [^"]*">[^<]+</a>', sec('closer')) is not None and 'href="/owners/"' in sec('closer'),
          f'{TECH_REL}: the closer needs an .eb-btn pill to /listings/ and a link to /owners/')
    check(len(re.findall(r'\bclass="eb-btn\b', main_)) == 1, f'{TECH_REL}: one pill on the page')
    check('href="#tenants"' in tp and 'href="#for-owners"' in tp, f'{TECH_REL}: the hero jumps to #tenants and #for-owners')
    # What the page may not contain. Statistics and superlatives cannot be verified from the source; pricing is contact-first.
    metas_ = ' '.join(re.findall(r'<meta [^>]*\bcontent="([^"]*)"', tp))
    claims_text = ' '.join([text_, _html.unescape(metas_), mld.group(1) if mld else ''])
    TECH_FORBIDDEN = (
        ('a percentage or an uptime figure', r'\d\s*%|%\s*of\b|\bper\s*cent|\bpercent|\buptime\b|\b99\.\d'),
        ('a "bank-level" / "military-grade" style security claim', r'bank[- ](?:level|grade)|military|enterprise[- ]grade|\bbank-?grade|256[- ]?bit|\bSOC\s?2|\bPCI\b|unhackable|impenetrable|100% secure|completely secure'),
        ('a dollar amount, price or subscription', r'\$|\bpric(?:e|es|ed|ing)\b|\bsubscription|\bper\s+(?:month|year|unit)\b|/\s*(?:mo|month|yr|year)\b|\bfree\b|\bcommissions?\b'),
        ('corporate SaaS-speak', r'maximi[sz]e|\bleverag(?:e|es|ed|ing)\b|seamless|synerg|revolution|game-?chang|cutting-?edge|all-in-one|state-of-the-art|best-in-class|world-?class|turn-?key|scalab|\brobust\b|\bstreamlin|\bplatform\b|\bsolutions?\b|next-?gen|AI-powered|\bholistic'),
        ('a headline statistic ("1,000 tenants", "24/7")', r'\b\d[\d,]*\+?\s+(?:tenants|owners|properties|units|buildings|customers|users|payments|transactions|leases)\b|\b24\s*/\s*7\b'),
        ('a testimonial (none exist; never fabricate one)', r'testimonial|\bstars?\b|★|\bfive-star\b|\brated\b'),
    )
    for what, pat in TECH_FORBIDDEN:
        mm = re.search(pat, claims_text, re.I)
        check(mm is None, f'{TECH_REL}: contains {what}' + (f' ({mm.group(0)!r} in ...{claims_text[max(0, mm.start() - 40):mm.end() + 40]}...)' if mm else '')
              + '; the page may only say what was verified in the Ledger source')
    for what, pat in TECH_FORBIDDEN:
        mm = re.search(pat, re.sub(r'\$[a-z_]+', ' ', visible_text(read(TECH_TMPL))), re.I) if exists(TECH_TMPL) else None
        check(mm is None, f'{TECH_TMPL}: contains {what} ({mm.group(0) if mm else ""!r})')
    check('<blockquote' not in tp and '<table' not in tp, f'{TECH_REL}: no testimonials and no feature-matrix tables')
    check(all(src in BRAND_IMAGES for src in re.findall(r'<img [^>]*\bsrc="([^"]+)"', main_)), f'{TECH_REL}: the only images are the E. Berry brand marks and the one Windermere co-brand logo (no screenshots, no stock photos)')
    # The Ledger listings feed: this site still reads /data/listings.json. While it does, the page must not say the site's listings
    # come straight from Ledger or are "never stale" (Ledger's feed is cached for minutes and this site is not wired to it yet).
    site_cfg = read('js/site-config.js') if exists('js/site-config.js') else ''
    if "LISTINGS_URL: '/data/listings.json'" in site_cfg:
        mm = re.search(r'never stale|always up to date|up to the minute|real-?time|straight from (?:ledger|the same system)|comes? (?:straight )?from ledger|powered by ledger|live (?:feed|from)', claims_text, re.I)
        check(mm is None, f'{TECH_REL}: says the listings here come live from Ledger ({mm.group(0) if mm else ""!r}), but js/site-config.js still reads /data/listings.json; keep the copy to what is true of Ledger itself')
    check(re.search(r'cdn', tp, re.I) is None, f'{TECH_REL}: mentions a CDN; vendor it instead')
    hosts = set()
    for tag in re.findall(r'<(?:script|link)\b[^>]*>', tp):
        mh = re.search(r'\b(?:src|href)="https?://([^/"]+)', tag)
        if mh and 'rel="canonical"' not in tag:
            hosts.add(mh.group(1))
    check(hosts <= {'fonts.googleapis.com', 'fonts.gstatic.com'}, f'{TECH_REL}: external script/stylesheet hosts {sorted(hosts)}; only Google Fonts allowed')
    check('<form' not in tp, f'{TECH_REL}: no form here (the forms live on / and /owners/)')
    for label, pat in FLAT_BRAND:
        check(re.search(pat, tp, re.I) is None, f'{TECH_REL}: contains {label} (E. Berry brand is flat, Berry/Cream only)')
tw_css = read('css/tailwind.css')
for cls in (r'lg\:grid-cols-\[5fr_7fr\]', r'lg\:grid-cols-3', r'lg\:grid-cols-4', r'text-\[length\:clamp\(2\.75rem\2c 11\.5vw\2c 8rem\)\]', r'sm\:py-12', r'sm\:flex-row'):
    check(cls in tw_css, f"css/tailwind.css has no .{cls}; rebuild it (see README, 'Rebuilding the stylesheet')")

# =====================================================================
# E. Berry Phase 10: the Windermere Real Estate Vashon Island co-brand logo (images/brand/windermere-vashon-island.png)
#   LEGAL CONTEXT: a broker using a brand must show the firm's licensed name clearly and conspicuously with it
#   (WAC 308-124B-210(2)(a)). The text co-brand lines (the header's "A PART OF WINDERMERE VASHON", the footer's
#   "E. Berry Property Management — A Part of Windermere Vashon", the owners page block) ARE that identification and
#   stay exactly as they are; the logo only makes the affiliation unmistakable. It goes in three places and nowhere else:
#     - the footer of every page, on its own flat Cream panel (the navy and black mark is illegible on Berry),
#     - the owners page's "A part of Windermere Vashon" lockup card, beside the E. Berry wordmark,
#     - the homepage's "part of Windermere Vashon" line, straight on the Cream field, exactly w-28 (112px) wide.
#   SIZES (Phase 12: the owner found them too big): footer panel w-32 (128px) with p-3, so the logo is 104px; homepage w-28 (112px);
#   owners lockup 9rem (144px). TRADEMARK RULE and legal line unchanged.
#   LINKS (Phase 12): every logo is a plain link to the office's own website, https://www.windermerevashon.com/ (same convention as the
#   footer's "Lease documents" link: no target, no rel), named by the img alt alone (no visible text, no aria-label needed).
#   NOT in the header: at header size its "Vashon Island" lettering would be about 6px, not clear and conspicuous.
#   TRADEMARK RULE: the mark is used unmodified (no recolor, restyle, redraw, distort or crop): only its white background was removed.
# =====================================================================
import struct, zlib

WM_PNG_REL = 'images/brand/windermere-vashon-island.png'
WM_INKS = {(0, 0, 0), (1, 26, 68), (104, 105, 107)}   # the logo's three solid inks (black, navy, grey), measured from the source JPEG

def decode_png(path):
    """(width, height, bit depth, color type, interlace, rows) of a PNG, stdlib only. rows are unfiltered RGBA scanlines
    (bytearrays) for 8-bit non-interlaced RGBA, else None."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    pos, idat, ihdr = 8, b'', None
    while pos + 8 <= len(data):
        n, typ = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', body)
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
    if ihdr is None:
        return None
    w, h, depth, ctype, _, _, interlace = ihdr
    if (depth, ctype, interlace) != (8, 6, 0):
        return (w, h, depth, ctype, interlace, None)
    raw, stride, bpp = zlib.decompress(idat), w * 4, 4
    rows, prev, i = [], bytearray(stride), 0
    for _y in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ft == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif ft == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif ft == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif ft == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 255
        rows.append(line)
        prev = line
    return (w, h, depth, ctype, interlace, rows)

# ---------------- the asset: a transparent RGBA PNG at full resolution, unmodified ink colors ----------------
check(exists(WM_PNG_REL), f'{WM_PNG_REL} is missing (the Windermere co-brand logo)')
if exists(WM_PNG_REL):
    png = decode_png(os.path.join(ROOT, WM_PNG_REL))
    check(png is not None, f'{WM_PNG_REL}: not a PNG')
    if png:
        pw, ph, pdepth, pctype, pinter, prows = png
        check((pdepth, pctype, pinter) == (8, 6, 0) and prows is not None,
              f'{WM_PNG_REL}: must be an 8-bit, non-interlaced RGBA PNG (color type 6) so it has a real alpha channel (got depth {pdepth}, color type {pctype}, interlace {pinter})')
        check(pw >= 700 and 1.6 <= pw / max(ph, 1) <= 1.8,
              f'{WM_PNG_REL}: keep the full source resolution (>= 700px wide, about 1.69:1); it is shown at up to 144px CSS wide and must stay crisp at 2x and 3x (got {pw}x{ph})')
        check(os.path.getsize(os.path.join(ROOT, WM_PNG_REL)) <= 80 * 1024,
              f'{WM_PNG_REL}: is {os.path.getsize(os.path.join(ROOT, WM_PNG_REL))} bytes; keep it under 80KB')
        if prows is not None:
            px = lambda x, y: tuple(prows[y][4 * x:4 * x + 4])
            check(all(px(x, y)[3] == 0 for x, y in ((0, 0), (pw - 1, 0), (0, ph - 1), (pw - 1, ph - 1))),
                  f'{WM_PNG_REL}: the four corners must be fully transparent (the white background was not removed)')
            check(all(prows[y][4 * x + 3] == 0 for y in list(range(8)) + list(range(ph - 8, ph)) for x in range(pw))
                  and all(prows[y][4 * x + 3] == 0 for y in range(ph) for x in list(range(8)) + list(range(pw - 8, pw))),
                  f'{WM_PNG_REL}: the padding around the logo must be fully transparent')
            if (pw, ph) == (725, 430):
                check(px(362, 225)[3] == 0, f'{WM_PNG_REL}: the gap between "Windermere" and "REAL ESTATE" must be transparent (a flat white fill was left)')
                # Solid interiors of each ink (black: the "W"; navy and grey: the diamond mark): fully opaque, in the exact ink color.
                for x, y, rgb in ((104, 201, (0, 0, 0)), (319, 68, (1, 26, 68)), (385, 48, (1, 26, 68)), (347, 53, (104, 105, 107)), (425, 52, (104, 105, 107))):
                    check(px(x, y) == rgb + (255,), f'{WM_PNG_REL}: the interior pixel at ({x}, {y}) should be opaque {rgb}, got {px(x, y)} (solid ink must stay fully opaque)')
            n_clear = sum(row[3::4].count(0) for row in prows)
            check(0.55 <= n_clear / (pw * ph) <= 0.95, f'{WM_PNG_REL}: {n_clear / (pw * ph):.0%} of the pixels are transparent; a logo on a transparent field should be mostly clear')
            # No recolor, no halo: every visible pixel is one of the three inks (only its alpha varies at anti-aliased edges).
            stray = sum(1 for row in prows for x in range(pw) if row[4 * x + 3] and tuple(row[4 * x:4 * x + 3]) not in WM_INKS)
            check(stray == 0, f'{WM_PNG_REL}: {stray} visible pixel(s) are not one of the logo\'s own ink colors (the mark must not be recolored; edges vary only in alpha)')

# ---------------- the placements: footer of every page, owners lockup, homepage line; never the header ----------------
FOOTER_FIRM_LINE = '<p class="mt-5 text-base">E. Berry Property Management &mdash; A Part of Windermere Vashon</p>'
HEADER_FIRM_LINE = '>A PART OF WINDERMERE VASHON</span>'
WM_IMG_RE = re.compile(r'<img\b[^>]*\bsrc="/images/brand/windermere-vashon-island\.png"[^>]*>')
EXPECT_WM_COUNT = {'index.html': 2, OWN_REL: 2}      # footer + (about line | owners lockup); every other page: the footer only
WM_HREF = 'https://www.windermerevashon.com/'          # the office's own website (Phase 12)
WM_LINK_RE = re.compile(r'<a\b([^>]*)>\s*(<img\b[^>]*\bsrc="/images/brand/windermere-vashon-island\.png"[^>]*>)\s*</a>')

def attrs_of(tag_attrs):
    """{name: value} of the attributes in an opening tag's attribute text (a bare attribute has the value '')."""
    return {m.group(1): m.group(2) or '' for m in re.finditer(r'([\w:-]+)(?:="([^"]*)")?', tag_attrs)}

def wm_links_ok(page):
    """(how many Windermere <img>s the page has, how many sit alone inside an <a> that is exactly a plain link to WM_HREF)."""
    good = 0
    for m in WM_LINK_RE.finditer(page):
        a = attrs_of(m.group(1))
        if a.get('href') == WM_HREF and set(a) <= {'href', 'class'} and 'target' not in a and 'rel' not in a and 'aria-label' not in a:
            good += 1
    return len(WM_IMG_RE.findall(page)), good
for rel in A11Y_PAGES:
    if not exists(rel):
        continue
    pg_ = read(rel)
    ftr_, hdr_ = shell_block(pg_, 'FOOTER') or '', shell_block(pg_, 'HEADER') or ''
    tags = WM_IMG_RE.findall(pg_)
    check(len(tags) == EXPECT_WM_COUNT.get(rel, 1),
          f'{rel}: the Windermere logo should appear {EXPECT_WM_COUNT.get(rel, 1)} time(s) (footer{", plus its placement" if rel in EXPECT_WM_COUNT else " only"}), found {len(tags)}')
    check(all(f'alt="{WM_ALT}"' in t for t in tags), f'{rel}: every Windermere logo needs alt="{WM_ALT}"')
    # Phase 12: every logo is wrapped by a plain <a href="https://www.windermerevashon.com/"> (no target, no rel, no aria-label: the alt names it)
    n_imgs, n_good = wm_links_ok(pg_)
    check(n_imgs == n_good == EXPECT_WM_COUNT.get(rel, 1),
          f'{rel}: every Windermere logo ({n_imgs}) must be the only content of a plain <a href="{WM_HREF}"> with no target, rel or aria-label (found {n_good} such link(s))')
    check(len(re.findall(r'<a\b[^>]*\bhref="https?://(?:www\.)?windermere[^"]*"', pg_)) == EXPECT_WM_COUNT.get(rel, 1)
          and all(h == WM_HREF for h in re.findall(r'<a\b[^>]*\bhref="(https?://(?:www\.)?windermere[^"]*)"', pg_)),
          f'{rel}: the only links to a Windermere site are the logo links, all to exactly {WM_HREF} (not windermere.com)')
    # Footer: one logo on its own Cream panel, directly after the (unchanged) firm line.
    check(len(WM_IMG_RE.findall(ftr_)) == 1, f'{rel}: EB:FOOTER must carry the Windermere logo once (edit index.html, then {RERUN})')
    pm = re.search(r'<div class="([^"]*)">\s*<a href="' + re.escape(WM_HREF) + r'" class="block">\s*(<img\b[^>]*\bsrc="/images/brand/windermere-vashon-island\.png"[^>]*>)\s*</a>\s*</div>', ftr_)
    check(pm is not None and 'bg-eb-cream' in pm.group(1).split() and 'rounded-card' in pm.group(1).split()
          and not re.search(r'\bbg-(?:white|black|eb-berry)\b', pm.group(1)),
          f'{rel}: the footer logo must be one link inside a flat Cream panel (bg-eb-cream rounded-card); the navy and black mark is illegible on Berry')
    pcls = pm.group(1).split() if pm else []
    check(pm is not None and 'w-32' in pcls and 'p-3' in pcls and 'max-w-full' in pcls and 'eb-cobrand-panel' in pcls
          and not any(c in pcls for c in ('p-4', 'p-5', 'p-6', 'w-40', 'w-36', 'w-44', 'w-48')) and not any(re.fullmatch(r'w-\[.*\]', c) for c in pcls),
          f'{rel}: the footer logo panel is w-32 (128px) with p-3 (so the logo is 104px), max-w-full and eb-cobrand-panel (for its Berry focus ring); found {pcls}')
    check(pm is not None and re.search(r'\bclass="block h-auto w-full"', pm.group(2)) is not None,
          f'{rel}: the footer logo fills the panel\'s content box (class "block h-auto w-full"), so its width follows the panel')
    check(FOOTER_FIRM_LINE in ftr_ and re.search(re.escape(FOOTER_FIRM_LINE) + r'\s*(?:<!--.*?-->\s*)?<div class="[^"]*\bbg-eb-cream\b', ftr_, re.S) is not None,
          f'{rel}: the footer firm line "E. Berry Property Management — A Part of Windermere Vashon" must be unchanged, with the logo panel right after it')
    # Header: the text line is the legal identification and stays; NO logo (at header size its lettering would be ~6px).
    check(HEADER_FIRM_LINE in hdr_ and 'A PART OF WINDERMERE VASHON' in hdr_, f'{rel}: the header firm-ID line "A PART OF WINDERMERE VASHON" must stay exactly as it is')
    hdr_imgs = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', hdr_)
    check(hdr_imgs == ['/images/brand/wordmark-berry.svg'] and 'windermere-vashon-island' not in hdr_ and not re.search(r'<img\b[^>]*\balt="[^"]*windermere', hdr_, re.I),
          f'{rel}: the header must hold only the E. Berry wordmark, NO Windermere logo (found {hdr_imgs}); the text line there is the legal identification')

# Focus ring (Phase 12): the footer's Cream logo panel sits inside the Berry footer, where the shell turns every focus ring Cream, which would
# vanish on Cream. The shell must switch the panel's link back to a Berry ring (the owners lockup card is an .eb-card, which already does).
shell_css = shell_block(index, 'SHELL-STYLES', r'</style>') or ''
check(re.search(r'\.bg-eb-berry \.eb-cobrand-panel a:focus-visible\s*\{\s*outline-color:\s*var\(--eb-berry\)', shell_css) is not None
      and re.search(r'\.bg-eb-berry \.eb-card :is\([^)]*\):focus-visible', shell_css) is not None,
      'index.html: EB:SHELL-STYLES must give the Windermere logo panel (.eb-cobrand-panel) and Cream cards on Berry a Berry focus ring (Cream on Cream is invisible)')

# Homepage: the "part of Windermere Vashon" line carries a modest logo (exactly w-28, 112px), linked, straight on the Cream field, copy unchanged.
about = (re.search(r'<section class="bg-eb-cream" aria-label="About Elijah">.*?</section>', index, re.S) or [''])[0]
check(bool(about), 'index.html: the About section (<section class="bg-eb-cream" aria-label="About Elijah">) is missing')
if about:
    check('Our property management work is part of Windermere Vashon.' in visible_text(about),
          'index.html: the line "Our property management work is part of Windermere Vashon." must stay as written')
    atags = WM_IMG_RE.findall(about)
    check(len(atags) == 1 and f'alt="{WM_ALT}"' in atags[0], f'index.html: the About section carries exactly one Windermere logo with alt="{WM_ALT}"')
    wclass = re.search(r'\bclass="([^"]*)"', atags[0]) if atags else None
    wnum = re.findall(r'(?<![\w:-])w-(\d+)(?![\w.-])', wclass.group(1)) if wclass else []
    check(wnum == ['28'], f'index.html: the homepage logo is a modest co-brand, exactly w-28 (112px) wide (found w-{wnum})')
    wrap = re.search(r'<div class="([^"]*)">\s*<p[^>]*>Our property management work[^<]*</p>\s*<a href="' + re.escape(WM_HREF) + r'"[^>]*>\s*<img\b[^>]*windermere-vashon-island\.png', about)
    check(wrap is not None and re.search(r'(?<![\w:-])bg-|\beb-field-|\beb-card\b', wrap.group(1)) is None,
          'index.html: the logo sits with the "part of Windermere Vashon" line, straight on the About section\'s Cream field (no color field or card behind the navy and black mark)')
check(len(WM_IMG_RE.findall(re.search(r'<main id="main">.*?</main>', index, re.S).group(0))) == 1,
      'index.html: <main> carries the Windermere logo exactly once (the About line); the footer has the other')

# Owners page: the "A part of Windermere Vashon" card is a co-brand lockup: E. Berry wordmark | divider | Windermere logo, plus the firm-ID line.
if exists(OWN_REL):
    op_ = read(OWN_REL)
    wind_ = (re.search(r'<section id="windermere".*?</section>', op_, re.S) or [''])[0]
    wm_pos = wind_.find('src="/images/brand/windermere-vashon-island.png"')
    eb_pos = wind_.find('src="/images/brand/wordmark-berry.svg"')
    rule_pos = wind_.find('eb-cobrand-rule')
    check(len(WM_IMG_RE.findall(wind_)) == 1 and f'alt="{WM_ALT}"' in (WM_IMG_RE.findall(wind_) or [''])[0],
          f'{OWN_REL}: the Windermere block carries the Windermere logo once, with alt="{WM_ALT}"')
    check('<img src="/images/brand/wordmark-berry.svg" alt="E. Berry"' in wind_, f'{OWN_REL}: the Windermere block lockup needs the E. Berry wordmark (the verbatim images/brand/wordmark-berry.svg)')
    check(0 < eb_pos < rule_pos < wm_pos, f'{OWN_REL}: the lockup runs E. Berry wordmark, then a divider (.eb-cobrand-rule), then the Windermere logo')
    check('>A PART OF WINDERMERE VASHON</p>' in wind_, f'{OWN_REL}: the lockup card keeps the uppercase firm-ID line "A PART OF WINDERMERE VASHON"')
    check(wind_.count('<div class="eb-card">') == 1 and 0 < wind_.find('<div class="eb-card">') < eb_pos,
          f'{OWN_REL}: the lockup is one Cream card (.eb-card) holding the wordmark, the divider and the logo')
    check(re.search(r'\.eb-cobrand-rule\s*\{[^}]*background:\s*var\(--eb-berry\)', op_) is not None and '@container' in op_,
          f'{OWN_REL}: the divider is a thin Berry rule, vertical or horizontal depending on the card width (page styles are missing)')
    # Phase 12 size: the lockup's Windermere logo is 9rem (144px) wide, and keeps its 7.5rem floor in the side-by-side layout
    check(re.search(r'\.eb-cobrand-logo\s*\{[^}]*\bwidth:\s*9rem\b', op_) is not None
          and re.search(r'@container[^{]*\{[^@]*\.eb-cobrand-logo\s*\{[^}]*\bflex:\s*0 1 9rem\b[^}]*\bmin-width:\s*7\.5rem\b', op_) is not None,
          f'{OWN_REL}: the lockup logo is 9rem (144px) wide, flex: 0 1 9rem with min-width: 7.5rem when side by side (found {re.findall(r"[.]eb-cobrand-logo[^}]*}", op_)})')
    check(re.search(r'<a href="' + re.escape(WM_HREF) + r'" class="eb-cobrand-logo block">\s*<img\b[^>]*windermere-vashon-island\.png[^>]*class="block h-auto w-full"', wind_) is not None,
          f'{OWN_REL}: the lockup logo is a plain link (class eb-cobrand-logo, the sized flex item) with the image filling it')
    owner_imgs = sorted(re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', (re.search(r'<main id="main">.*?</main>', op_, re.S) or [''])[0]))
    check(owner_imgs == sorted(['/images/brand/monogram-tangerine-bare.svg', '/images/brand/wordmark-berry.svg', WM_LOGO]),
          f'{OWN_REL}: the only images in <main> are the monogram, the E. Berry wordmark and the Windermere logo (found {owner_imgs})')
    check(all(s in BRAND_IMAGES for s in owner_imgs), f'{OWN_REL}: only E. Berry brand marks and {WM_LOGO} may appear (no stock photos)')

# =====================================================================
# E. Berry Phase 13: the legal pages (/fair-housing/, /privacy/, /accessibility/), the Equal Housing Opportunity mark, and the footer's legal row
#   Generated by tools/build_pages.py from tools/templates/{fair-housing,privacy,accessibility}.tmpl.html + legal.parts.tmpl.html.
#   EVIDENCE RULE: everything factual on these pages was read on a primary source (listed at the bottom of /fair-housing/). The lists below are
#   PINNED here, independently of build_pages.py, so an edit to the canonical lists in build_pages.py cannot slip through unnoticed. A fact that could
#   not be verified is left off the page, and the checks below keep it off: no deadlines, no fees or prices, no statistics, and no phone number that
#   is not in ALLOWED_VERIFIED_PHONES.
# =====================================================================
import datetime, importlib.util

sys.dont_write_bytecode = True      # importing build_pages must not leave a tools/__pycache__ behind
_spec = importlib.util.spec_from_file_location('build_pages', os.path.join(ROOT, 'tools', 'build_pages.py'))
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)

EHO_SVG = '/images/brand/equal-housing-opportunity.svg'
EHO_ALT = 'Equal Housing Opportunity'
LEGAL_PAGES = (('fair-housing', 'Fair housing', 'tools/templates/fair-housing.tmpl.html'),
               ('privacy', 'Privacy', 'tools/templates/privacy.tmpl.html'),
               ('accessibility', 'Accessibility', 'tools/templates/accessibility.tmpl.html'))
LEGAL_LINKS = [('/fair-housing/', 'Fair housing'), ('/privacy/', 'Privacy'), ('/accessibility/', 'Accessibility')]
FOOTER_LINKS = [('/listings/', 'Listings'), ('/buildings/courthouse-square/', 'Courthouse Square'), ('/owners/', 'For owners'),
                ('/technology/', 'Technology'), ('https://courthousesquarevashon.com/lease/', 'Lease documents'), ('mailto:me@ebberry.com', 'Email')]

# ---- the verified lists, pinned (sources: see the header comment above PROTECTED_CLASSES in tools/build_pages.py, all read 2026-10-18) ----
VERIFIED_CLASSES = {
    # HUD, "Fair Housing: Rights and Obligations" https://www.hud.gov/stat/fheo/rights-obligations ("...because of race, color, national origin, religion, sex, familial status, and disability")
    'federal': ['Race', 'Color', 'National origin', 'Religion', 'Sex', 'Familial status', 'Disability'],
    # RCW 49.60.222(1) https://app.leg.wa.gov/RCW/default.aspx?cite=49.60.222
    'washington': ['Sex', 'Marital status', 'Sexual orientation', 'Race', 'Creed', 'Color', 'National origin', 'Citizenship or immigration status',
                   'Families with children status', 'Honorably discharged veteran or military status',
                   'Presence of any sensory, mental, or physical disability',
                   'Use of a trained dog guide or service animal by a person with a disability'],
    # K.C.C. 12.20.040.A = "the protected classes as defined in K.C.C. chapter 3.12D" (3.12D.005.H) + "participation in the Section 8 program or other housing
    # subsidy program" + "alternative source of income"; 12.20.040.E adds "use of a service or assistive animal by an individual with a disability".
    # https://aqua.kingcounty.gov/council/clerk/code/15_Title_12.htm and .../06_Title_3.htm (compiled code UPDATED September 9, 2026).
    'king-county': ['Sex', 'Race', 'Color', 'National origin', 'Ethnicity', 'Religious affiliation', 'Disability', 'Sexual orientation',
                    'Gender identity or expression', 'Age (except by minimum age and retirement provisions)', 'Status as a family caregiver',
                    'Parental status', 'Marital status',
                    "Military status, or status as a veteran who was honorably discharged or who was discharged solely as a result of the person's "
                    "sexual orientation or gender identity or expression",
                    'Citizenship or immigration status', 'Participation in the Section 8 program or other housing subsidy program',
                    'Alternative source of income', 'Use of a service or assistive animal by an individual with a disability'],
}
# Phone numbers that may appear on the fair housing page, each READ on the agency's own page on 2026-10-18 (10 digits, no country code).
ALLOWED_VERIFIED_PHONES = {
    '8006699777': 'https://www.hud.gov/reporthousingdiscrimination',        # HUD FHEO: "Talk with an FHEO intake specialist by calling: 1-800-669-9777"
    '8002333247': 'https://www.hum.wa.gov/fair-housing',                    # Washington State Human Rights Commission: "please call us at 800-233-3247" (contact page: "Toll-Free: +1-800-233-3247")
    '2062632446': 'https://kingcounty.gov/en/dept/executive/governance-leadership/equity-social-justice/civil-rights-program',   # King County Civil Rights Program: "Phone: 206-263-2446 (TTY 7-1-1)"
}
# Every outside link the fair housing page may carry (all in <main>), each a primary source or an agency's own page.
FAIR_LINKS = {
    'https://www.hud.gov/stat/fheo/rights-obligations', 'https://www.hud.gov/reporthousingdiscrimination',
    'https://app.leg.wa.gov/RCW/default.aspx?cite=49.60.222', 'https://app.leg.wa.gov/RCW/default.aspx?cite=59.18.255',
    'https://app.leg.wa.gov/RCW/default.aspx?cite=59.18.257', 'https://aqua.kingcounty.gov/council/clerk/code/15_Title_12.htm',
    'https://aqua.kingcounty.gov/council/clerk/code/06_Title_3.htm',
    'https://kingcounty.gov/en/dept/local-services/governance-leadership/local-government-for-unincorporated-king-county/community-service-areas',
    'https://www.hum.wa.gov/fair-housing',
    'https://kingcounty.gov/en/dept/executive/governance-leadership/equity-social-justice/civil-rights-program',
}
PRIVACY_LINKS = {'https://docs.netlify.com/manage/forms/submissions/', 'https://docs.netlify.com/manage/forms/notifications/',
                 'https://www.netlify.com/privacy/', 'https://policies.google.com/privacy'}
# Words and shapes that would turn a notice into a price list, a promise, or a statistic. (The pages quote no deadline either: each agency states its own.)
LEGAL_FORBIDDEN = (
    ('a fee, rate, price, deposit or charge', r'\$|\d\s*%|\bpercent\b|\bfees?\b|\brates?\b|\bpric(?:e|es|ed|ing)\b|\bcommissions?\b|\bdeposits?\b|\bcharges?\b|\bfree\b|/\s*(?:mo|month|yr|year)\b|\bper\s+(?:month|year)\b'),
    ('a deadline or time limit in numbers', r'\b\d+\s+(?:days?|weeks?|months?|years?)\b|\b(?:one|two|six|twelve)\s+(?:years?|months?)\b'),
    ('a headline statistic', r'\b\d[\d,]*\+?\s+(?:tenants|owners|renters|families|complaints|cases|applicants|properties|units|buildings|customers|users|visitors)\b|\b24\s*/\s*7\b'),
    ('a testimonial (none exist; never fabricate one)', r'testimonial|\bstars?\b|★|\bfive-star\b'),
)
PHONE_RE = re.compile(r'(?<![\d.])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?![\d])')

def phones_in(text):
    """Normalized 10-digit phone numbers found in `text`."""
    out = set()
    for m in PHONE_RE.finditer(text):
        d = re.sub(r'\D', '', m.group(0))
        out.add(d[1:] if len(d) == 11 and d[0] == '1' else d)
    return out

def main_of(page):
    return (re.search(r'<main id="main">.*?</main>', page, re.S) or [''])[0]

def external_hrefs(markup):
    return set(re.findall(r'<a\b[^>]*\bhref="(https?://[^"]+)"', markup))

def list_items(page, attr, name):
    """The <li> texts of <ul ... data-<attr>="<name>"> on a page, entities decoded."""
    m = re.search(r'<ul\b[^>]*\bdata-' + attr + r'="' + re.escape(name) + r'"[^>]*>(.*?)</ul>', page, re.S)
    return [visible_text(x) for x in re.findall(r'<li\b[^>]*>(.*?)</li>', m.group(1), re.S)] if m else None

# ---- the footer of every page: the EHO mark, the unchanged six links, the quiet legal row ----
for rel in A11Y_PAGES:
    if not exists(rel):
        continue
    pg_ = read(rel)
    ftr_, hdr_ = shell_block(pg_, 'FOOTER') or '', shell_block(pg_, 'HEADER') or ''
    eho = re.findall(r'<img\b[^>]*\bsrc="' + re.escape(EHO_SVG) + r'"[^>]*>', ftr_)
    check(len(eho) == 1 and f'alt="{EHO_ALT}"' in eho[0], f'{rel}: EB:FOOTER must carry the Equal Housing Opportunity mark exactly once, with alt="{EHO_ALT}" (edit index.html, then {RERUN}); found {len(eho)}')
    ecls = (re.search(r'\bclass="([^"]*)"', eho[0]) or ['', ''])[1].split() if eho else []
    check('h-12' in ecls and not any(re.fullmatch(r'h-(?:1[4-9]|[2-9]\d|\[.*\])', c) for c in ecls),
          f'{rel}: the footer EHO mark is modest: h-12 (48px; the brief allows about 44-56px), found classes {ecls}')
    panel = re.search(r'<div class="eb-cobrand-panel[^"]*">.*?</div>', ftr_, re.S)
    check(panel is not None and 'equal-housing' not in panel.group(0).lower() and 'Equal Housing' not in panel.group(0),
          f'{rel}: the EHO mark must not be inside the Windermere co-brand panel')
    check(re.search(re.escape(eho[0]) + r'\s*<p class="text-sm" aria-hidden="true">Equal Housing Opportunity</p>', ftr_) is not None if eho else False,
          f'{rel}: the footer EHO mark has the words "Equal Housing Opportunity" beside it (aria-hidden: the image alt already says them)')
    check(0 < ftr_.find('eb-cobrand-panel') < ftr_.find(EHO_SVG) < ftr_.find('<nav aria-label="Footer">'),
          f'{rel}: the footer order is Windermere panel, then the EHO mark, then the link row')
    navs = {m.group(1): re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', m.group(2))
            for m in re.finditer(r'<nav aria-label="([^"]+)">(.*?)</nav>', ftr_, re.S)}
    check(navs.get('Footer') == FOOTER_LINKS, f'{rel}: the six footer links must stay unchanged and in order (found {navs.get("Footer")})')
    check(navs.get('Legal') == LEGAL_LINKS, f'{rel}: the footer legal row must be exactly Fair housing, Privacy, Accessibility with hrefs /fair-housing/, /privacy/, /accessibility/ (found {navs.get("Legal")})')
    check('<ul class="flex flex-wrap gap-x-5 gap-y-1 text-sm">' in (re.search(r'<nav aria-label="Legal">.*?</nav>', ftr_, re.S) or [''])[0],
          f'{rel}: the legal row is text-sm, quieter than the main link row (text-base)')
    check(EHO_SVG not in hdr_ and not any(h in hdr_ for h, _ in LEGAL_LINKS) and 'Legal' not in hdr_,
          f'{rel}: the header stays as it was: no EHO mark and no legal links in it (the nav is Homes, Commercial, For owners, Technology + Inquire)')

# ---- the mark itself: images/brand/equal-housing-opportunity.svg ----
EHO_REL = 'images/brand/equal-housing-opportunity.svg'
check(exists(EHO_REL), f'{EHO_REL} is missing (the Equal Housing Opportunity mark)')
if exists(EHO_REL):
    svg = read(EHO_REL)
    try:
        svg_root = ET.fromstring(svg)
    except ET.ParseError:
        svg_root = None
    check(svg_root is not None and svg_root.tag.endswith('svg') and svg_root.get('viewBox') == '0 0 288 305', f'{EHO_REL}: must be a valid SVG with viewBox "0 0 288 305" (the proportions of HUD\'s artwork)')
    check('currentColor' in svg and not re.search(r'fill="(?!currentColor|none)[^"]*"|stroke="(?!currentColor|none)[^"]*"', svg), f'{EHO_REL}: every fill and stroke is currentColor')
    check(svg_root is not None and svg_root.get('color') == '#F1ECE9', f'{EHO_REL}: the root color is Cream (#F1ECE9): an <img> cannot inherit the page color, so the file carries its own')
    check(re.search(r'gradient|shadow|filter|#fff\b|#ffffff\b|#000\b|#000000\b|\bwhite\b|\bblack\b', svg, re.I) is None, f'{EHO_REL}: flat brand: no gradient, shadow, filter, white or black')
    check('<title' in svg and EHO_ALT in svg and len(svg) <= 16 * 1024, f'{EHO_REL}: has its <title> and stays small (<= 16KB; {len(svg)} bytes)')
    check(svg.count('<rect') == 2 and svg.count('<path') == 3, f'{EHO_REL}: the house outline, the two bars of the equals sign and the two lines of lettering (found {svg.count("<rect")} rects, {svg.count("<path")} paths)')

# ---- the three pages ----
today = datetime.date.today().isoformat()
check(re.fullmatch(r'\d{4}-\d{2}-\d{2}', bp.LEGAL_DATE) is not None and bp.LEGAL_DATE <= today, f'build_pages.LEGAL_DATE {bp.LEGAL_DATE!r} must be a real date that is not in the future')
for slug, h1_text, tmpl in LEGAL_PAGES:
    rel = f'{slug}/index.html'
    for r_ in (tmpl, rel):
        check(exists(r_), f'{r_} is missing ({RERUN})')
    if not exists(rel):
        continue
    pg = read(rel)
    main_ = main_of(pg)
    title = f'{h1_text} — E. Berry Property Management'
    check_shell(rel, pg, RERUN)
    check('A PART OF WINDERMERE VASHON' in pg, f"{rel}: header is missing the 'A PART OF WINDERMERE VASHON' firm-ID line")
    check(f'<title>{title}</title>' in pg, f'{rel}: <title> is not {title!r}')
    check(f'<link rel="canonical" href="{SITE_URL}/{slug}/" />' in pg, f'{rel}: canonical URL is not {SITE_URL}/{slug}/')
    check('<meta name="robots" content="index, follow" />' in pg and 'noindex' not in pg, f'{rel}: must be indexable: <meta name="robots" content="index, follow" />, no noindex')
    check('name="description"' in pg and f'property="og:url" content="{SITE_URL}/{slug}/"' in pg and f'property="og:title" content="{title}"' in pg and 'name="twitter:card"' in pg,
          f'{rel}: missing meta description or Open Graph / Twitter tags')
    m = re.search(r'property="og:image" content="https://eberryvashon\.com(/[^"]+)"', pg)
    check(m is not None and exists(m.group(1).lstrip('/')), f'{rel}: og:image must be an absolute eberryvashon.com URL of a file that exists')
    desc = (re.search(r'name="description" content="([^"]*)"', pg) or ['', ''])[1]
    check(40 <= len(desc) <= 200 and re.search(r"\b(?:I|I'm|I'd|my|me)\b", _html.unescape(desc)) is not None, f'{rel}: the meta description is in the owner\'s voice ("I") and a sensible length ({len(desc)} characters)')
    # structured data: a WebPage by the RealEstateAgent; never an offer, price, rating or review
    mld = re.search(r'<script type="application/ld\+json">(.*?)</script>', pg, re.S)
    try:
        ld = json.loads(mld.group(1)) if mld else None
    except ValueError:
        ld = None
    def _keys(o):
        if isinstance(o, dict):
            return set(o) | {k for v in o.values() for k in _keys(v)}
        if isinstance(o, list):
            return {k for v in o for k in _keys(v)}
        return set()
    check(isinstance(ld, dict) and ld.get('@type') == 'WebPage' and ld.get('url') == f'{SITE_URL}/{slug}/' and ld.get('name') == h1_text
          and isinstance(ld.get('publisher'), dict) and ld['publisher'].get('@type') == 'RealEstateAgent'
          and ld['publisher'].get('parentOrganization', {}).get('name') == 'Windermere Vashon' and ld.get('dateModified') == bp.LEGAL_DATE,
          f'{rel}: JSON-LD is missing/invalid (a WebPage "{h1_text}" at /{slug}/, published by the RealEstateAgent, part of Windermere Vashon, dateModified {bp.LEGAL_DATE})')
    check(not (_keys(ld) & {'offers', 'price', 'priceRange', 'priceCurrency', 'aggregateRating', 'review', 'ratingValue'}), f'{rel}: JSON-LD must not carry offers, prices, ratings or reviews')
    # structure: one h1 with the highlighted-word device once, sections labelled by their headings
    h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', pg, re.S)
    check(len(h1s) == 1 and visible_text(h1s[0]) == h1_text, f'{rel}: the h1 is "{h1_text}" (found {[visible_text(x) for x in h1s]})')
    check(len(re.findall(r'<span class="eb-hl eb-hl-mustard">', main_)) == 1, f'{rel}: the highlighted-word device is used once, in the h1')
    check(all(re.search(rf'id="{re.escape(i)}"', main_) for i in re.findall(r'aria-labelledby="([^"]+)"', main_)), f'{rel}: every section\'s aria-labelledby points at a heading that exists')
    # nothing a notice should not have
    check('<form' not in pg and '<table' not in pg and '<blockquote' not in pg, f'{rel}: no form, table or testimonial on a legal page')
    imgs = re.findall(r'<img [^>]*\bsrc="([^"]+)"', main_)
    check(all(src in (BRAND_IMAGES | {EHO_SVG}) for src in imgs), f'{rel}: the only images are the brand SVGs and the EHO mark (found {imgs})')
    check(re.search(r'cdn', pg, re.I) is None, f'{rel}: mentions a CDN; vendor it instead')
    hosts = set()
    for tag in re.findall(r'<(?:script|link)\b[^>]*>', pg):
        mh = re.search(r'\b(?:src|href)="https?://([^/"]+)', tag)
        if mh and 'rel="canonical"' not in tag:
            hosts.add(mh.group(1))
    check(hosts <= {'fonts.googleapis.com', 'fonts.gstatic.com'}, f'{rel}: external script/stylesheet hosts {sorted(hosts)}; only Google Fonts allowed')
    for label, pat in FLAT_BRAND:
        check(re.search(pat, pg, re.I) is None, f'{rel}: contains {label} (E. Berry brand is flat, Berry/Cream only)')
    metas_ = ' '.join(re.findall(r'<meta [^>]*\bcontent="([^"]*)"', pg))
    claims = ' '.join([visible_text(pg), _html.unescape(metas_), mld.group(1) if mld else '']).replace('Human Rights Commission', 'Human Rights Agency')   # (an agency's name, not a sales commission)
    for what, pat in LEGAL_FORBIDDEN:
        mm = re.search(pat, claims, re.I)
        check(mm is None, f'{rel}: contains {what} ({mm.group(0) if mm else ""!r} in ...{claims[max(0, (mm.start() if mm else 0) - 40):(mm.end() if mm else 0) + 40]}...)')
        tt = re.sub(r'\$[a-z_]+', ' ', visible_text(read(tmpl))) if exists(tmpl) else ''
        mm = re.search(pat, tt, re.I)
        check(mm is None, f'{tmpl}: contains {what} ({mm.group(0) if mm else ""!r})')
    check(re.search(r'\bI\b', visible_text(main_)) is not None and re.search(r"(?<![\w'])we(?![\w'])|\bour\b|\bus\b", visible_text(main_), re.I) is None,
          f'{rel}: the owner\'s voice: first person singular ("I"), never "we"')

# ---- /fair-housing/ ----
FH = 'fair-housing/index.html'
if exists(FH):
    fp = read(FH); fmain = main_of(fp); ftext = visible_text(fmain)
    # the canonical lists: pinned here, rendered from ONE list in build_pages.py, and every item on the page
    canon = {c['key']: c['items'] for c in bp.PROTECTED_CLASSES}
    check(canon == VERIFIED_CLASSES, 'tools/build_pages.py PROTECTED_CLASSES differs from the verified lists pinned in tools/check_site.py: '
          + '; '.join(f'{k}: missing {[i for i in VERIFIED_CLASSES[k] if i not in canon.get(k, [])]} extra {[i for i in canon.get(k, []) if i not in VERIFIED_CLASSES[k]]}' for k in VERIFIED_CLASSES if canon.get(k) != VERIFIED_CLASSES[k])
          + ' (change the pin only after reading the law again)')
    for key, items in VERIFIED_CLASSES.items():
        on_page = list_items(fp, 'protected', key)
        check(on_page == items, f'{FH}: the "{key}" protected-class list is not the verified list (missing {[i for i in items if i not in (on_page or [])]}, extra {[i for i in (on_page or []) if i not in items]})')
        check(all(i in ftext for i in items), f'{FH}: every {key} class is on the page')
    check(len(re.findall(r'data-protected="', fp)) == 3, f'{FH}: exactly three protected-class lists (federal, Washington, King County)')
    check('Alternative source of income' in (list_items(fp, 'protected', 'king-county') or []) and 'Participation in the Section 8 program or other housing subsidy program' in (list_items(fp, 'protected', 'king-county') or []),
          f'{FH}: the King County list carries both source-of-income protections the code names')
    check(not any(w in ftext for w in ('Ancestry', 'ancestry', 'Gender identity/expression')), f'{FH}: "ancestry" is not in the current King County code (it was in Ord. 18708 of 2018); list only what the code now says')
    # the voice and the commitments
    check('Every home I manage is offered to everyone on the same terms.' in ftext
          and 'I follow federal, Washington and King County fair housing law' in ftext, f'{FH}: the plain first-person commitment is missing')
    check(all(s in ftext for s in ('I welcome housing choice vouchers and every other lawful source of income.', 'off the monthly rent first', 'RCW 59.18.255(3)', 'RCW 59.18.255(2)')),
          f'{FH}: the source-of-income paragraph (vouchers welcome; subsidies come off the rent first, RCW 59.18.255(3); no advertised preference, (2)) is missing')
    check('Ask me and we\'ll work it out.' in ftext and 'RCW 49.60.222(2)' in ftext and 'K.C.C. 12.20.040.E' in ftext, f'{FH}: the accommodations paragraph (cited, "ask me and we\'ll work it out") is missing')
    scr = re.search(r'<h2 id="screening-heading".*?</h2>\s*<p[^>]*>(.*?)</p>', fmain, re.S)
    check(scr is not None and visible_text(scr.group(1)).startswith('I use the same written criteria for every applicant, and I share them in writing before I pull any screening report') and 'RCW 59.18.257' in visible_text(scr.group(1))
          and len(re.findall(r'[.!?](?:\s|$)', visible_text(scr.group(1)))) == 1, f'{FH}: the screening paragraph is one sentence citing RCW 59.18.257')
    check('me@ebberry.com' in ftext and 'href="mailto:me@ebberry.com"' in fmain, f'{FH}: "me first": the page sends concerns to me@ebberry.com')
    check(ftext.find('me@ebberry.com') < ftext.find('HUD: Office of Fair Housing') < ftext.find('Washington State Human Rights Commission') < ftext.find('King County Civil Rights Program'), f'{FH}: me first, then HUD, the Washington Human Rights Commission, and the King County Civil Rights Program')
    # outside links: exactly the verified sources and agencies; phone numbers only the verified ones
    ext = external_hrefs(fmain)
    check(ext == FAIR_LINKS, f'{FH}: outside links must be exactly the verified sources and agencies (extra {sorted(ext - FAIR_LINKS)}, missing {sorted(FAIR_LINKS - ext)})')
    check(all('href="' + a['url'] + '"' in fmain for a in bp.AGENCIES) and len(bp.AGENCIES) == 3, f'{FH}: each agency\'s website is linked')
    tels = set(re.findall(r'href="tel:\+?([\d-]+)"', fp))
    found = phones_in(ftext) | {re.sub(r'\D', '', t)[1:] if re.sub(r'\D', '', t).startswith('1') and len(re.sub(r'\D', '', t)) == 11 else re.sub(r'\D', '', t) for t in tels}
    check(found <= set(ALLOWED_VERIFIED_PHONES), f'{FH}: phone number(s) not in ALLOWED_VERIFIED_PHONES (read on the agency\'s own page): {sorted(found - set(ALLOWED_VERIFIED_PHONES))}')
    check(set(ALLOWED_VERIFIED_PHONES) <= found, f'{FH}: a verified agency phone number is missing from the page ({sorted(set(ALLOWED_VERIFIED_PHONES) - found)})')
    check(set(ALLOWED_VERIFIED_PHONES) == {re.sub(r'\D', '', a['phone'])[-10:] for a in bp.AGENCIES}, 'tools/build_pages.py AGENCIES phones differ from ALLOWED_VERIFIED_PHONES')
    check(phones_in(re.sub(r'\$[a-z_]+', ' ', visible_text(read(LEGAL_PAGES[0][2])))) == set(), f'{LEGAL_PAGES[0][2]}: no phone number may be typed into the template (they come from AGENCIES, which must match ALLOWED_VERIFIED_PHONES)')
    check(phones_in(visible_text(read('tools/templates/legal.parts.tmpl.html'))) == set(), 'tools/templates/legal.parts.tmpl.html: no phone number may be typed into a partial')
    # the EHO mark on this page too (the footer has one of its own)
    check(re.findall(r'<img [^>]*\bsrc="([^"]+)"', fmain) == [EHO_SVG] and f'alt="{EHO_ALT}"' in fmain, f'{FH}: the Equal Housing Opportunity mark appears once in the page itself (the hero), with alt="{EHO_ALT}"')
    secs = [fp.find(f'id="{i}"') for i in ('protected', 'income', 'how-i-rent', 'concerns', 'sources')]
    check(all(i > 0 for i in secs) and secs == sorted(secs), f'{FH}: sections must run protected, income, how-i-rent, concerns, sources')
    # no claim the evidence could not support: the "no pet fee for assistance animals" line stays off until a current rule can be cited
    check(re.search(r'pet\b|\banimals? (?:are|is) welcome without', ftext, re.I) is None, f'{FH}: no pet-policy promise (HUD rescinded the no-fee assistance-animal notice in 2025; nothing current could be verified)')
    check({u for _, u in bp.LEGAL_SOURCES} <= FAIR_LINKS and {a['url'] for a in bp.AGENCIES} <= FAIR_LINKS, 'tools/build_pages.py LEGAL_SOURCES or AGENCIES holds a URL that is not in FAIR_LINKS')
    check(bp.long_date(bp.LEGAL_DATE) in ftext, f'{FH}: says when the sources were checked ({bp.long_date(bp.LEGAL_DATE)})')

# ---- /privacy/ ----
def form_labels_in(markup, name):
    m = re.search(r'<form\b[^>]*\bname="' + re.escape(name) + r'"[^>]*>(.*?)</form>', markup, re.S)
    if not m:
        return None
    raw = re.findall(r'<span class="mb-1\.5 block text-base font-medium">(.*?)</span>\s*<(?:input|select|textarea)\b', m.group(1), re.S)
    return [re.sub(r'\s*\*$', '', visible_text(r)) for r in raw]

def hidden_fields_in(markup, name):
    m = re.search(r'<form\b[^>]*\bname="' + re.escape(name) + r'"[^>]*>(.*?)</form>', markup, re.S)
    return sorted(re.findall(r'<input type="hidden" name="([^"]+)"', m.group(1))) if m else None

PV = 'privacy/index.html'
if exists(PV):
    vp = read(PV); vmain = main_of(vp); vtext = visible_text(vmain)
    form_sources = {'inquiry': ['index.html', 'buildings/courthouse-square/index.html'],
                    'listing-inquiry': ['listings/chs-n101/index.html', 'tools/templates/listing.tmpl.html', 'listing.html'],
                    'owner-intro': [OWN_REL, 'tools/templates/owners.tmpl.html']}
    # js/listing-detail.js draws the same listing form in the browser; its labels are in a template literal
    for name, sources in form_sources.items():
        got = [form_labels_in(read(s_), name) for s_ in sources if exists(s_) and s_ != 'listing.html']
        got.append(form_labels_in(read('js/listing-detail.js'), name) if name == 'listing-inquiry' else got[0])
        check(got[0] is not None and all(g == got[0] for g in got), f'{name}: the form\'s field labels differ between its pages/templates ({got}); the privacy notice describes one list')
        page_list = list_items(vp, 'form', name)
        check(page_list is not None and page_list == got[0], f'{PV}: the "{name}" form\'s fields on the privacy page must be exactly the labels in the form\'s markup (page {page_list}, form {got[0]})')
    check(len(re.findall(r'data-form="', vp)) == 3 and set(form_names) >= {'inquiry', 'listing-inquiry', 'owner-intro'}, f'{PV}: exactly three form lists, and the site has those three forms (found {sorted(form_names)})')
    # the hidden fields the notice mentions are the ones the forms really carry
    hid = {n: hidden_fields_in(read('index.html' if n == 'inquiry' else 'tools/templates/listing.tmpl.html' if n == 'listing-inquiry' else OWN_REL), n) for n in form_sources}
    check(hid == {'inquiry': ['form-name'], 'listing-inquiry': ['building', 'form-name', 'listing'], 'owner-intro': ['form-name']}, f'the forms\' hidden fields changed ({hid}); update the privacy notice\'s notes about them')
    check(hidden_fields_in(read('buildings/courthouse-square/index.html'), 'inquiry') == ['building', 'form-name'], 'the Courthouse Square page\'s inquiry form carries a hidden building field (the privacy notice says so)')
    check('which building page you wrote from' in vtext and 'which listing and building you asked about' in vtext, f'{PV}: the notes about the hidden building and listing fields are missing')
    # where it goes, what it does not do, the one outside request, links out
    check(all(s in vtext for s in ('Netlify', 'stores your submission', 'emails it to me', "I don't sell it", 'I use it to write back to you')), f'{PV}: where the data goes (Netlify stores it and emails it to me; used only to write back; not sold) is missing')
    check(external_hrefs(vmain) == PRIVACY_LINKS, f'{PV}: outside links must be exactly Netlify\'s and Google\'s own pages (found {sorted(external_hrefs(vmain))}); no portal URL is ever linked')
    gf = re.search(r'family=Fraunces[^"]*family=Inter[^"]*family=Anton', index)
    check(gf is not None and 'Fraunces, Inter and Anton come from Google Fonts' in vtext and 'includes your IP address' in vtext, f'{PV}: the one outside request is the Google Fonts typefaces (Fraunces, Inter and Anton), and says Google receives your IP address')
    check('windermerevashon.com' in vtext and 'courthousesquarevashon.com' in vtext and 'openstreetmap.org' in vtext and 'covers eberryvashon.com only' in vtext, f'{PV}: the links out (Windermere, Lease documents, OpenStreetMap) and the scope line are missing')
    check('Ledger' in vtext and 'separate system' in vtext and 'privacy notice is shown inside the portal' in vtext and not re.search(r'https?://[^\s"]*(?:ledger|portal|app\.)', vmain, re.I), f'{PV}: Ledger is a separate system with its own notice; no portal URL is linked')
    check('me@ebberry.com' in vtext and "tell me and I'll delete it" in vtext and not re.search(r'retain|retention|\bkeep\b.*\bdays\b', vtext, re.I), f'{PV}: "your choices" is "on request" (see it, or have it deleted), with no retention period promised')
    check(f"It's effective {bp.long_date(bp.LEGAL_DATE)}." in vtext, f'{PV}: the effective date must be {bp.long_date(bp.LEGAL_DATE)}')

# ---- /accessibility/ ----
AC = 'accessibility/index.html'
if exists(AC):
    ap_ = read(AC); amain = main_of(ap_); atext = visible_text(amain)
    check(external_hrefs(amain) == {'https://www.w3.org/TR/WCAG21/'}, f'{AC}: the only outside link is the W3C\'s WCAG 2.1 (found {sorted(external_hrefs(amain))})')
    check('WCAG 2.1' in atext and 'level AA' in atext and re.search(r'\bconform|\bcompl(?:y|iant|iance)\b|fully accessible', atext, re.I) is None, f'{AC}: the target is WCAG 2.1 level AA, stated as a target (no claim of conformance)')
    tiles = [visible_text(t) for t in re.findall(r'<h3[^>]*>(.*?)</h3>', (re.search(r'<section id="checks".*?</section>', amain, re.S) or [''])[0], re.S)]
    check(tiles == ['Structure', 'Names', 'Keyboard', 'Contrast', 'Less motion', 'Small screens'], f'{AC}: "What the site checks" is the six things part Q asserts (found {tiles})')
    check(f'This statement is dated {bp.long_date(bp.LEGAL_DATE)}.' in atext, f'{AC}: the statement date must be {bp.long_date(bp.LEGAL_DATE)}')
    check(all(s in atext for s in ('Windermere', 'Netlify', 'Stripe', 'courthousesquarevashon.com', 'me@ebberry.com', "I'll fix what I can and write back")), f'{AC}: known limits (Windermere, Netlify, Stripe, Ledger and the lease site) and the way to tell me are missing')
    # every claim has a test behind it: part Q of tools/test_listings.py asserts these things
    tl = read('tools/test_listings.py')
    for token in ("exactly one {lm} landmark", 'accessible name', 'heading levels never skip', 'the first Tab stop is the skip link', 'focus rings', 'contrast', 'scroll-behavior is', "{'width': 390", 'sideways scroll'):
        check(token in tl, f'tools/test_listings.py: part Q no longer asserts "{token}", but {AC} says the site checks it')
    # "the map has a list equivalent" and "without JavaScript": verified in the markup
    lp = read(LIST_REL)
    nos = re.findall(r'<noscript>(.*?)</noscript>', lp, re.S)
    nos_all = ' '.join(nos)
    check(all(f'href="/listings/{L.get("id")}/"' in nos_all for L in listings), f'{LIST_REL}: the <noscript> list must link every listing in data/listings.json ({AC} says that with JavaScript off the Listings page shows everything that is open)')
    check('id="listing-grid"' in lp and 'id="map"' in lp, f'{LIST_REL}: the map and the list of cards are both on the page')
    ebm_ = read('js/eb-map.js')
    check("e.key === 'Enter' || e.key === ' '" in ebm_ and "setAttribute('role', 'button')" in ebm_ and "'tabindex'" in tl, f'js/eb-map.js: map pins must be keyboard buttons (Enter or Space opens them, and part E asserts tabindex 0); {AC} says so')
    check(not re.search(r'<script[^>]*>[^<]*(?:fetch|XMLHttpRequest)', read('listings/chs-n101/index.html')), 'listings/chs-n101/index.html: a generated listing page is static HTML that reads nothing from the network (it works with JavaScript off)')

# ---- the site sets no cookies and loads no analytics, advertising or tracking code, and asks no host but Google Fonts for anything ----
TRACK_RE = re.compile(r'document\.cookie|\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|sendBeacon|\bgtag\s*\(|google-analytics|googletagmanager|\bga\s*\(\s*[\'"]|analytics\.js|plausible|\bfbq\s*\(|hotjar|matomo|mixpanel|\b_paq\b|umami|fathom|clarity\.ms|newrelic|sentry|doubleclick\.net|adsbygoogle|facebook\.net|segment\.(?:com|io)', re.I)
site_files = []
for dirpath, dirs, files_ in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ('.git', '.claude', 'node_modules', 'lease', 'tools', 'review', 'fonts', 'images', 'data', '__pycache__')]
    for fn in files_:
        rel_ = os.path.relpath(os.path.join(dirpath, fn), ROOT)
        if fn.endswith(('.html', '.js')) and rel_ != 'js/lease-builder.js' and not rel_.endswith('tailwind.css'):
            site_files.append(rel_)
check(len(site_files) >= 20, f'the privacy scan looked at {len(site_files)} pages and scripts (expected 20 or more)')
for rel_ in site_files:
    t_ = read(rel_)
    hit = TRACK_RE.search(t_)
    check(hit is None, f'{rel_}: cookie, storage, analytics, advertising or tracking code ({hit.group(0) if hit else ""!r}); the privacy notice says the site has none')
    if rel_.endswith('.html'):
        outside = [u for u in re.findall(r'<(?:script|img|iframe|source|video|audio|embed|object)\b[^>]*\b(?:src|data)="(https?://[^"]+)"', t_)]
        outside += [u for tag in re.findall(r'<link\b[^>]*>', t_) if 'rel="canonical"' not in tag for u in re.findall(r'\bhref="(https?://[^"]+)"', tag) if not re.match(r'https://fonts\.(?:googleapis|gstatic)\.com(?:/|$)', u)]
        check(not outside, f'{rel_}: asks a host other than Google Fonts for a script, image, frame or stylesheet ({outside[:2]}); the privacy notice says that is the only outside request')
    else:
        if not rel_.startswith('js/vendor/'):       # (the vendored map libraries are third-party code; the tests run them with the network sealed)
            check(re.search(r'fetch\(\s*[\'"`]https?:|XMLHttpRequest|new\s+WebSocket|new\s+EventSource', t_) is None,
                  f'{rel_}: reaches out to another host from script; the privacy notice says the pages ask no one but Google Fonts')
ms = read('map/style.json')
check('pmtiles://' in ms and re.search(r'https?://', ms) is None, 'map/style.json: the basemap tiles come from this site (a pmtiles:// archive), not another host; the privacy notice says the map stays here')

# ---- plumbing: Tailwind sees the pages, the E2E workflow runs for them, the README says what they are and what must happen before launch ----
for glob_ in ('./fair-housing/**/*.html', './privacy/**/*.html', './accessibility/**/*.html'):
    check(glob_ in tw_cfg, f'tailwind.config.js content[] does not include {glob_}')
if exists('.github/workflows/listings-e2e.yml'):
    wf = read('.github/workflows/listings-e2e.yml')
    for d in ('fair-housing', 'privacy', 'accessibility'):
        check(wf.count(f"'{d}/**'") == 2, f".github/workflows/listings-e2e.yml: expected '{d}/**' under both push and pull_request paths")
tw_css = read('css/tailwind.css')
for cls in (r'h-12', r'h-24', r'sm\:h-28', r'list-disc', r'space-y-1\.5', r'pl-5', r'gap-x-5', r'sm\:items-end', r'items-end', r'border-b-\[1\.5px\]', r'first\:pt-0', r'last\:pb-0', r'last\:border-b-0',
            r'text-\[length\:clamp\(2\.5rem\2c 10\.5vw\2c 8rem\)\]'):
    check('.' + cls in tw_css, f"css/tailwind.css has no .{cls}; rebuild it (see README, 'Rebuilding the stylesheet')")
rd = read('README.md')
check('/fair-housing/' in rd and '/privacy/' in rd and '/accessibility/' in rd and re.search(r'designated broker.{0,200}/fair-housing/|/fair-housing/.{0,300}designated broker', rd, re.S) is not None,
      'README.md: needs the legal-pages section and the "Before launch" item that has the designated broker review /fair-housing/ with the firm-name lines')
check('equal-housing-opportunity.svg' in read('images/brand/README.md'), 'images/brand/README.md: must say where the Equal Housing Opportunity mark came from and how to use it')

# ---------------- verdict ----------------
if problems:
    print(f"FAIL: {len(problems)} problem(s) out of {checks} checks")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print(f"OK: {checks} checks passed")
if placeholder_note:
    print(f"note: {placeholder_note}")
if approval_note:
    print(f"note: {approval_note}")
print("note: generated pages are verified separately; run `python3 tools/build_pages.py --check` (also a CI step) to prove buildings/ and sitemap.xml are not stale")
