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

def check_shell(rel, page, fix):
    """The page's EB:HEADER, EB:FOOTER and EB:SHELL-STYLES blocks must equal index.html's, byte for byte."""
    for name, end in (('HEADER', None), ('FOOTER', None), ('SHELL-STYLES', r'</style>')):
        a, b = shell_block(index, name, end), shell_block(page, name, end)
        check(a is not None and a == b, f"{rel}: EB:{name} block differs from index.html ({fix})")

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
    wanted = [f'{SITE_URL}/', f'{SITE_URL}/listings/']
    wanted += [f"{SITE_URL}/listings/{L.get('id')}/" for L in listings]
    wanted += [f"{SITE_URL}/buildings/{B.get('id')}/" for B in buildings]
    for u in wanted:
        check(u in sm_urls, f"sitemap.xml: missing {u} ({RERUN})")
        check(sm_urls.get(u) == listings_doc.get('updated'),
              f"sitemap.xml: {u} lastmod {sm_urls.get(u)!r} != listings.json updated {listings_doc.get('updated')!r}")
    check(all(u.startswith(SITE_URL + '/') for u in sm_urls), "sitemap.xml: every URL must be on https://eberryvashon.com")

# =====================================================================
# E. Berry listings index (Phase 4): /listings/, the filter bar, and the brand Leaflet map
#   listings/index.html is hand-maintained (not generated): its shell is copied from index.html, and the
#   byte-identity check below is what tells you to copy it again when the shell changes.
# =====================================================================
LIST_REL = 'listings/index.html'
LEAFLET_VERSION = '1.9.4'

def exists(rel):
    return os.path.exists(os.path.join(ROOT, rel))

for rel in (LIST_REL, 'js/listings.js', 'js/eb-map.js', 'css/eb-map.css',
            'js/vendor/leaflet.js', 'js/vendor/leaflet-LICENSE.md', 'css/vendor/leaflet.css',
            'tools/test_listings.py', '.github/workflows/listings-e2e.yml'):
    check(exists(rel), f"{rel} is missing")

# Vendored Leaflet: exact version, its license, and every image its stylesheet points at.
if exists('js/vendor/leaflet.js'):
    leaflet_js = read('js/vendor/leaflet.js')
    check(f'Leaflet {LEAFLET_VERSION}' in leaflet_js[:200] and f't.version="{LEAFLET_VERSION}"' in leaflet_js,
          f"js/vendor/leaflet.js is not Leaflet {LEAFLET_VERSION}")
if exists('js/vendor/leaflet-LICENSE.md'):
    lic = read('js/vendor/leaflet-LICENSE.md')
    check(f'Leaflet {LEAFLET_VERSION}' in lic.splitlines()[0] and 'BSD 2-Clause' in lic and 'Volodymyr Agafonkin' in lic,
          "js/vendor/leaflet-LICENSE.md: header must name the exact version and carry the BSD-2-Clause text")
if exists('css/vendor/leaflet.css'):
    for img in sorted(set(re.findall(r'url\((images/[^)]+)\)', read('css/vendor/leaflet.css')))):
        check(exists('css/vendor/' + img), f"css/vendor/{img} is missing (referenced by css/vendor/leaflet.css)")

# The brand map wrapper and its skin.
if exists('js/eb-map.js'):
    ebmap = read('js/eb-map.js')
    for token in ('https://tile.openstreetmap.org/{z}/{x}/{y}.png', 'OpenStreetMap</a> contributors', 'scrollWheelZoom: false',
                  'maxZoom: 18', "setAttribute('role', 'region')", "setAttribute('aria-label'", 'L.divIcon', 'eb-pin--muted',
                  'window.EBMap', 'groupPoints', 'fmtMoney', "'/listings/'"):
        check(token in ebmap, f"js/eb-map.js: expected {token!r}")
    for label, pat in FLAT_BRAND:
        check(re.search(pat, ebmap, re.I) is None, f"js/eb-map.js: contains {label} (E. Berry brand is flat)")
if exists('css/eb-map.css'):
    mapcss = read('css/eb-map.css')
    for token in ('.leaflet-popup-content-wrapper', '.leaflet-popup-tip', '.eb-map-tiles', '.eb-pin--muted', 'border-radius: 24px',
                  'border: 1.5px solid', 'sepia(.18) saturate(.85)'):
        check(token in mapcss, f"css/eb-map.css: expected {token!r}")
    check(re.search(r'gradient|#fff\b|#ffffff\b|#000\b|#000000\b|(?<![-\w])(?:white|black)(?![-\w])', mapcss, re.I) is None,
          "css/eb-map.css: contains a gradient, pure white or pure black (E. Berry brand is flat)")
    shadows = re.findall(r'(?:box|text|drop)-shadow\s*:\s*([^;}]+)', mapcss)
    check(all(v.strip() == 'none' for v in shadows),
          f"css/eb-map.css: the only shadow value allowed is none (found {[v for v in shadows if v.strip() != 'none']})")

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
    # Everything local except OSM tiles (fetched by eb-map.js) and Google Fonts.
    check(re.search(r'cdn', lp, re.I) is None, f"{LIST_REL}: mentions a CDN; vendor it instead")
    hosts = set()
    for tag in re.findall(r'<(?:script|link)\b[^>]*>', lp):
        mh = re.search(r'\b(?:src|href)="https?://([^/"]+)', tag)
        if mh and 'rel="canonical"' not in tag:
            hosts.add(mh.group(1))
    check(hosts <= {'fonts.googleapis.com', 'fonts.gstatic.com'}, f"{LIST_REL}: external script/stylesheet hosts {sorted(hosts)}; only Google Fonts allowed")
    # Load order: Leaflet before the wrapper before the page script; Leaflet's CSS before the skin.
    order = [lp.find(f'src="{u}"') for u in ('/js/vendor/leaflet.js', '/js/eb-map.js', '/js/site-config.js', '/js/listings.js')]
    check(all(i >= 0 for i in order) and order == sorted(order),
          f"{LIST_REL}: scripts must load leaflet.js, eb-map.js, site-config.js, listings.js in that order")
    css_order = [lp.find(f'href="{u}"') for u in ('/css/tailwind.css', '/css/vendor/leaflet.css', '/css/eb-map.css')]
    check(all(i >= 0 for i in css_order) and css_order == sorted(css_order),
          f"{LIST_REL}: stylesheets must load tailwind.css, vendor/leaflet.css, eb-map.css in that order")
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
    for token in ("'listings/**'", "'js/listings.js'", "'js/eb-map.js'", "'js/vendor/leaflet.js'", "'data/listings.json'",
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

MAP_SCRIPTS = ('/js/vendor/leaflet.js', '/js/eb-map.js')
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
    # Map: only when there are coordinates, and then with Leaflet loaded in order.
    has_map = L.get('lat') is not None and L.get('lng') is not None
    if has_map:
        order = [page.find(f'src="{u}"') for u in MAP_SCRIPTS]
        check(all(i >= 0 for i in order) and order == sorted(order), f"{rel}: has coordinates, so it must load leaflet.js then eb-map.js")
        css_order = [page.find(f'href="{u}"') for u in ('/css/tailwind.css', '/css/vendor/leaflet.css', '/css/eb-map.css')]
        check(all(i >= 0 for i in css_order) and css_order == sorted(css_order), f"{rel}: stylesheets must load tailwind.css, vendor/leaflet.css, eb-map.css in that order")
        check('id="listing-map"' in page and f'data-lat="{L.get("lat")}"' in page and f'data-lng="{L.get("lng")}"' in page and 'EBMap.create' in page,
              f"{rel}: the #listing-map div (with data-lat/data-lng) or its init script is missing")
    else:
        check('id="listing-map"' not in page and 'leaflet' not in page.lower() and 'eb-map' not in page,
              f"{rel}: no coordinates, so it must carry no map markup and load no Leaflet")
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
    order = [fb.find(f'src="{u}"') for u in ('/js/vendor/leaflet.js', '/js/eb-map.js', '/js/site-config.js', '/js/listing-detail.js')]
    check(all(i >= 0 for i in order) and order == sorted(order),
          f"{FB_REL}: scripts must load leaflet.js, eb-map.js, site-config.js, listing-detail.js in that order")
    css_order = [fb.find(f'href="{u}"') for u in ('/css/tailwind.css', '/css/vendor/leaflet.css', '/css/eb-map.css')]
    check(all(i >= 0 for i in css_order) and css_order == sorted(css_order), f"{FB_REL}: stylesheets must load tailwind.css, vendor/leaflet.css, eb-map.css in that order")
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
A11Y_PAGES = (['index.html', LIST_REL, 'listing.html', '404.html']
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
check('prefers-reduced-motion: reduce' in ebm and all(t in ebm for t in ('zoomAnimation: !calm', 'fadeAnimation: !calm', 'markerZoomAnimation: !calm', 'inertia: !calm')),
      'js/eb-map.js: the map must drop its zoom/fade/inertia animation under prefers-reduced-motion')
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

# ---------------- verdict ----------------
if problems:
    print(f"FAIL: {len(problems)} problem(s) out of {checks} checks")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print(f"OK: {checks} checks passed")
print("note: generated pages are verified separately; run `python3 tools/build_pages.py --check` (also a CI step) to prove buildings/ and sitemap.xml are not stale")
