#!/usr/bin/env python3
"""End-to-end test for the Lease Builder (/lease/builder.html).

Drives the real page in headless Chromium and verifies the generated PDFs:

  A. Maximal deal   — guarantor + tenant work + renewal + 3% escalation +
                      mid-month start: everything included, proration correct,
                      rent schedule present, record exactly two pages,
                      due-at-signing math checks out.
  B. Minimal deal   — every optional item blank: all nine optional sections
                      absent from the terms sheet, documented as omitted in
                      the record, record exactly two pages.
  C. Record import  — dropping the record PDF from A back onto the builder
                      restores the deal (embedded deal.json round-trip).
  D. LOI import     — a filled Letter of Intent PDF prefills the checklist.

Requirements: pip install playwright pypdf; playwright install chromium
(or set CHROME=/path/to/chrome). Run: python3 tools/test_builder.py
"""

import http.server, json, os, re, socketserver, sys, tempfile, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8189
failures = []
passed = 0

def check(ok, msg):
    global passed
    if ok: passed += 1
    else: failures.append(msg)

def pdf_text(path):
    from pypdf import PdfReader
    return re.sub(r'\s+', ' ', "\n".join((p.extract_text() or "") for p in PdfReader(path).pages))

def squash(t):
    """Uppercase and strip spaces — matches tracked (letterspaced) display type."""
    return re.sub(r'\s+', '', t.upper())

def launch(p):
    chrome = os.environ.get('CHROME')
    candidates = [c for c in [chrome, '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'] if c]
    for c in candidates:
        if os.path.exists(c):
            return p.chromium.launch(executable_path=c, args=['--no-sandbox'])
    return p.chromium.launch(args=['--no-sandbox'])   # playwright-managed browser (CI)

def fill_common(pg, tenant, suite, start, use):
    pg.fill('#f-tenant', tenant)
    pg.select_option('#f-suite', suite)
    pg.fill('#f-start', start)
    pg.dispatch_event('#f-start', 'change')
    pg.fill('#f-use', use)

def generate(pg, outdir):
    downloads = []
    pg.on('download', lambda d: downloads.append(d))
    pg.click('#generate')
    pg.wait_for_timeout(6000)
    paths = {}
    for d in downloads:
        p = os.path.join(outdir, d.suggested_filename)
        d.save_as(p)
        key = 'lease' if d.suggested_filename.startswith('CourthouseSquare_Lease') else 'record'
        paths[key] = p
    return paths

def main():
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader

    os.chdir(ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(('127.0.0.1', PORT), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{PORT}/lease/builder.html'

    vac = json.load(open('data/vacancies.json'))
    n108 = next(s for s in vac['suites'] if s['unit'] == 'N108')
    monthly = round(n108['rent'] + n108['cam'] + n108['utilities'], 2)
    prorated = round(monthly * 17 / 31, 2)          # Aug 15 start: 17 of 31 days
    due = round(prorated + 800 - 100, 2)            # + deposit - GFD credit

    outdir = tempfile.mkdtemp(prefix='builder-e2e-')
    with sync_playwright() as p:
        browser = launch(p)

        # ---------- A: maximal deal with mid-month start ----------
        ctx = browser.new_context(accept_downloads=True, viewport={'width': 1280, 'height': 1000})
        pg = ctx.new_page()
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(url, wait_until='networkidle'); pg.wait_for_timeout(600)
        fill_common(pg, 'Cooper Law PLLC', 'N108', '2026-08-15', 'Law office')
        pg.fill('#f-guarantor', 'David F. Cooper')
        pg.fill('#f-guarantor-addr', '123 Maple Ln SW, Vashon WA 98070')
        pg.fill('#f-renewal', 'One 2-year renewal at market rate')
        pg.fill('#f-escalation', '3% annually on the anniversary')
        pg.fill('#f-ti-allowance', '2500')
        pg.fill('#f-ti-scope', 'Paint and carpet')
        pg.fill('#f-deposit', '800')
        check(abs(float(pg.input_value('#f-first-month')) - prorated) < 0.02,
              f"A: prorated first payment {pg.input_value('#f-first-month')} != {prorated}")
        a = generate(pg, outdir)
        check('lease' in a and 'record' in a, 'A: both downloads produced')
        lt = pdf_text(a['lease']); rt = pdf_text(a['record'])
        UP = lt.upper()
        for needle in ['PERSONAL GUARANTOR: DAVID F. COOPER', 'ONE 2-YEAR RENEWAL',
                       'FIRST PAYMENT (PRORATED, 17/31 DAYS OF AUGUST 2026)', 'NOTICE TO LANDLORD',
                       'LEGAL DESCRIPTION', 'SEE EXHIBIT A, ATTACHED']:
            check(needle in UP, f'A: lease package missing {needle!r}')
        check('EXHIBITC' in squash(lt), 'A: lease package missing Exhibit C')
        SR = squash(rt)
        for needle in ['PROJECTEDBASERENTSCHEDULE', 'LEASEYEAR2', 'TOTALDUEATSIGNING',
                       squash(f'{due:,.2f}'), 'LESS:GOODFAITHDEPOSITCREDIT']:
            check(needle in SR, f'A: record missing {needle!r}')
        check(len(PdfReader(a['record']).pages) == 2, 'A: record must be exactly 2 pages')
        # deal.json embedded in record
        att = PdfReader(a['record']).attachments
        check('deal.json' in att, 'A: record embeds deal.json')
        # midcentury fonts embedded in builder output (BaseFont names)
        fdict = PdfReader(a['lease']).pages[0]['/Resources']['/Font']
        basefonts = ' '.join(str(fdict[k].get_object().get('/BaseFont', '')) for k in fdict.keys())
        check('Jost' in basefonts and 'LibreBaskerville' in basefonts,
              f'A: Jost/Baskerville embedded in lease package (got {basefonts})')
        check(not errors, f'A: page errors: {errors[:2]}')

        # ---------- B: minimal deal (omission matrix) ----------
        ctx2 = browser.new_context(accept_downloads=True, viewport={'width': 1280, 'height': 1000})
        pg2 = ctx2.new_page()
        pg2.goto(url, wait_until='networkidle'); pg2.wait_for_timeout(600)
        fill_common(pg2, 'Quiet Mind Counseling LLC', 'N204', '2026-09-01', 'Counseling practice')
        b = generate(pg2, outdir)
        n_std = len(PdfReader('lease/lease.pdf').pages)
        rb = PdfReader(b['lease'])
        ts = re.sub(r'\s+', ' ', "\n".join((rb.pages[i].extract_text() or "") for i in range(len(rb.pages) - n_std)))
        TSU = ts.upper()
        for needle in ['PERSONAL GUARANTOR', 'EXHIBIT B', 'EXHIBIT C', 'RENEWAL OPTIONS',
                       'RENT ESCALATION', 'EXCLUSIVE USE', 'SPECIAL STIPULATIONS', 'EXHIBIT D',
                       'PRORATED']:
            check(needle not in TSU, f'B: terms sheet should omit {needle!r}')
        check('FIRST MONTH (RENT, CAM & SHARED UTILITIES)' in TSU, 'B: whole-month first-payment label')
        rt2 = pdf_text(b['record'])
        check(rt2.count('Not applicable') >= 5, 'B: record documents omissions')
        check(len(PdfReader(b['record']).pages) == 2, 'B: record must be exactly 2 pages')

        # ---------- C: record PDF import round-trip ----------
        ctx3 = browser.new_context(viewport={'width': 1280, 'height': 1000})
        pg3 = ctx3.new_page()
        pg3.goto(url, wait_until='networkidle'); pg3.wait_for_timeout(600)
        pg3.set_input_files('#import-file', a['record'])
        pg3.wait_for_timeout(1500)
        check(pg3.input_value('#f-tenant') == 'Cooper Law PLLC', 'C: tenant restored from record PDF')
        check(pg3.input_value('#f-deposit') == '800', 'C: deposit restored from record PDF')
        check(pg3.input_value('#f-guarantor') == 'David F. Cooper', 'C: guarantor restored')

        # ---------- D: filled LOI import ----------
        from pypdf import PdfWriter
        w = PdfWriter(clone_from='lease/letter-of-intent.pdf')
        for page in w.pages:
            w.update_page_form_field_values(page, {
                'loi_legal_name': 'Harbor Books LLC',
                'loi_premises': '19001 Vashon Hwy SW, Suite N101',
                'loi_use': 'Retail bookshop',
                'loi_base_rent': '$815.85',
                'loi_deposit': '500',
                'loi_contact_info': '206-555-0101, books@harbor.example',
            }, auto_regenerate=False)
        loi_path = os.path.join(outdir, 'filled-loi.pdf')
        with open(loi_path, 'wb') as f: w.write(f)
        ctx4 = browser.new_context(viewport={'width': 1280, 'height': 1000})
        pg4 = ctx4.new_page()
        pg4.goto(url, wait_until='networkidle'); pg4.wait_for_timeout(600)
        pg4.set_input_files('#import-file', loi_path)
        pg4.wait_for_timeout(1500)
        check(pg4.input_value('#f-tenant') == 'Harbor Books LLC', 'D: tenant from LOI')
        check(pg4.input_value('#f-suite') == 'N101', 'D: suite matched from LOI premises')
        check(pg4.input_value('#f-rent') == '815.85', 'D: rent from LOI')
        check(pg4.input_value('#f-notice-email') == 'books@harbor.example', 'D: email extracted from LOI')

        browser.close()

    if failures:
        print(f'FAIL: {len(failures)} failure(s), {passed} checks passed')
        for f in failures: print('  -', f)
        sys.exit(1)
    print(f'OK: builder E2E — {passed} checks passed (A maximal/proration, B omission, C record import, D LOI import)')

if __name__ == '__main__':
    main()
