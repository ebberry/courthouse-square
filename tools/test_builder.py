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
  E. Additional terms — natural-language requests interpreted via a mocked
                      Anthropic API (network-intercepted): review cards render,
                      approved terms appear as a numbered Additional Terms
                      section, the record documents dispositions, and the
                      terms survive a record-PDF round-trip. Also the manual
                      "add as written" path and the not-interpreted guard.
  F. Live Claude    — only when ANTHROPIC_API_KEY is set: the real Messages
                      API interprets a request end-to-end (skipped in CI).

Requirements: pip install playwright pypdf pymupdf; playwright install chromium
(or set CHROME=/path/to/chrome). Run: python3 tools/test_builder.py
(pymupdf is optional locally — the layout overrun scan is skipped without it).
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

def scan_layout(path, tag, lm=61.2, rm=61.2):
    """Objective overrun scan: no word may cross the page margins, and no two
    words on the same baseline may overlap (text drawn over text)."""
    try:
        import fitz  # pymupdf
    except ImportError:
        print('note: pymupdf not installed; skipping layout scan')
        return
    doc = fitz.open(path)
    overruns, collisions = [], []
    for pno, page in enumerate(doc, 1):
        W = page.rect.width
        words = sorted(page.get_text('words'), key=lambda w: (round(w[1], 1), w[0]))
        lines = []
        for w in words:
            if w[0] < lm - 1.5 or w[2] > W - rm + 1.5:
                overruns.append((pno, w[4]))
            for ln in lines:
                if abs(ln[0][1] - w[1]) < 2.5:
                    ln.append(w); break
            else:
                lines.append([w])
        for ln in lines:
            ln.sort(key=lambda w: w[0])
            for a, b in zip(ln, ln[1:]):
                if a[2] - b[0] > 1.2:
                    collisions.append((pno, a[4], b[4]))
    check(not overruns, f'{tag}: margin overrun(s): {overruns[:4]}')
    check(not collisions, f'{tag}: text collision(s): {collisions[:4]}')

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
        scan_layout(a['lease'], 'A lease layout'); scan_layout(a['record'], 'A record layout')

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
        check('ADDITIONALTERMS' not in squash(ts), 'B: terms sheet should omit Additional Terms section')
        check('FIRST MONTH (RENT, CAM & SHARED UTILITIES)' in TSU, 'B: whole-month first-payment label')
        rt2 = pdf_text(b['record'])
        check(rt2.count('Not applicable') >= 5, 'B: record documents omissions')
        check(len(PdfReader(b['record']).pages) == 2, 'B: record must be exactly 2 pages')
        scan_layout(b['lease'], 'B lease layout'); scan_layout(b['record'], 'B record layout')
        for committed in ('lease/lease.pdf', 'lease/lease-terms-sheet.pdf', 'lease/letter-of-intent.pdf'):
            scan_layout(committed, f'{committed} layout')

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

        # ---------- E: additional terms via mocked Anthropic API ----------
        mock_terms = {'terms': [
            {'request': 'Can have a dog', 'disposition': 'covered',
             'clauseRef': 'Article 3.5 (Use of Premises)', 'termText': '',
             'note': 'Not prohibited by the lease; use remains within the permitted use.'},
            {'request': 'Wants a sandwich board sign', 'disposition': 'granted',
             'clauseRef': 'Article 12 (Signs)',
             'termText': 'Tenant may place one professionally made sandwich-board sign on the walkway '
                         'adjacent to the Premises during business hours.',
             'note': 'Reasonable and consistent with building practice.'},
        ]}
        mock_resp = {'id': 'msg_mock', 'type': 'message', 'role': 'assistant',
                     'model': 'claude-opus-4-8', 'stop_reason': 'tool_use',
                     'usage': {'input_tokens': 10, 'output_tokens': 10},
                     'content': [{'type': 'tool_use', 'id': 'toolu_mock',
                                  'name': 'report_lease_terms', 'input': mock_terms}]}
        captured = {}
        ctx5 = browser.new_context(accept_downloads=True, viewport={'width': 1280, 'height': 1000})
        def mock_route(route):
            captured['body'] = json.loads(route.request.post_data)
            route.fulfill(status=200, content_type='application/json', body=json.dumps(mock_resp))
        ctx5.route('https://api.anthropic.com/**', mock_route)
        pg5 = ctx5.new_page()
        pg5.goto(url, wait_until='networkidle'); pg5.wait_for_timeout(600)
        fill_common(pg5, 'Dog & Sign LLC', 'N101', '2026-09-01', 'Retail')
        pg5.fill('#f-addl-notes', 'Can have a dog\nWants a sandwich board sign')
        # not-interpreted guard: generating now must be blocked
        pg5.click('#generate'); pg5.wait_for_timeout(400)
        check('not interpreted' in pg5.text_content('#builder-errors'),
              'E: generation blocked while requests are uninterpreted')
        pg5.evaluate("document.getElementById('claude-key-wrap').open = true")
        pg5.fill('#claude-key', 'sk-ant-test-mock')
        pg5.click('#interpret-claude')
        pg5.wait_for_timeout(1500)
        check(pg5.locator('#addl-terms-list [data-term]').count() == 2, 'E: two review cards rendered')
        req = captured.get('body') or {}
        check(req.get('model') == 'claude-opus-4-8', f"E: model sent was {req.get('model')!r}")
        check(req.get('tool_choice', {}).get('name') == 'report_lease_terms', 'E: tool_choice forces the terms tool')
        msg = (req.get('messages') or [{}])[0].get('content', '')
        check('Standard Lease Terms' in msg and 'Can have a dog' in msg,
              'E: request carries the lease text and the notes')
        e = generate(pg5, outdir)
        check('lease' in e and 'record' in e, 'E: both downloads produced')
        lt5 = pdf_text(e['lease']); S5 = squash(lt5); U5 = lt5.upper()
        check('ADDITIONALTERMS' in S5, 'E: lease has Additional Terms section')
        check('ALREADY PROVIDED FOR UNDER ARTICLE 3.5' in U5, 'E: covered request cites the clause')
        check('SANDWICH-BOARD SIGN' in U5, 'E: granted term text present')
        check('6.1' in lt5 and '6.2' in lt5, 'E: terms numbered 6.1/6.2')
        check('9. INDEX OF EXHIBITS' in U5 or 'INDEXOFEXHIBITS' in S5, 'E: exhibit index present')
        rt5 = pdf_text(e['record'])
        check('Covered by Article 3.5' in rt5, 'E: record documents covered disposition')
        check('Granted in the Terms Sheet' in rt5, 'E: record documents granted disposition')
        check(len(PdfReader(e['record']).pages) == 2, 'E: record must be exactly 2 pages')
        scan_layout(e['lease'], 'E lease layout'); scan_layout(e['record'], 'E record layout')
        # round-trip: the record restores the reviewed terms
        pg6 = ctx5.new_page()
        pg6.goto(url, wait_until='networkidle'); pg6.wait_for_timeout(600)
        pg6.evaluate("localStorage.removeItem('chsLeaseDraft.v2')")
        pg6.set_input_files('#import-file', e['record'])
        pg6.wait_for_timeout(1500)
        check(pg6.locator('#addl-terms-list [data-term]').count() == 2, 'E: record import restores terms')
        check('sandwich-board' in pg6.input_value('#addl-terms-list [data-term="1"] [data-k="termText"]'),
              'E: restored term text intact')
        # manual path: every line becomes an editable verbatim term
        pg6.fill('#f-addl-notes', 'Month-to-month after year one')
        pg6.click('#interpret-manual'); pg6.wait_for_timeout(400)
        check(pg6.locator('#addl-terms-list [data-term]').count() == 1, 'E: manual path replaces terms')
        check(pg6.input_value('#addl-terms-list [data-term="0"] [data-k="termText"]') == 'Month-to-month after year one',
              'E: manual term is verbatim')

        # ---------- F: live Claude interpretation (needs ANTHROPIC_API_KEY) ----------
        live_key = os.environ.get('ANTHROPIC_API_KEY')
        if live_key:
            ctx7 = browser.new_context(viewport={'width': 1280, 'height': 1000})
            pg7 = ctx7.new_page()
            pg7.goto(url, wait_until='networkidle'); pg7.wait_for_timeout(600)
            fill_common(pg7, 'Live Test LLC', 'N101', '2026-09-01', 'Office')
            pg7.fill('#f-addl-notes', 'Can we keep a small, well-behaved dog in the office?')
            pg7.evaluate("document.getElementById('claude-key-wrap').open = true")
            pg7.fill('#claude-key', live_key)
            pg7.click('#interpret-claude')
            pg7.wait_for_selector('#addl-terms-list [data-term]', timeout=120000)
            check(pg7.locator('#addl-terms-list [data-term]').count() >= 1, 'F: live Claude returned terms')
            status = pg7.text_content('#interpret-status')
            check('failed' not in status.lower(), f'F: live interpretation status: {status}')
        else:
            print('note: ANTHROPIC_API_KEY not set; skipping live Claude scenario F')

        browser.close()

    if failures:
        print(f'FAIL: {len(failures)} failure(s), {passed} checks passed')
        for f in failures: print('  -', f)
        sys.exit(1)
    print(f'OK: builder E2E — {passed} checks passed (A maximal/proration, B omission, C record import, '
          f'D LOI import, E additional terms{", F live Claude" if os.environ.get("ANTHROPIC_API_KEY") else ""})')

if __name__ == '__main__':
    main()
