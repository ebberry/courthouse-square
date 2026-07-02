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

# ---------------- version stamps ----------------
build = read('tools/build_lease_docs.py')
def const(name):
    m = re.search(rf"^{name}\s*=\s*'([^']*)'", build, re.M)
    return m.group(1) if m else None

version, vdate = const('VERSION'), const('VDATE')
form_version, form_vdate = const('FORM_VERSION'), const('FORM_VDATE')
check(version and vdate, "build script: VERSION/VDATE not found")
check(form_version and form_vdate, "build script: FORM_VERSION/FORM_VDATE not found")

lease_page = read('lease/index.html')
if version and vdate:
    short = version.replace('Version ', 'v')
    check(short in lease_page and vdate in lease_page,
          f"lease/index.html: version line does not mention standard lease {short} ({vdate})")
if form_version and form_vdate:
    short = form_version.replace('Version ', 'v')
    check(short in lease_page and form_vdate in lease_page,
          f"lease/index.html: version line does not mention intake forms {short} ({form_vdate})")

lease_md = read('lease/lease.md')
if version and vdate:
    check(f"{version}, {vdate}" in lease_md,
          f"lease/lease.md: header does not carry '{version}, {vdate}'")

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
