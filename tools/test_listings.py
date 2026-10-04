#!/usr/bin/env python3
"""End-to-end test for the listings index (/listings/).

Drives the real page in headless Chromium, with the network sealed: OpenStreetMap tiles and Google Fonts
are answered locally, so the test is the same on a laptop, in CI and behind a proxy that blocks both.

  A. Cards          — /listings/ renders one card per feed entry and the count line agrees
  B. Type           — ?type=commercial preselects Commercial; ?type=residential shows the residential empty state;
                      the homepage's header links land on the right filter
  C. Beds           — the beds select is disabled (and muted) while Commercial is active
  D. Price          — price max filters to exactly the subset computed from data/listings.json
  E. Map            — one marker for the one shared coordinate; its popup lists every listing; markers follow filters
  F. URL state      — filters round-trip through location.search; bad params are ignored; Clear resets
  G. Flat brand     — computed-style audit (no shadows, gradients, pure white/black) on the bar, a card and the map
  H. Mobile         — at 390px the Map / List pill swaps the panes; the map is built lazily; no sideways scroll
  I. Synthetic feed — homes, a future date, a null coordinate: beds semantics, muted pin, no marker without coords
  J. Details        — sticky bar and map, whole-card focus ring, empty/over-filtered/failed-feed states, zero page errors
  K. No Leaflet     — if the map library fails to load, the page is still a working filterable list

Requirements: pip install playwright; playwright install chromium (or set CHROME=/path/to/chrome).
Run: python3 tools/test_listings.py
"""

import base64, copy, glob, http.server, json, os, re, socketserver, sys, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8190
BASE = f'http://127.0.0.1:{PORT}'
failures = []
passed = 0

# A 1x1 PNG: stands in for every OpenStreetMap tile.
TILE_PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
TILE_RE = re.compile(r'^https://tile\.openstreetmap\.org/\d+/\d+/\d+\.png$')


def check(ok, msg):
    global passed
    if ok: passed += 1
    else: failures.append(msg)


def money(n):
    return f'${n:,.0f}'


# ---------------------------------------------------------------- data + the filter, computed independently of the page

DOC = json.load(open(os.path.join(ROOT, 'data/listings.json'), encoding='utf-8'))
LISTINGS = DOC['listings']


def expected(listings, type=None, beds=None, price=None, sqft=None):
    """ids the page should show. Beds and sqft are minimums, price is a maximum; a listing with no
    value for a filter that is set cannot satisfy it (a commercial suite has no bedrooms)."""
    out = []
    for L in listings:
        if type and L['type'] != type: continue
        if beds and not (L['beds'] is not None and L['beds'] >= beds): continue
        if price and not (L['rent'] <= price): continue
        if sqft and not (L['sqft'] is not None and L['sqft'] >= sqft): continue
        out.append(L['id'])
    return out


def groups(listings):
    g = {}
    for L in listings:
        if L['lat'] is not None and L['lng'] is not None:
            g.setdefault((L['lat'], L['lng']), []).append(L['id'])
    return g


# ---------------------------------------------------------------- harness

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def launch(p):
    chrome = os.environ.get('CHROME')
    candidates = [chrome] + sorted(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome'))
    for c in candidates:
        if c and os.path.exists(c):
            return p.chromium.launch(executable_path=c, args=['--no-sandbox'])
    return p.chromium.launch(args=['--no-sandbox'])   # playwright-managed browser (CI)


class Session:
    """One browser context with the network sealed and every problem recorded."""

    def __init__(self, browser, tag, feed=None, feed_status=200, **ctx_kw):
        self.tag = tag
        self.errors = []        # page errors and console errors
        self.bad_local = []     # local requests answered 4xx/5xx
        self.tiles = []         # tile URLs requested
        self.ctx = browser.new_context(**ctx_kw)
        self.ctx.route(re.compile(r'^https://tile\.openstreetmap\.org/'), self._tile)
        self.ctx.route(re.compile(r'^https://fonts\.googleapis\.com/'),
                       lambda r: r.fulfill(status=200, content_type='text/css', body=''))
        self.ctx.route(re.compile(r'^https://fonts\.gstatic\.com/'), lambda r: r.abort())
        if feed is not None or feed_status != 200:
            def feed_route(r):
                if feed_status != 200:
                    r.fulfill(status=feed_status, body='nope')
                else:
                    r.fulfill(status=200, content_type='application/json', body=json.dumps(feed))
            self.ctx.route('**/data/listings.json', feed_route)
        self.pg = self.ctx.new_page()
        self.pg.on('pageerror', lambda e: self.errors.append(f'{tag} pageerror: {e}'))
        self.pg.on('console', self._console)
        self.pg.on('response', self._response)

    def _tile(self, route):
        self.tiles.append(route.request.url)
        route.fulfill(status=200, content_type='image/png', body=TILE_PNG)

    def _console(self, m):
        if m.type == 'error':
            self.errors.append(f'{self.tag} console: {m.text}')

    def _response(self, r):
        if self.bad_local is not None and r.url.startswith(BASE) and r.status >= 400:
            self.bad_local.append(f'{r.status} {r.url}')

    def open(self, path='/listings/'):
        self.pg.goto(BASE + path, wait_until='networkidle')
        self.settle()
        return self.pg

    def settle(self):
        """The count line leaves its 'Checking…' placeholder once the feed has rendered (or failed)."""
        self.pg.wait_for_function("!document.getElementById('result-count').textContent.startsWith('Checking')",
                                  timeout=10000)
        self.pg.wait_for_timeout(150)


def cards(pg):
    return pg.locator('#listing-grid article')


def card_ids(pg):
    return pg.eval_on_selector_all('#listing-grid article', 'els => els.map(e => e.dataset.id)')


def count_text(pg):
    # inner_text: the small-screen "Clear filters" link inside the line is display:none from lg up
    return re.sub(r'\s+', ' ', pg.inner_text('#result-count')).strip()


def pressed(pg):
    return pg.eval_on_selector_all('#type-group [data-type]',
                                   'els => Object.fromEntries(els.map(e => [e.dataset.type, e.getAttribute("aria-pressed")]))')


def popup_items(pg):
    return pg.eval_on_selector_all('.leaflet-popup .eb-pop-item',
                                   'els => els.map(e => ({href: e.querySelector("a").getAttribute("href"), rent: e.querySelector("span").textContent}))')


# Computed-style flat-brand audit: no shadows, gradients, pure white or pure black on the elements under `sel`.
AUDIT_JS = """
(sel) => {
  const bad = [];
  const BAD = new Set(['rgb(255, 255, 255)', 'rgb(0, 0, 0)']);
  const roots = document.querySelectorAll(sel);
  roots.forEach(root => {
    [root, ...root.querySelectorAll('*')].forEach(el => {
      for (const pseudo of [null, '::before', '::after']) {
        const cs = getComputedStyle(el, pseudo);
        if (pseudo && cs.content === 'none') continue;
        const name = el.tagName.toLowerCase() + (el.className && el.className.baseVal === undefined ? '.' + String(el.className).split(' ')[0] : '') + (pseudo || '');
        if (cs.boxShadow !== 'none') bad.push(name + ' box-shadow ' + cs.boxShadow);
        if (cs.textShadow !== 'none') bad.push(name + ' text-shadow ' + cs.textShadow);
        if (/gradient/.test(cs.backgroundImage)) bad.push(name + ' gradient');
        if (BAD.has(cs.backgroundColor)) bad.push(name + ' background ' + cs.backgroundColor);
        if (BAD.has(cs.color)) bad.push(name + ' color ' + cs.color);
        for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
          if (parseFloat(cs['border' + side + 'Width']) > 0 && cs['border' + side + 'Style'] !== 'none' && BAD.has(cs['border' + side + 'Color']))
            bad.push(name + ' border-' + side + ' ' + cs['border' + side + 'Color']);
        }
        if (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 && BAD.has(cs.outlineColor)) bad.push(name + ' outline ' + cs.outlineColor);
        if (el instanceof SVGElement) {
          if (BAD.has(cs.fill)) bad.push(name + ' fill ' + cs.fill);
          if (BAD.has(cs.stroke)) bad.push(name + ' stroke ' + cs.stroke);
        }
      }
    });
  });
  return { roots: roots.length, bad };
}
"""


def audit(pg, sel, tag):
    r = pg.evaluate(AUDIT_JS, sel)
    check(r['roots'] >= 1, f'{tag}: audit found nothing at {sel}')
    check(not r['bad'], f'{tag}: flat-brand violations under {sel}: {r["bad"][:4]}')


def synthetic_feed():
    """The real feed plus three homes: a future date and its own coordinate, a plain one on another
    coordinate, and one with no coordinates at all."""
    doc = copy.deepcopy(DOC)
    base = copy.deepcopy(LISTINGS[0])
    def home(id, title, rent, beds, baths, sqft, available, lat, lng):
        h = dict(base)
        h.update(id=id, type='residential', title=title, address=f'{title}, Vashon, WA 98070', rent=rent, beds=beds,
                 baths=baths, sqft=sqft, available=available, lat=lat, lng=lng, photos=[],
                 summary=f'A warm little place called {title}.', features=[])
        h.pop('buildingId', None)
        return h
    doc['listings'] += [
        home('test-cottage', 'Cottage on Bank Road', 2100, 2, 1, 800, '2099-01-01', 47.4000, -122.4600),
        home('test-farmhouse', 'Farmhouse near the Pond', 2900, 3, 2, 1400, None, 47.3800, -122.4900),
        home('test-studio', 'Studio above the Shop', 1200, 1, 1, None, None, None, None),
    ]
    return doc


# ---------------------------------------------------------------- the test

def main():
    from playwright.sync_api import sync_playwright

    os.chdir(ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(('127.0.0.1', PORT), Quiet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    n_all = len(LISTINGS)
    n_comm = len(expected(LISTINGS, type='commercial'))
    n_res = len(expected(LISTINGS, type='residential'))
    sessions = []

    with sync_playwright() as p:
        browser = launch(p)

        # ---------- A: the page, the cards, the count line ----------
        s = Session(browser, 'A', viewport={'width': 1440, 'height': 900}); sessions.append(s)
        pg = s.open()
        check(pg.title() == "What's open — E. Berry Property Management", f'A: title is {pg.title()!r}')
        check(pg.get_attribute('link[rel=canonical]', 'href') == 'https://eberryvashon.com/listings/', 'A: canonical URL')
        check(cards(pg).count() == n_all, f'A: {cards(pg).count()} cards, expected {n_all}')
        check(card_ids(pg) == [L['id'] for L in LISTINGS], 'A: cards follow feed order')
        check(count_text(pg) == f'{n_all} places open right now.', f'A: count line is {count_text(pg)!r}')
        check(pressed(pg) == {'all': 'true', 'residential': 'false', 'commercial': 'false'}, f'A: default type blocks {pressed(pg)}')
        check(pg.is_hidden('#clear-filters'), 'A: Clear is hidden while no filter is active')
        check(pg.locator('#listing-grid .listing-card-link').first.get_attribute('href') == f'/listings/{LISTINGS[0]["id"]}/',
              'A: first card links to its listing page')
        first = LISTINGS[0]
        ctext = re.sub(r'\s+', ' ', cards(pg).first.inner_text())
        for needle in ('COMMERCIAL' if first['type'] == 'commercial' else 'HOME', money(first['rent']) + '/mo',
                       f"{first['sqft']} sq ft", 'available now', first['title'], "Curious? Let's talk", 'photos soon'):
            check(needle.lower() in ctext.lower(), f'A: first card is missing {needle!r}: {ctext!r}')
        check(pg.locator('#listing-grid p.line-clamp-2').count() == n_all, 'A: every card clamps its summary to two lines')
        # tiles came from OpenStreetMap, and the attribution is on screen
        pg.wait_for_selector('.leaflet-tile-loaded', timeout=10000)
        check(len(s.tiles) > 0 and all(TILE_RE.match(u) for u in s.tiles), f'A: tile requests {s.tiles[:2]}')
        attr = re.sub(r'\s+', ' ', pg.text_content('.leaflet-control-attribution'))
        check('© OpenStreetMap contributors' in attr, f'A: attribution reads {attr!r}')
        check(pg.is_visible('.leaflet-control-attribution'), 'A: attribution is visible')
        check(pg.get_attribute('#map', 'role') == 'region' and bool(pg.get_attribute('#map', 'aria-label')),
              'A: map container is a labelled region')

        # ---------- B: the type blocks ----------
        pg = s.open('/listings/?type=commercial')
        check(pressed(pg) == {'all': 'false', 'residential': 'false', 'commercial': 'true'}, f'B: ?type=commercial blocks {pressed(pg)}')
        check(cards(pg).count() == n_comm, f'B: ?type=commercial shows {cards(pg).count()}, expected {n_comm}')
        check(pg.is_visible('#clear-filters'), 'B: Clear appears once a filter is active')
        check(re.search(r'bg-eb-mustard|rgb\(232, 196, 80\)', pg.evaluate(
            "getComputedStyle(document.querySelector('#type-group [data-type=commercial]')).backgroundColor")) is not None,
            'B: the active block is Mustard')

        pg = s.open('/listings/?type=residential')
        check(pressed(pg)['residential'] == 'true', 'B: ?type=residential preselects Homes')
        if n_res == 0:
            check(cards(pg).count() == 0, 'B: ?type=residential shows no cards')
            es = re.sub(r'\s+', ' ', pg.text_content('#empty-state'))
            check(pg.is_visible('#empty-state'), 'B: residential empty state is visible')
            check("Nothing's open just now — but homes come and go. Tell me what you're looking for and I'll keep an eye out." in es,
                  f'B: residential empty copy is {es!r}')
            check(pg.get_attribute('#empty-state a[href="/#inquire"]', 'href') == '/#inquire', 'B: empty state links to /#inquire')
            check(count_text(pg) == 'No homes open right now.', f'B: count line {count_text(pg)!r}')
            # the quiet cross-link switches to Commercial without a reload
            pg.click('#empty-state a[data-set-type="commercial"]')
            check(cards(pg).count() == n_comm and pressed(pg)['commercial'] == 'true', 'B: cross-link switches to Commercial')
        else:
            check(cards(pg).count() == n_res, f'B: ?type=residential shows {cards(pg).count()}, expected {n_res}')

        # the homepage's header links deep-link here with ?type=
        pg.goto(BASE + '/', wait_until='networkidle')
        pg.click('header nav a[href="/listings/?type=commercial"]')
        pg.wait_for_url(re.compile(r'/listings/\?type=commercial$'))
        s.settle()
        check(pressed(pg)['commercial'] == 'true' and cards(pg).count() == n_comm, 'B: the homepage Commercial link lands on the Commercial filter')
        pg.goto(BASE + '/', wait_until='networkidle')
        pg.click('header nav a[href="/listings/?type=residential"]')
        pg.wait_for_url(re.compile(r'/listings/\?type=residential$'))
        s.settle()
        check(pressed(pg)['residential'] == 'true' and cards(pg).count() == n_res, 'B: the homepage Homes link lands on the Homes filter')

        # ---------- C: beds is for homes ----------
        pg = s.open('/listings/')
        check(not pg.is_disabled('#f-beds'), 'C: beds select is enabled for All')
        pg.click('#type-group [data-type="commercial"]')
        check(pg.is_disabled('#f-beds'), 'C: beds select is disabled for Commercial')
        check(float(pg.evaluate("getComputedStyle(document.getElementById('f-beds')).opacity")) < 1, 'C: disabled beds select is visually muted')
        pg.click('#type-group [data-type="residential"]')
        check(not pg.is_disabled('#f-beds'), 'C: beds select is enabled again for Homes')
        pg = s.open('/listings/?type=commercial&beds=2')
        check(pg.is_disabled('#f-beds') and pg.input_value('#f-beds') == '' and 'beds' not in pg.evaluate('location.search'),
              'C: ?type=commercial&beds=2 ignores beds')
        check(cards(pg).count() == n_comm, 'C: commercial with a stray beds param still shows every commercial listing')

        # ---------- D: price max ----------
        pg = s.open('/listings/')
        pg.select_option('#f-price', '750')
        want = expected(LISTINGS, price=750)
        check(want and len(want) < n_all, 'D: test data should make $750 a real subset')
        check(sorted(card_ids(pg)) == sorted(want), f'D: $750 shows {card_ids(pg)}, expected {want}')
        rent = {L['id']: L['rent'] for L in LISTINGS}
        check(all(rent[i] <= 750 for i in card_ids(pg)), 'D: every card is at most $750')
        check(count_text(pg) == f'{len(want)} of {n_all} places match.', f'D: count line {count_text(pg)!r}')
        check('price=750' in pg.evaluate('location.search'), 'D: price lands in the URL')
        pg.select_option('#f-sqft', '150')
        want2 = expected(LISTINGS, price=750, sqft=150)
        check(sorted(card_ids(pg)) == sorted(want2), f'D: $750 + 150 sq ft shows {card_ids(pg)}, expected {want2}')

        # ---------- E: the map ----------
        pg = s.open('/listings/')
        g = groups(LISTINGS)
        check(len(g) == 1, f'E: the feed should still share one coordinate (found {len(g)}); update this test if that changed')
        pg.wait_for_selector('.leaflet-marker-icon')
        check(pg.locator('.leaflet-marker-icon').count() == len(g), f'E: {pg.locator(".leaflet-marker-icon").count()} markers, expected {len(g)}')
        check(pg.locator('.eb-pin__count').first.text_content().strip() == str(n_all), 'E: the pin carries the group count')
        pin_label = pg.get_attribute('.leaflet-marker-icon', 'aria-label') or ''
        check(str(n_all) in pin_label and pg.get_attribute('.leaflet-marker-icon', 'tabindex') == '0', f'E: pin is keyboard reachable and named ({pin_label!r})')
        pg.locator('.leaflet-marker-icon').first.click()
        pg.wait_for_selector('.leaflet-popup .eb-pop-item')
        items = popup_items(pg)
        ids = list(g.values())[0]
        check(len(items) == len(ids) == n_all, f'E: popup lists {len(items)} entries, expected {len(ids)}')
        check([i['href'] for i in items] == [f'/listings/{x}/' for x in ids], f'E: popup links {[i["href"] for i in items]}')
        check([i['rent'] for i in items] == [money(next(L for L in LISTINGS if L['id'] == x)['rent']) + '/mo' for x in ids],
              f'E: popup rents {[i["rent"] for i in items]}')
        check(pg.get_attribute('.leaflet-popup', 'class').find('eb-popup') >= 0, 'E: popup carries the brand class')
        audit(pg, '.leaflet-popup', 'E popup')
        # markers follow the filter: $750 leaves a smaller group
        pg.select_option('#f-price', '750')
        try:
            pg.wait_for_selector('.leaflet-popup', state='detached', timeout=3000)   # Leaflet fades popups out for 200ms
            closed = True
        except Exception:
            closed = False
        check(closed, 'E: popup closes when its marker is re-rendered')
        pg.locator('.leaflet-marker-icon').first.click()
        pg.wait_for_selector('.leaflet-popup .eb-pop-item')
        got = [i['href'] for i in popup_items(pg)]
        check(sorted(got) == sorted(f'/listings/{x}/' for x in expected(LISTINGS, price=750)), f'E: filtered popup lists {got}')
        pg.select_option('#f-sqft', '1000')   # nothing this big in the feed
        if not expected(LISTINGS, price=750, sqft=1000):
            check(pg.locator('.leaflet-marker-icon').count() == 0, 'E: no results means no markers')

        # ---------- F: URL state ----------
        pg = s.open('/listings/')
        pg.click('#type-group [data-type="commercial"]')
        pg.select_option('#f-price', '1000')
        pg.select_option('#f-sqft', '150')
        search = pg.evaluate('location.search')
        check(search == '?type=commercial&price=1000&sqft=150', f'F: search is {search!r}')
        n_before = cards(pg).count()
        check(n_before == len(expected(LISTINGS, type='commercial', price=1000, sqft=150)), 'F: filtered count matches the data')
        pg = s.open('/listings/' + search)
        check(cards(pg).count() == n_before, f'F: reload shows {cards(pg).count()}, expected {n_before}')
        check(pg.input_value('#f-price') == '1000' and pg.input_value('#f-sqft') == '150' and pressed(pg)['commercial'] == 'true',
              'F: reload restores every control')
        check(pg.evaluate('location.search') == search, 'F: reload keeps the same URL')
        pg.click('#clear-filters')
        check(pg.evaluate('location.search') == '' and cards(pg).count() == n_all, 'F: Clear resets the URL and the list')
        check(pg.is_hidden('#clear-filters') and pressed(pg)['all'] == 'true', 'F: Clear hides itself and returns to All')
        pg = s.open('/listings/?type=bogus&price=999&beds=abc&sqft=-1')
        check(cards(pg).count() == n_all and pg.evaluate('location.search') == '', 'F: unknown params are ignored and cleaned from the URL')

        # ---------- J (part): other states, in the same desktop session ----------
        # over-filtered
        pg = s.open('/listings/?price=750&sqft=1000')
        if not expected(LISTINGS, price=750, sqft=1000):
            es = re.sub(r'\s+', ' ', pg.text_content('#empty-state'))
            check(cards(pg).count() == 0 and 'Nothing matches that combination. Loosen a filter or two?' in es, f'J: over-filtered copy {es!r}')
            check(pg.locator('#empty-state a[data-clear]').count() == 1, 'J: over-filtered state offers Clear')
            pg.click('#empty-state a[data-clear]')
            check(cards(pg).count() == n_all and pg.is_hidden('#empty-state'), 'J: its Clear link restores the list')
        # sticky filter bar and map while the cards scroll
        pg = s.open('/listings/')
        pg.mouse.wheel(0, 700); pg.wait_for_timeout(300)
        geo = pg.evaluate("""() => {
          const r = id => document.getElementById(id).getBoundingClientRect();
          const h = document.querySelector('body > header').getBoundingClientRect();
          const probe = document.elementFromPoint(window.innerWidth - 120, h.height / 2);
          return { headerBottom: h.bottom, bar: r('filter-bar'), map: r('map'), vh: window.innerHeight,
                   headerOnTop: !!(probe && probe.closest('header')), sy: window.scrollY };
        }""")
        check(geo['sy'] > 300, f'J: page scrolled ({geo["sy"]})')
        check(abs(geo['bar']['top'] - geo['headerBottom']) <= 1.5, f'J: filter bar sticks under the header ({geo["bar"]["top"]} vs {geo["headerBottom"]})')
        check(geo['map']['top'] >= geo['bar']['bottom'] - 1 and geo['map']['bottom'] <= geo['vh'] + 1 and geo['map']['height'] > 300,
              f'J: map stays in view beside the cards ({geo["map"]})')
        check(geo['headerOnTop'], 'J: the header stays above the Leaflet panes')
        audit(pg, '#filter-bar', 'G filter bar')
        audit(pg, '#listing-grid li:first-child', 'G first card')
        audit(pg, '#map', 'G map')
        check(not pg.is_visible('#mobile-toggle'), 'J: no Map/List pill on desktop')
        # keyboard: a card is one link and its focus ring goes around the whole card
        pg = s.open('/listings/')
        found = False
        for _ in range(40):
            pg.keyboard.press('Tab')
            if pg.evaluate("document.activeElement.classList.contains('listing-card-link')"):
                found = True; break
        check(found, 'J: Tab reaches a card link')
        if found:
            ring = pg.evaluate("""() => { const a = document.activeElement, own = getComputedStyle(a), after = getComputedStyle(a, '::after');
              const card = a.closest('article').getBoundingClientRect(), box = a.getBoundingClientRect();
              return { own: own.outlineStyle, afterStyle: after.outlineStyle, afterWidth: after.outlineWidth, afterColor: after.outlineColor,
                       coversCard: after.position === 'absolute' && box.width < card.width }; }""")
            check(ring['own'] == 'none' and ring['afterStyle'] == 'solid' and ring['afterWidth'] == '2px' and ring['afterColor'] == 'rgb(103, 10, 47)',
                  f'J: focus ring is a 2px Berry ring on the whole card: {ring}')
        s.ctx.close()

        # ---------- J (part): the feed will not load ----------
        s = Session(browser, 'J-fail', feed_status=500, viewport={'width': 1440, 'height': 900}); sessions.append(s)
        s.bad_local = None  # a 500 here is the point of the scenario
        pg = s.pg
        pg.goto(BASE + '/listings/', wait_until='networkidle')
        pg.wait_for_selector('#empty-state:not([hidden])')
        es = re.sub(r'\s+', ' ', pg.text_content('#empty-state'))
        check("couldn't load the list" in es and pg.locator('#empty-state a[href="mailto:me@ebberry.com"]').count() == 1,
              f'J: failed-feed message {es!r}')
        check(cards(pg).count() == 0, 'J: failed feed shows no cards')
        s.errors = [e for e in s.errors if 'status of 500' not in e]   # the browser logs the 500 itself
        s.ctx.close()

        # ---------- K: Leaflet will not load: still a perfectly good list ----------
        s = Session(browser, 'K', viewport={'width': 1440, 'height': 900}); sessions.append(s)
        s.ctx.route('**/js/vendor/leaflet.js', lambda r: r.abort())
        pg = s.pg
        pg.goto(BASE + '/listings/', wait_until='networkidle')
        s.settle()
        check(cards(pg).count() == n_all, 'K: cards render without Leaflet')
        check(not pg.is_visible('#map-pane') and pg.get_attribute('#split', 'data-nomap') == '1', 'K: the map pane steps aside')
        pg.select_option('#f-price', '750')
        check(cards(pg).count() == len(expected(LISTINGS, price=750)), 'K: filters still work without Leaflet')
        s.errors = [e for e in s.errors if 'Failed to load resource' not in e]   # the aborted request itself is the point
        s.ctx.close()

        # ---------- I: synthetic feed (homes, a future date, a null coordinate) ----------
        feed = synthetic_feed(); all_l = feed['listings']
        s = Session(browser, 'I', feed=feed, viewport={'width': 1440, 'height': 900}); sessions.append(s)
        pg = s.open()
        check(cards(pg).count() == len(all_l), f'I: {cards(pg).count()} cards, expected {len(all_l)}')
        g = groups(all_l)
        check(g and len(g) == 3, f'I: synthetic coordinates make 3 groups, got {len(g)}')
        pg.wait_for_selector('.leaflet-marker-icon')
        check(pg.locator('.leaflet-marker-icon').count() == 3, f'I: {pg.locator(".leaflet-marker-icon").count()} markers; the null-coordinate home must not get one')
        check(pg.locator('.eb-pin--muted').count() == 1, f'I: exactly one muted pin (the future-dated cottage), found {pg.locator(".eb-pin--muted").count()}')
        check(pg.locator('[data-id="test-studio"]').count() == 1, 'I: the null-coordinate home still gets a card')
        cottage = re.sub(r'\s+', ' ', pg.locator('[data-id="test-cottage"]').inner_text())
        check('HOME' in cottage.upper() and '2 bed · 1 bath · 800 sq ft · available Jan 1' in cottage and '$2,100/mo' in cottage,
              f'I: cottage card reads {cottage!r}')
        # residential
        pg.click('#type-group [data-type="residential"]')
        check(sorted(card_ids(pg)) == sorted(expected(all_l, type='residential')), f'I: Homes shows {card_ids(pg)}')
        check(count_text(pg) == '3 homes open right now.', f'I: Homes count line {count_text(pg)!r}')
        # beds: minimum, residential only
        pg.select_option('#f-beds', '2')
        check(sorted(card_ids(pg)) == sorted(expected(all_l, type='residential', beds=2)), f'I: Homes 2+ beds shows {card_ids(pg)}')
        check(count_text(pg).startswith('2 of 3 homes match.'), f'I: Homes 2+ beds count line {count_text(pg)!r}')
        check(pg.locator('.leaflet-marker-icon').count() == 2, 'I: markers follow the beds filter')
        pg.click('#type-group [data-type="all"]')
        check(sorted(card_ids(pg)) == sorted(expected(all_l, beds=2)) and not any(i.startswith('chs-') for i in card_ids(pg)),
              f'I: All + 2+ beds drops the commercial suites ({card_ids(pg)})')
        pg.select_option('#f-beds', '')
        pg.select_option('#f-sqft', '600')
        check(sorted(card_ids(pg)) == sorted(expected(all_l, sqft=600)), f'I: 600+ sq ft shows {card_ids(pg)} (a home with no size cannot match)')
        pg.select_option('#f-sqft', '')
        pg.select_option('#f-price', '2000')
        check(sorted(card_ids(pg)) == sorted(expected(all_l, price=2000)) and 'test-studio' in card_ids(pg),
              f'I: up to $2,000 shows {card_ids(pg)}')
        # residential empty state is not shown when homes exist but are filtered out
        pg.click('#type-group [data-type="residential"]'); pg.select_option('#f-price', '1000')
        es = re.sub(r'\s+', ' ', pg.text_content('#empty-state'))
        check(cards(pg).count() == 0 and 'Nothing matches that combination' in es and 'homes come and go' not in es,
              f'I: homes exist, so an over-filtered Homes view says so: {es!r}')
        s.ctx.close()

        # ---------- H: mobile ----------
        s = Session(browser, 'H', viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True); sessions.append(s)
        pg = s.open('/listings/')
        check(pg.is_visible('#mobile-toggle') and pg.inner_text('#mobile-toggle').strip() == 'Map', 'H: the pill reads "Map" in List view')
        fs = pg.evaluate("parseFloat(getComputedStyle(document.getElementById('mobile-toggle')).fontSize)")
        fw = pg.evaluate("parseInt(getComputedStyle(document.getElementById('mobile-toggle')).fontWeight)")
        check(fs >= 19 and fw >= 700, f'H: pill label is >=19px bold (got {fs}px / {fw})')
        box = pg.locator('#mobile-toggle').bounding_box()
        check(abs((box['x'] + box['width'] / 2) - 195) < 2 and box['y'] + box['height'] > 844 - 80, f'H: pill is bottom-center ({box})')
        check(cards(pg).count() == n_all and pg.is_visible('#listing-grid'), 'H: the list shows first')
        check(not pg.is_visible('#map'), 'H: the map is not shown in List view')
        check(pg.locator('.leaflet-container').count() == 0, 'H: the map is not built until it is on screen')
        check(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'H: no sideways page scroll in List view')
        bar = pg.evaluate("document.getElementById('filter-bar').getBoundingClientRect().height")
        check(bar < 90, f'H: the sticky filter bar stays short on a phone ({bar}px)')
        pg.click('#mobile-toggle')
        pg.wait_for_selector('.leaflet-container')
        pg.wait_for_selector('.leaflet-marker-icon')
        mb = pg.locator('#map').bounding_box()
        check(pg.is_visible('#map') and mb['height'] > 400 and mb['width'] > 300, f'H: Map view shows a full-height map ({mb})')
        check(not pg.is_visible('#listing-grid'), 'H: the list is hidden in Map view')
        check(pg.inner_text('#mobile-toggle').strip() == 'List', 'H: the pill now reads "List"')
        check(pg.locator('.leaflet-marker-icon').count() == 1, 'H: the marker is on the mobile map')
        pill = pg.locator('#mobile-toggle').bounding_box()
        attrib = pg.locator('.leaflet-control-attribution').bounding_box()
        overlap = not (pill['x'] + pill['width'] <= attrib['x'] or attrib['x'] + attrib['width'] <= pill['x']
                       or pill['y'] + pill['height'] <= attrib['y'] or attrib['y'] + attrib['height'] <= pill['y'])
        check(not overlap, f'H: the pill does not cover the map attribution ({pill} vs {attrib})')
        check(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'H: no sideways page scroll in Map view')
        pg.locator('.leaflet-marker-icon').first.click()
        pg.wait_for_selector('.leaflet-popup .eb-pop-item')
        pb = pg.locator('.leaflet-popup-content-wrapper').bounding_box()
        check(pb['x'] >= 0 and pb['x'] + pb['width'] <= 390, f'H: the popup fits a phone screen ({pb})')
        audit(pg, '#mobile-toggle-wrap', 'H pill')
        pg.click('#mobile-toggle')
        check(pg.is_visible('#listing-grid') and not pg.is_visible('#map'), 'H: List returns to the cards')
        check(pg.inner_text('#mobile-toggle').strip() == 'Map', 'H: the pill reads "Map" again')
        # filters carry over to the mobile map
        pg.select_option('#f-price', '750')
        pg.click('#mobile-toggle')
        pg.locator('.leaflet-marker-icon').first.click()
        pg.wait_for_function("document.querySelectorAll('.leaflet-popup').length === 1")   # the old popup fades out for 200ms
        check(len(popup_items(pg)) == len(expected(LISTINGS, price=750)), 'H: the mobile map shows the filtered set')
        s.ctx.close()

        browser.close()

    # ---------- zero page errors, everywhere ----------
    for s in sessions:
        check(not s.errors, f'{s.tag}: page/console errors: {s.errors[:3]}')
        if s.bad_local is not None:
            check(not s.bad_local, f'{s.tag}: local requests failed: {s.bad_local[:3]}')

    if failures:
        print(f'FAIL: {len(failures)} failure(s), {passed} checks passed')
        for f in failures: print('  -', f)
        sys.exit(1)
    print(f'OK: listings E2E — {passed} checks passed (A cards, B type, C beds, D price, E map, F URL state, '
          f'G flat brand, H mobile, I synthetic feed, J details, K no Leaflet)')


if __name__ == '__main__':
    main()
