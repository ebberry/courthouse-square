#!/usr/bin/env python3
"""Sanity checks for the Courthouse Square site.

Guards the invariants that have historically drifted: suite pricing math,
data-file shape, version stamps, and download links. Stdlib-only so the owner
can run it anywhere; the PDF content checks activate only if pypdf is present.

Run:  python3 tools/check_site.py     (exit 0 = all good, 1 = problems)
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
m = re.search(r'property="og:image" content="https://courthousesquarevashon\.com(/[^"]+)"', index)
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

# ---------------- verdict ----------------
if problems:
    print(f"FAIL: {len(problems)} problem(s) out of {checks} checks")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print(f"OK: {checks} checks passed")
