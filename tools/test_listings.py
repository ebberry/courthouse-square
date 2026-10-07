#!/usr/bin/env python3
"""End-to-end test for the listings index (/listings/).

Drives the real page in headless Chromium, with the network sealed: Google Fonts are answered locally and the map
runs the REAL vendored MapLibre GL + PMTiles against the committed map/vashon.pmtiles, served by the local server
below (with HTTP Range support, which PMTiles needs), so the test is the same on a laptop, in CI and behind a proxy.

  A. Cards          — /listings/ renders one card per feed entry and the count line agrees
  B. Type           — ?type=commercial preselects Commercial; ?type=residential shows the residential empty state;
                      the homepage's header links land on the right filter
  C. Beds           — the beds select is disabled (and muted) while Commercial is active
  D. Price          — price max filters to exactly the subset computed from data/listings.json
  E. Map            — the basemap really draws (PMTiles over Range requests, brand colors on the canvas); one pin for the
                      one shared coordinate; its popup lists every listing; pins follow filters; panning is locked to the
                      island; place names; attribution
  F. URL state      — filters round-trip through location.search; bad params are ignored; Clear resets
  G. Flat brand     — computed-style audit (no shadows, gradients, pure white/black) on the bar, a card and the map
  H. Mobile         — at 390px the Map / List pill swaps the panes; the map is built lazily; no sideways scroll
  I. Synthetic feed — homes, a future date, a null coordinate: beds semantics, muted pin, no marker without coords
  J. Details        — sticky bar and map, whole-card focus ring, empty/over-filtered/failed-feed states, zero page errors
  K. No map         — if the map library fails to load, the page is still a working filterable list; if only the basemap
                      fails, the Cream map, pins, names and popups still work, with no page errors

Part 2 drives the listing detail pages (/listings/<id>/, generated) and their client-side fallback (/listing.html):

  L. Static page    — a card click on /listings/ lands on /listings/chs-n101/; rent, facts, features, gallery
                      placeholder, location map and the no-JS / no-MapLibre cases, all computed from data/listings.json;
                      the page never loads the fallback script or the feed
  M. Inquiry form   — form name, hidden form-name / listing / building, honeypot, and the POST body a submission sends
  N. Fallback       — /listing.html?id=<id>, /listings/<id>/ through a simulated Netlify rewrite, unknown ids, a feed-only
                      listing, a failed feed, and DOM parity with the generated page (real and synthetic listings)
  O. Structured data— the RealEstateListing JSON-LD parses, carries the right price/address/geo, and escapes hostile text
  P. Flat brand     — computed-style audit of the detail page, one huge element, 390px layout, zero console errors

Part 3 is the accessibility sweep over every page type (homepage, /listings/, a detail page, the building page,
/404.html and the /listing.html fallback), at 1440px and 390px:

  Q. Accessibility  — one h1, banner / main / contentinfo landmarks, an accessible name on every link, button and
                      field, no skipped heading levels, a skip link that is the first Tab stop, shows itself, jumps to
                      <main> and passes AA; every visible text at AA (4.5:1, or 3:1 for large text) at rest and on
                      hover, including an open map popup, the empty states and a populated tenant wall; a visible
                      focus ring of at least 3:1 on every Tab stop; and prefers-reduced-motion honoured (no smooth
                      scrolling, no map animation, the tally counts up instantly)

Requirements: pip install playwright; playwright install chromium (or set CHROME=/path/to/chrome).
Run: python3 tools/test_listings.py
"""

import base64, copy, datetime, glob, http.server, io, json, os, re, socketserver, sys, threading
from urllib.parse import parse_qs, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8190
BASE = f'http://127.0.0.1:{PORT}'
failures = []
passed = 0

# A 1x1 PNG: stands in for the gallery photos that are not in the repo yet.
TILE_PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


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
    """The site as Netlify serves it: static files, the /listings/* rewrite, and single-range requests (bytes=a-b),
    which PMTiles needs to read map/vashon.pmtiles. Netlify does Range natively; SimpleHTTPRequestHandler does not."""
    support_range = True        # tools/test_listings.py is also the proof that the map section FAILS without this
    range_log = []              # (status, Range header or None) for every request of map/vashon.pmtiles

    def log_message(self, *a):
        pass

    def translate_path(self, path):
        """netlify.toml: /listings/*  ->  /listing.html (status 200, not forced). A file or folder that exists
        (/listings/, /listings/chs-n101/) is served as itself; only an unknown /listings/<slug>/ falls through."""
        real = super().translate_path(path)
        if urlsplit(path).path.startswith('/listings/') and not os.path.exists(real):
            return os.path.join(ROOT, 'listing.html')
        return real

    def end_headers(self):
        if self.support_range:
            self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        is_archive = urlsplit(self.path).path == '/map/vashon.pmtiles'
        rng = self.headers.get('Range') if self.support_range else None
        m = re.fullmatch(r'bytes=(\d+)-(\d*)', rng or '')
        if not (m and os.path.isfile(path)):
            f = super().send_head()
            if is_archive:
                Quiet.range_log.append((200 if f else 404, self.headers.get('Range')))
            return f
        size = os.path.getsize(path)
        start = int(m.group(1))
        end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
        if start >= size or end < start:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            if is_archive:
                Quiet.range_log.append((416, rng))
            return None
        with open(path, 'rb') as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if is_archive:
            Quiet.range_log.append((206, rng))
        return io.BytesIO(data)


class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True       # MapLibre asks for several ranges at once


def launch(p):
    chrome = os.environ.get('CHROME')
    candidates = [chrome] + sorted(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome'))
    # MapLibre needs WebGL; headless Chromium draws it in software (SwiftShader), which newer builds only allow when asked.
    args = ['--no-sandbox', '--enable-unsafe-swiftshader']
    for c in candidates:
        if c and os.path.exists(c):
            return p.chromium.launch(executable_path=c, args=args)
    return p.chromium.launch(args=args)   # playwright-managed browser (CI)


class Session:
    """One browser context with the network sealed (only fonts are answered locally) and every problem recorded."""

    def __init__(self, browser, tag, feed=None, feed_status=200, **ctx_kw):
        self.tag = tag
        self.errors = []        # page errors and console errors
        self.bad_local = []     # local requests answered 4xx/5xx
        self.requests = []      # every URL the page asked for
        self.ctx = browser.new_context(**ctx_kw)
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
        self.pg.on('request', lambda r: self.requests.append(r.url))

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

    def open_detail(self, path):
        """A listing detail page (generated or fallback): ready once its h1 exists and the network is quiet."""
        self.pg.goto(BASE + path, wait_until='networkidle')
        self.pg.wait_for_selector('#listing-title', timeout=10000)
        self.pg.wait_for_timeout(150)
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


# The MapLibre instance that draws `sel` (js/eb-map.js keeps every map it makes on EBMap.maps).
MAP_JS = "(sel) => { const el = document.querySelector(sel); return el && (window.EBMap.maps || []).find(m => m.getContainer() === el); }"

# True once the PMTiles source has loaded and MapLibre has drawn features from it (the earth and water of the archive).
MAP_DRAWN_JS = ("(sel) => { const m = (" + MAP_JS + ")(sel);"
                " return !!(m && m.loaded() && m.isSourceLoaded('vashon') && m.queryRenderedFeatures({layers: ['earth', 'water']}).length > 0); }")

# Colors actually on the WebGL canvas: read the pixels right after a render (no preserveDrawingBuffer needed), on a grid.
PIXELS_JS = r"""(sel) => new Promise(resolve => {
  const m = (%s)(sel);
  m.once('render', () => {
    const c = m.getCanvas(), gl = c.getContext('webgl2') || c.getContext('webgl');
    const w = c.width, h = c.height, px = new Uint8Array(4), out = {};
    for (let i = 1; i < 24; i++) for (let j = 1; j < 24; j++) {
      gl.readPixels(Math.floor(w * i / 24), Math.floor(h * j / 24), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const k = px[0] + ',' + px[1] + ',' + px[2] + ',' + px[3];
      out[k] = (out[k] || 0) + 1;
    }
    resolve(out);
  });
  m.triggerRepaint();
})""" % MAP_JS


def wait_map_drawn(pg, sel='#map', timeout=20000):
    """Wait until the basemap has drawn; if it never does, record that as a failure (and carry on) instead of crashing."""
    try:
        pg.wait_for_function(MAP_DRAWN_JS, arg=sel, timeout=timeout)
        return True
    except Exception:
        check(False, f'{sel}: the basemap never drew (the PMTiles source did not load, or MapLibre drew nothing from it)')
        return False


def close_to(rgb, want, tol=3):
    return all(abs(a - b) <= tol for a, b in zip(rgb[:3], want))


def popup_items(pg):
    return pg.eval_on_selector_all('.maplibregl-popup .eb-pop-item',
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


# ---------------------------------------------------------------- part 2: listing detail pages (L-P)

BY_ID = {L['id']: L for L in LISTINGS}
UPDATED = DOC['updated']
BUILDINGS = {b['id']: b for b in json.load(open(os.path.join(ROOT, 'data/buildings.json'), encoding='utf-8'))['buildings']}
BERRY, CREAM, MUSTARD, SAND = 'rgb(103, 10, 47)', 'rgb(241, 236, 233)', 'rgb(232, 196, 80)', 'rgb(241, 221, 183)'
PHOTOS = ['/images/og-card-eberry.png', '/images/og-card.png', '/images/favicon.svg']   # real files the server can serve


def ws(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def plain(n):
    return int(n) if float(n).is_integer() else n


def human_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f'{d.strftime("%b")} {d.day}, {d.year}'


def expected_facts(L):
    """The fact tiles a listing should show, computed from its data (not from the page code)."""
    out = []
    if L['sqft'] is not None: out.append(f"{plain(L['sqft']):,} sq ft")
    if L['beds'] is not None: out.append(f"{plain(L['beds']):,} bed")
    if L['baths'] is not None: out.append(f"{plain(L['baths']):,} bath")
    out.append('Available now' if L['available'] is None or L['available'] <= datetime.date.today().isoformat()
               else f"Available {human_date(L['available'])}")
    allin = next((f for f in L['features'] if f.lower().startswith('all-in pricing')), None)
    if allin:
        note = allin.split(' — ', 1)[1].strip() if ' — ' in allin else ''
        out.append('All-in pricing' + (' ' + note[:1].upper() + note[1:] if note else ''))
    return out


def facts_of(pg):
    return [ws(t) for t in pg.locator('#listing-facts li').all_inner_texts()]


# A compact signature of everything inside <main>: the same listing must give the same one on the generated page and on
# the fallback. Attributes that carry the layout and the behaviour are kept; the live map's own DOM is left out.
SIG_JS = r"""
() => {
  const KEEP = ['class', 'id', 'href', 'src', 'alt', 'name', 'value', 'type', 'for', 'role', 'rows', 'loading', 'method',
                'required', 'autocomplete', 'netlify-honeypot', 'data-netlify', 'aria-label', 'aria-labelledby', 'aria-hidden'];
  const out = [];
  const walk = (el, depth) => {
    const attrs = KEEP.filter(a => el.hasAttribute(a)).map(a => {
      let v = el.getAttribute(a);
      if (a === 'class' && el.id === 'listing-map-wrap') v = v.split(/\s+/).filter(c => c !== 'hidden').join(' ');
      if (a === 'class' && el.id === 'listing-map') return null;      // MapLibre adds its own classes
      return a + '=' + v;
    }).filter(Boolean);
    if (el.id === 'listing-map') attrs.push(...[...el.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name + '=' + a.value));
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').replace(/\s+/g, ' ').trim();
    out.push(depth + ' <' + el.tagName.toLowerCase() + '> ' + attrs.join(' ') + (own ? ' :: ' + own : ''));
    if (el.id === 'listing-map') return;
    [...el.children].forEach(c => walk(c, depth + 1));
  };
  [...document.getElementById('main').children].forEach(c => walk(c, 0));
  return out;
}
"""

# The biggest type on the page, with where it sits.
SIZES_JS = r"""
() => {
  const sizes = [];
  const walker = document.createTreeWalker(document.getElementById('main'), NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.textContent.trim()) continue;
    const el = n.parentElement, cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    sizes.push({ size: parseFloat(cs.fontSize), inRent: !!el.closest('#listing-rent'), text: n.textContent.trim().slice(0, 30) });
  }
  sizes.sort((a, b) => b.size - a.size);
  return sizes;
}
"""


def assert_detail(pg, L, tag, building=None, photos=None):
    """Everything a detail page shows for listing L, checked against L itself. `building` is the buildings.json entry
    the "Part of" link should name (or None); `photos` the photo paths that should be in the grid."""
    commercial = L['type'] == 'commercial'
    check(ws(pg.inner_text('#listing-title')) == L['title'], f'{tag}: h1 is {pg.inner_text("#listing-title")!r}, expected {L["title"]!r}')
    check(pg.locator('h1').count() == 1, f'{tag}: exactly one h1')
    badge = pg.evaluate("document.getElementById('listing-title').previousElementSibling.textContent.trim()")
    check(badge == ('Commercial' if commercial else 'Home'), f'{tag}: type badge reads {badge!r}')
    bg = pg.evaluate("getComputedStyle(document.getElementById('listing-title').previousElementSibling).backgroundColor")
    check(bg == (MUSTARD if commercial else SAND), f'{tag}: badge is {"Mustard" if commercial else "Sand"} (got {bg})')
    check(ws(pg.inner_text('main address >> nth=0')) == L['address'], f'{tag}: address line')
    check(ws(pg.inner_text('#listing-rent')) == f"{money(L['rent'])} /month", f'{tag}: rent reads {ws(pg.inner_text("#listing-rent"))!r}')
    check(facts_of(pg) == expected_facts(L), f'{tag}: fact tiles {facts_of(pg)}, expected {expected_facts(L)}')
    summary = ws(L['summary'])
    if summary:
        check(ws(pg.inner_text('#listing-summary')) == summary, f'{tag}: summary text')
    else:
        check(pg.locator('#listing-summary').count() == 0, f'{tag}: no empty summary paragraph')
    feats = [f for f in L['features'] if f.strip()]
    got = [ws(t) for t in pg.locator('#listing-features li').all_inner_texts()]
    check(got == feats, f'{tag}: feature tags {got}, expected {feats}')
    if feats:
        look = pg.evaluate("""() => { const cs = getComputedStyle(document.querySelector('#listing-features li'));
                                      return { bg: cs.backgroundColor, color: cs.color, radius: cs.borderTopLeftRadius }; }""")
        check(look == {'bg': MUSTARD if commercial else SAND, 'color': BERRY, 'radius': '4px'}, f'{tag}: feature tags are flat {look}')
    else:
        check(pg.locator('#listing-features').count() == 0, f'{tag}: no empty tag list')
    # gallery
    if photos:
        srcs = pg.eval_on_selector_all('#listing-photos img', 'els => els.map(e => e.getAttribute("src"))')
        alts = pg.eval_on_selector_all('#listing-photos img', 'els => els.map(e => e.getAttribute("alt"))')
        check(srcs == photos and alts == [f"{L['title']}, photo {i}" for i in range(1, len(photos) + 1)], f'{tag}: photo grid {srcs} {alts}')
        check(pg.locator('#listing-photos-placeholder').count() == 0, f'{tag}: no placeholder when there are photos')
        wide = pg.eval_on_selector_all('#listing-photos li', 'els => els.map(e => e.classList.contains("sm:col-span-2"))')
        check(wide == [len(photos) % 2 == 1] + [False] * (len(photos) - 1), f'{tag}: first photo spans two columns only for an odd count ({wide})')
        radius = pg.evaluate("getComputedStyle(document.querySelector('#listing-photos li')).borderTopLeftRadius")
        check(radius == '24px', f'{tag}: photo tiles have a 24px radius ({radius})')
    else:
        check(pg.locator('#listing-photos').count() == 0 and pg.locator('#listing-photos-placeholder').count() == 1,
              f'{tag}: ONE placeholder band and no grid')
        check(ws(pg.inner_text('#listing-photos-placeholder')) == "Photos are coming — ask me and I'll walk you through in person.",
              f'{tag}: placeholder copy')
        look = pg.evaluate("""() => { const el = document.getElementById('listing-photos-placeholder'), cs = getComputedStyle(el), p = getComputedStyle(el.querySelector('p'));
                                      return { bg: cs.backgroundColor, color: p.color, italic: p.fontStyle, mono: el.querySelector('img').getAttribute('src') }; }""")
        check(look == {'bg': BERRY, 'color': CREAM, 'italic': 'italic', 'mono': '/images/brand/monogram-tangerine-bare.svg'},
              f'{tag}: placeholder is a Berry block with the bare monogram and Cream italic type {look}')
    # breadcrumb
    crumbs = pg.eval_on_selector_all('nav[aria-label="Breadcrumb"] a', 'els => els.map(e => [e.getAttribute("href"), e.textContent.trim()])')
    want = [['/listings/', "← Everything that's open"]]
    if building:
        want.append([f"/buildings/{building['id']}/", f"Part of {building['name']} →"])
    check(crumbs == want, f'{tag}: breadcrumb {crumbs}, expected {want}')
    # inquiry form
    hidden = pg.eval_on_selector_all('#inquire input[type=hidden]', 'els => Object.fromEntries(els.map(e => [e.name, e.value]))')
    check(hidden == {'form-name': 'listing-inquiry', 'listing': L['id'], 'building': building['id'] if building else ''},
          f'{tag}: hidden inputs {hidden}')
    # location
    field = pg.evaluate("document.getElementById('location').className")
    check(('eb-field-mustard' if commercial else 'eb-field-sand') in field, f'{tag}: location field color ({field})')
    has_coords = L['lat'] is not None and L['lng'] is not None
    osm = pg.get_attribute('#location a[href^="https://www.openstreetmap.org/"]', 'href')
    if has_coords:
        check(pg.locator('#listing-map').count() == 1, f'{tag}: location has the map div')
        check((pg.get_attribute('#listing-map', 'data-lat'), pg.get_attribute('#listing-map', 'data-lng'))
              == (str(L['lat']), str(L['lng'])), f'{tag}: map data-lat/data-lng')
        check(osm == f"https://www.openstreetmap.org/?mlat={L['lat']}&mlon={L['lng']}#map=17/{L['lat']}/{L['lng']}", f'{tag}: OSM link {osm}')
    else:
        check(pg.locator('#listing-map').count() == 0 and pg.locator('#listing-map-wrap').count() == 0, f'{tag}: no map block without coordinates')
        check(osm and osm.startswith('https://www.openstreetmap.org/search?query='), f'{tag}: OSM search link {osm}')


def synthetic_listings():
    """Listings the feed could carry that the committed pages do not cover: homes, photos (odd and even), a future date,
    no coordinates, no building, an empty summary, hostile characters."""
    base = copy.deepcopy(LISTINGS[0])
    def mk(id, **kw):
        h = dict(base)
        h.update(id=id, type='residential', photos=[], features=[], summary='', lat=47.4000, lng=-122.4600, available=None,
                 beds=None, baths=None, sqft=None)
        h.update(kw)
        h.pop('buildingId', None)
        return h
    out = [
        mk('test-cottage', title='Cottage on Bank Road', address='21500 Bank Rd SW, Vashon, WA 98070', rent=2100, beds=2, baths=1, sqft=800,
           available='2099-01-01', photos=PHOTOS, features=['Wood stove', 'Fenced garden'],
           summary='A warm   little place\n with a view.'),
        mk('test-farmhouse', title='Farmhouse near the Pond', address='9 Pond Ln, Vashon, WA 98070', rent=2900, beds=3, baths=1.5, sqft=1400,
           lat=47.3800, lng=-122.4900, photos=PHOTOS[:2], features=['Room for chickens'], summary='Quiet, with room to roam.'),
        mk('test-studio', title='Studio above the Shop', address='Somewhere near the ferry', rent=1200, beds=1, baths=1,
           lat=None, lng=None, features=['All-in pricing'], summary=''),
        mk('test-hostile', title='Suite <img src=x onerror=alert(1)> & "Co" — Test', address='1 <b>Main</b> St, Vashon, WA 98070', rent=950,
           type='commercial', sqft=120, features=['5 < 6 & "quoted" </script>'], summary='Nothing </script><script>alert(1)</script> here.',
           buildingId='courthouse-square'),
    ]
    return out


def part2(browser, sessions):
    import importlib.util
    sys.dont_write_bytecode = True                  # importing the generator must not leave a __pycache__ in tools/
    spec = importlib.util.spec_from_file_location('build_pages', os.path.join(ROOT, 'tools', 'build_pages.py'))
    bp = importlib.util.module_from_spec(spec); spec.loader.exec_module(bp)
    ctx_pages = bp.load_context()
    L1 = BY_ID['chs-n101']
    cs = BUILDINGS['courthouse-square']

    # ---------- L: the generated page, reached the way a visitor reaches it ----------
    s = Session(browser, 'L', viewport={'width': 1440, 'height': 900}); sessions.append(s)
    pg = s.open('/listings/')
    mark = len(s.requests)                                 # everything after this belongs to the detail page
    pg.click('#listing-grid [data-id="chs-n101"] .listing-card-link')
    pg.wait_for_url(BASE + '/listings/chs-n101/')
    pg.wait_for_selector('#listing-rent'); pg.wait_for_load_state('networkidle')
    check(pg.url == BASE + '/listings/chs-n101/', f'L: card click lands on {pg.url}')
    check(pg.title() == f"{L1['title']} — {money(L1['rent'])}/mo on Vashon — E. Berry Property Management", f'L: title is {pg.title()!r}')
    check(pg.get_attribute('link[rel=canonical]', 'href') == 'https://eberryvashon.com/listings/chs-n101/', 'L: canonical URL')
    check(pg.get_attribute('meta[name=description]', 'content') == ' '.join(L1['summary'].split()), 'L: meta description is the summary')
    check(pg.get_attribute('meta[property="og:image"]', 'content') == 'https://eberryvashon.com/images/og-card-eberry.png', 'L: og:image falls back to the brand card')
    check(pg.get_attribute('meta[property="og:type"]', 'content') == 'website', 'L: og:type website')
    check(pg.locator('meta[name="robots"]').count() == 0, 'L: the generated page is indexable (no robots meta)')
    check(money(L1['rent']) == '$1,181', 'L: the data still says $1,181 (update this test if the rent changed)')
    assert_detail(pg, L1, 'L chs-n101', building=cs, photos=None)
    check(facts_of(pg) == ['259 sq ft', 'Available now', 'All-in pricing Rent, CAM & shared utilities'], f'L: chs-n101 facts {facts_of(pg)}')
    check('A PART OF WINDERMERE VASHON' in pg.inner_text('header'), 'L: the firm-ID line is in the header')
    flat = pg.evaluate("""() => { const cs = getComputedStyle(document.querySelector('#listing-facts li'));
                                  return { bg: cs.backgroundColor, border: cs.borderTopColor, w: cs.borderTopWidth, r: cs.borderTopLeftRadius }; }""")
    flat['w'] = '1.5px' if flat['w'] in ('1px', '1.5px') else flat['w']      # Chromium rounds a 1.5px border to 1px at 1x
    check(flat == {'bg': CREAM, 'border': BERRY, 'w': '1.5px', 'r': '12px'}, f'L: fact tiles are flat Cream with a thin Berry border {flat}')
    # the static page is just HTML: no fallback script, no feed
    later = s.requests[mark:]
    check(not any('listing-detail.js' in u or u.endswith('/data/listings.json') for u in later),
          f'L: the generated page must not load the fallback script or the feed ({[u for u in later if "listing-detail" in u or "listings.json" in u]})')
    # the map: lazy, one pin, the real basemap, attribution, no popup back to itself
    check(pg.locator('.maplibregl-map').count() == 0, 'L: the map is not built until it is near the screen')
    Quiet.range_log.clear()
    pg.locator('#listing-map').scroll_into_view_if_needed()
    pg.wait_for_selector('#listing-map .eb-pin', timeout=10000)
    wait_map_drawn(pg, '#listing-map')
    check(pg.locator('#listing-map .eb-pin').count() == 1, 'L: one pin on the single-listing map')
    check(any(st == 206 for st, _ in Quiet.range_log), f'L: this page read the archive with Range requests ({Quiet.range_log[:3]})')
    zoom = pg.evaluate("(%s)('#listing-map').getZoom()" % MAP_JS)
    check(zoom == 15.5, f'L: the single-listing map opens as close as the map goes, zoom 15.5 (got {zoom})')
    attr = ws(pg.text_content('#listing-map .maplibregl-ctrl-attrib'))
    check('© OpenStreetMap' in attr and 'Protomaps' in attr and pg.is_visible('#listing-map .maplibregl-ctrl-attrib'), f'L: attribution reads {attr!r}')
    check(pg.get_attribute('#listing-map .maplibregl-ctrl-attrib a', 'href') == 'https://www.openstreetmap.org/copyright', 'L: attribution links to the OSM copyright page')
    check(pg.get_attribute('#listing-map', 'role') == 'region' and 'Suite N101' in (pg.get_attribute('#listing-map', 'aria-label') or ''),
          'L: map is a labelled region')
    check(pg.get_attribute('#listing-map .eb-pin', 'role') == 'img' and pg.get_attribute('#listing-map .eb-pin', 'tabindex') is None,
          'L: a pin with no popup is a plain picture, not a button')
    pg.locator('#listing-map .eb-pin').click(); pg.wait_for_timeout(400)
    check(pg.locator('.maplibregl-popup').count() == 0, 'L: no popup that links back to the same page')
    # the whole page works without JS: everything is in the HTML
    ctx_nojs = browser.new_context(java_script_enabled=False, viewport={'width': 1440, 'height': 900})
    ctx_nojs.route(re.compile(r'^https://fonts\.'), lambda r: r.abort())
    npg = ctx_nojs.new_page(); npg.goto(BASE + '/listings/chs-n101/', wait_until='load')
    check(ws(npg.inner_text('#listing-rent')) == '$1,181 /month' and facts_of(npg) == expected_facts(L1), 'L: rent and facts are in the HTML, no JS needed')
    check(npg.is_visible('#inquire form') and not npg.is_visible('#listing-map-wrap'), 'L: without JS the form is there and the empty map box is not')
    check(npg.is_visible('#location a[href^="https://www.openstreetmap.org/"]'), 'L: without JS the OpenStreetMap link remains')
    ctx_nojs.close()
    s.ctx.close()

    # every generated page matches its listing
    for L in LISTINGS:
        s2 = Session(browser, f'L-{L["id"]}', viewport={'width': 1440, 'height': 900}); sessions.append(s2)
        pg = s2.open_detail(f'/listings/{L["id"]}/')
        b = BUILDINGS.get(L.get('buildingId'))
        assert_detail(pg, L, f'L {L["id"]}', building=b, photos=None)
        check(pg.title() == f"{L['title']} — {money(L['rent'])}/mo on Vashon — E. Berry Property Management", f'L {L["id"]}: title')
        s2.ctx.close()

    # MapLibre will not load: the address and the OpenStreetMap link carry the location
    s = Session(browser, 'L-nomap', viewport={'width': 1440, 'height': 900}); sessions.append(s)
    s.ctx.route('**/js/vendor/maplibre-gl.js', lambda r: r.abort())
    pg = s.open_detail('/listings/chs-n101/')
    check(not pg.is_visible('#listing-map-wrap') and pg.is_visible('#location address') and pg.is_visible('#location a[href^="https://www.openstreetmap.org/"]'),
          'L: without MapLibre the map box stays hidden and the address + OpenStreetMap link stand')
    s.errors = [e for e in s.errors if 'Failed to load resource' not in e]
    s.ctx.close()

    # ---------- M: the inquiry form ----------
    s = Session(browser, 'M', viewport={'width': 1440, 'height': 900}); sessions.append(s)
    pg = s.pg
    posts = []
    def catch(route):
        req = route.request
        if req.method == 'POST':
            posts.append(req.post_data or '')
            route.fulfill(status=200, content_type='text/html', body='<p>thanks</p>')
        else:
            route.continue_()
    pg.route('**/listings/chs-n101/', catch)
    s.open_detail('/listings/chs-n101/')
    form = pg.locator('form[name="listing-inquiry"]')
    check(form.count() == 1 and pg.locator('#inquire').count() == 1, 'M: one form named listing-inquiry inside #inquire')
    check(form.get_attribute('data-netlify') == 'true' and form.get_attribute('netlify-honeypot') == 'bot-field' and form.get_attribute('method').lower() == 'post',
          'M: Netlify form attributes (data-netlify, honeypot, POST)')
    hidden = pg.eval_on_selector_all('#inquire input[type=hidden]', 'els => els.map(e => [e.name, e.value])')
    check(hidden == [['form-name', 'listing-inquiry'], ['listing', 'chs-n101'], ['building', 'courthouse-square']], f'M: hidden inputs {hidden}')
    check(pg.locator('#inquire input[name="bot-field"]').count() == 1 and not pg.is_visible('#inquire input[name="bot-field"]'), 'M: the honeypot exists and is hidden')
    check(pg.get_attribute('#inquire input[name=name]', 'required') is not None and pg.get_attribute('#inquire input[name=email]', 'required') is not None
          and pg.get_attribute('#inquire input[name=email]', 'type') == 'email', 'M: name and email are required, email is typed')
    check(pg.get_attribute('#inquire input[name=phone]', 'required') is None, 'M: phone is optional')
    opts = pg.eval_on_selector_all('#inquire select[name=timeframe] option', 'els => els.map(e => e.textContent.trim())')
    check(opts == ['Choose one', 'As soon as possible', '1–3 months', 'Later', 'Just curious'], f'M: timeframe options {opts}')
    check(ws(pg.inner_text('#inquire label:has(textarea)')) == 'Anything I should know?', 'M: message label')
    btn = pg.locator('#inquire button[type=submit]')
    check(ws(btn.inner_text()) == 'Ask about this space' and 'eb-btn' in btn.get_attribute('class'), 'M: the submit pill reads "Ask about this space"')
    fs = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#inquire button[type=submit]')).fontSize)")
    fw = pg.evaluate("parseInt(getComputedStyle(document.querySelector('#inquire button[type=submit]')).fontWeight)")
    check(fs >= 19 and fw >= 700, f'M: pill label is >=19px bold ({fs}px / {fw})')
    # an empty submit is stopped by the browser; a filled one POSTs every field, including the hidden ones
    btn.click(); pg.wait_for_timeout(200)
    check(not posts, 'M: an empty form does not submit')
    pg.fill('#inquire input[name=name]', 'Pat Example'); pg.fill('#inquire input[name=email]', 'pat@example.com')
    pg.fill('#inquire input[name=phone]', '206-555-0100'); pg.select_option('#inquire select[name=timeframe]', '1–3 months')
    pg.fill('#inquire textarea[name=message]', 'Is there room for a second chair?')
    btn.click(); pg.wait_for_timeout(600)
    sent = {k: v[0] for k, v in parse_qs(posts[0] if posts else '').items()}      # blank fields (the honeypot) are dropped
    check(sent == {'form-name': 'listing-inquiry', 'listing': 'chs-n101', 'building': 'courthouse-square', 'name': 'Pat Example',
                   'email': 'pat@example.com', 'phone': '206-555-0100', 'timeframe': '1–3 months',
                   'message': 'Is there room for a second chair?'}, f'M: POST body {sent}')
    s.ctx.close()

    # ---------- N: the client-side fallback ----------
    L4 = BY_ID['chs-n204']
    s = Session(browser, 'N', viewport={'width': 1440, 'height': 900}); sessions.append(s)
    pg = s.open_detail('/listing.html?id=chs-n204')
    check(pg.get_attribute('meta[name=robots]', 'content') == 'noindex', 'N: listing.html is noindex')
    check(pg.title() == f"{L4['title']} — {money(L4['rent'])}/mo on Vashon — E. Berry Property Management", f'N: the tab title follows the listing ({pg.title()!r})')
    assert_detail(pg, L4, 'N ?id=chs-n204', building=cs, photos=None)
    check(ws(pg.inner_text('#listing-rent')) == f"{money(L4['rent'])} /month" and 'N204' in pg.inner_text('#listing-title'), 'N: ?id=chs-n204 renders N204')
    check(pg.locator('link[rel=canonical]').count() == 0, 'N: the fallback has no canonical (it is noindex)')
    check(pg.locator('script[type="application/ld+json"]').count() == 0, 'N: no structured data on the fallback')
    check('A PART OF WINDERMERE VASHON' in pg.inner_text('header'), 'N: the shell is there')
    pg.locator('#listing-map').scroll_into_view_if_needed()
    pg.wait_for_selector('#listing-map .eb-pin', timeout=10000)
    wait_map_drawn(pg, '#listing-map')
    check(pg.locator('#listing-map .eb-pin').count() == 1, 'N: the fallback builds the same single-pin map')
    check(pg.locator('#listing-map .eb-pin[role="img"]').count() == 1, 'N: and, like the generated page, its pin has no popup')
    # unknown id and no id: the brand's not-found page
    for path, label in (('/listing.html?id=bogus', '?id=bogus'), ('/listing.html', 'no id'), ('/listings/not-a-real-slug/', 'rewrite /listings/not-a-real-slug/')):
        pg = s.open_detail(path)
        check(ws(pg.inner_text('#listing-title')) == "That one isn't on my list just now.", f'N {label}: not-found heading')
        check(pg.get_attribute('main a[href="/listings/"]', 'href') == '/listings/' and pg.is_visible('main a[href="/listings/"]'), f'N {label}: links back to /listings/')
        check(pg.locator('#listing-rent').count() == 0 and pg.locator('#inquire').count() == 0, f'N {label}: no listing is drawn')
        check(pg.get_attribute('meta[name=robots]', 'content') == 'noindex', f'N {label}: still noindex')
    # the rewrite is not forced: real pages are served as files, not as the fallback
    pg.goto(BASE + '/listings/chs-n101/', wait_until='networkidle')
    check(pg.locator('meta[name=robots]').count() == 0 and pg.locator('script[src="/js/listing-detail.js"]').count() == 0,
          'N: /listings/chs-n101/ is its own generated file, not the rewrite')
    pg.goto(BASE + '/listings/', wait_until='networkidle')
    check(pg.locator('#filter-bar').count() == 1, 'N: /listings/ is the index, not the rewrite')
    s.ctx.close()

    # the fallback page's noscript message
    ctx_nojs = browser.new_context(java_script_enabled=False)
    ctx_nojs.route(re.compile(r'^https://fonts\.'), lambda r: r.abort())
    npg = ctx_nojs.new_page(); npg.goto(BASE + '/listing.html?id=chs-n101', wait_until='load')
    check(npg.is_visible('main a[href="/listings/"]'), 'N: without JS the fallback still points at /listings/')
    ctx_nojs.close()

    # a listing that is in the feed but has no generated page: homes, photos, future date, no coordinates, hostile text
    synth = synthetic_listings()
    feed = copy.deepcopy(DOC); feed['listings'] += synth
    s = Session(browser, 'N-feed', feed=feed, viewport={'width': 1440, 'height': 900}); sessions.append(s)
    for L in synth:
        pg = s.open_detail(f'/listings/{L["id"]}/')            # served through the simulated rewrite
        check(pg.get_attribute('meta[name=robots]', 'content') == 'noindex' and pg.locator('#listing-rent').count() == 1,
              f'N {L["id"]}: a feed-only listing is drawn by the fallback')
        b = BUILDINGS.get(L.get('buildingId'))
        assert_detail(pg, L, f'N {L["id"]}', building=b, photos=L['photos'] or None)
    pg = s.open_detail('/listings/test-cottage/')
    check('Available Jan 1, 2099' in facts_of(pg) and '2 bed' in facts_of(pg) and '1 bath' in facts_of(pg) and '800 sq ft' in facts_of(pg), f'N: cottage facts {facts_of(pg)}')
    check(pg.title().startswith('Cottage on Bank Road — $2,100/mo on Vashon'), 'N: cottage tab title')
    check(pg.locator('#listing-map').count() == 1, 'N: the cottage has coordinates, so a map')
    pg = s.open_detail('/listings/test-studio/')
    check(pg.locator('#listing-map-wrap').count() == 0 and 'Find it on OpenStreetMap' in pg.inner_text('#location'), 'N: the studio has no coordinates, so no map')
    check(facts_of(pg) == ['1 bed', '1 bath', 'Available now', 'All-in pricing'], f'N: studio facts {facts_of(pg)}')
    pg = s.open_detail('/listings/test-hostile/')
    check(pg.locator('#listing-title img').count() == 0 and pg.evaluate('window.__pwned === undefined'), 'N: hostile markup in the feed stays text')
    check(ws(pg.inner_text('#listing-title')) == synth[3]['title'], 'N: hostile title is shown literally')
    s.ctx.close()

    # the feed will not load
    s = Session(browser, 'N-fail', feed_status=500, viewport={'width': 1440, 'height': 900}); sessions.append(s)
    s.bad_local = None
    pg = s.open_detail('/listing.html?id=chs-n101')
    check(ws(pg.inner_text('#listing-title')) == "I couldn't load this just now." and pg.locator('main a[href="mailto:me@ebberry.com"]').count() == 1
          and pg.locator('main a[href="/listings/"]').count() == 1, 'N: failed-feed page offers email and /listings/')
    s.errors = [e for e in s.errors if 'status of 500' not in e]
    s.ctx.close()

    # DOM parity: the fallback draws exactly what the generator writes, for real and synthetic listings
    feed = copy.deepcopy(DOC); feed['listings'] += synth
    ctx_pages['listings'] = synth
    ctx_pages['updated'] = UPDATED
    static_html = {L['id']: bp.render_listing_page(L, ctx_pages) for L in synth}
    check('maplibre' not in static_html['test-studio'].lower() and 'pmtiles' not in static_html['test-studio'].lower()
          and 'listing-map' not in static_html['test-studio'], 'N: a page with no coordinates ships no map markup and no MapLibre')
    check('maplibre-gl.js' in static_html['test-cottage'] and 'pmtiles.js' in static_html['test-cottage'] and 'maplibre-gl.css' in static_html['test-cottage'],
          'N: a page with coordinates loads MapLibre, PMTiles and the skin')
    sp = Session(browser, 'N-parity-static', viewport={'width': 1440, 'height': 900}); sessions.append(sp)
    sf = Session(browser, 'N-parity-fallback', feed=feed, viewport={'width': 1440, 'height': 900}); sessions.append(sf)
    def serve_static(route):
        sid = route.request.url.rstrip('/').rsplit('/', 1)[1]
        route.fulfill(status=200, content_type='text/html', body=static_html[sid])
    for sid in static_html:
        sp.ctx.route(f'**/listings/{sid}/', serve_static)
    pairs = [(L['id'], f'/listings/{L["id"]}/') for L in LISTINGS] + [(L['id'], f'/listings/{L["id"]}/') for L in synth]
    for lid, path in pairs:
        a = sp.open_detail(path).evaluate(SIG_JS)
        b = sf.open_detail(path.replace('/listings/', '/listing.html?id=').rstrip('/')).evaluate(SIG_JS)
        diff = next(((i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
        check(a == b and len(a) > 40, f'N parity {lid}: static and fallback DOMs differ at {diff} (lengths {len(a)} / {len(b)})')
    sp.ctx.close(); sf.ctx.close()

    # ---------- O: structured data ----------
    for L in LISTINGS:
        html = open(os.path.join(ROOT, 'listings', L['id'], 'index.html'), encoding='utf-8').read()
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        try:
            ld = json.loads(m.group(1))
        except Exception as e:
            check(False, f'O {L["id"]}: JSON-LD does not parse ({e})'); continue
        street = L['address'].rsplit(', Vashon, WA 98070', 1)[0]
        want = {'@context': 'https://schema.org', '@type': 'RealEstateListing', 'url': f'https://eberryvashon.com/listings/{L["id"]}/',
                'name': L['title'], 'datePosted': UPDATED}
        check(all(ld.get(k) == v for k, v in want.items()), f'O {L["id"]}: JSON-LD head fields {ld}')
        check(ld['description'] == ' '.join(L['summary'].split()), f'O {L["id"]}: JSON-LD description is the summary')
        check(ld['offers'] == {'@type': 'Offer', 'price': L['rent'], 'priceCurrency': 'USD', 'availability': 'https://schema.org/InStock',
                               'businessFunction': 'http://purl.org/goodrelations/v1#LeaseOut'}, f'O {L["id"]}: offers {ld["offers"]}')
        about = ld['about']
        check(about['@type'] == ('Place' if L['type'] == 'commercial' else 'Residence')
              and about['address'] == {'@type': 'PostalAddress', 'streetAddress': street, 'addressLocality': 'Vashon', 'addressRegion': 'WA',
                                       'postalCode': '98070', 'addressCountry': 'US'}, f'O {L["id"]}: about.address {about}')
        check(about.get('geo') == {'@type': 'GeoCoordinates', 'latitude': L['lat'], 'longitude': L['lng']}, f'O {L["id"]}: about.geo')
    s = Session(browser, 'O', viewport={'width': 1440, 'height': 900}); sessions.append(s)
    pg = s.open_detail('/listings/chs-n101/')
    ld = pg.evaluate("JSON.parse(document.querySelector('script[type=\"application/ld+json\"]').textContent)")
    check(ld['@type'] == 'RealEstateListing' and ld['offers']['price'] == L1['rent'] and isinstance(ld['offers']['price'], (int, float)),
          f'O: the browser parses the JSON-LD and offers.price is the rent ({ld["offers"]["price"]!r})')
    s.ctx.close()
    # hostile text cannot break out of the JSON-LD script, and null coordinates leave out geo
    hostile = static_html['test-hostile']
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', hostile, re.S)
    ld = json.loads(m.group(1))
    check(ld['name'] == synth[3]['title'] and '<' not in m.group(1) and ld['about']['@type'] == 'Place', 'O: hostile title survives JSON-LD intact with "<" escaped')
    check('<img src=x onerror' not in hostile and '</script><script>alert' not in hostile, 'O: hostile text is escaped in the HTML')
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', static_html['test-studio'], re.S)
    ld = json.loads(m.group(1))
    check('geo' not in ld['about'] and ld['about']['@type'] == 'Residence', 'O: no coordinates, no geo; a home is a Residence')
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', static_html['test-cottage'], re.S)
    ld = json.loads(m.group(1))
    check(ld['image'] == 'https://eberryvashon.com' + PHOTOS[0], 'O: with a photo on disk, image and og:image are the first photo')
    check(f'<meta property="og:image" content="https://eberryvashon.com{PHOTOS[0]}" />' in static_html['test-cottage'], 'O: og:image is the first photo (absolute URL)')

    # ---------- P: flat brand, one huge element, phone layout, console ----------
    s = Session(browser, 'P', viewport={'width': 1440, 'height': 900}); sessions.append(s)
    pg = s.open_detail('/listings/chs-n101/')
    audit(pg, 'body', 'P detail page')
    sizes = pg.evaluate(SIZES_JS)
    check(sizes[0]['inRent'] and sizes[0]['size'] >= 160, f'P: the rent is the huge element ({sizes[0]})')
    nxt = next(x for x in sizes if not x['inRent'])
    check(sizes[0]['size'] >= 2 * nxt['size'], f'P: the rent is at least twice the next-biggest type ({sizes[0]["size"]} vs {nxt})')
    check(nxt['size'] <= 56, f'P: nothing else is huge (next {nxt})')
    check(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'P: no sideways scroll on desktop')
    s.ctx.close()
    s = Session(browser, 'P-fallback', viewport={'width': 1440, 'height': 900}); sessions.append(s)
    pg = s.open_detail('/listing.html?id=chs-n101')
    audit(pg, 'body', 'P fallback page')
    s.ctx.close()
    s = Session(browser, 'P-mobile', viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True); sessions.append(s)
    pg = s.open_detail('/listings/chs-n101/')
    check(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'P: no sideways page scroll at 390px')
    r = pg.evaluate("(() => { const b = document.querySelector('#listing-rent span').getBoundingClientRect(); return { right: b.right, left: b.left, h: b.height }; })()")
    check(r['left'] >= 0 and r['right'] <= 390 and r['h'] < 100, f'P: the rent fits on one line at 390px ({r})')
    mono = pg.evaluate(SIZES_JS)
    check(mono[0]['inRent'] and mono[0]['size'] >= 60, f'P: the rent is still the huge element on a phone ({mono[0]})')
    check(pg.locator('.maplibregl-map').count() == 0, 'P: the map is not built until it is near the screen on a phone')
    pg.locator('#listing-map').scroll_into_view_if_needed()
    pg.wait_for_selector('#listing-map .eb-pin', timeout=10000)
    wait_map_drawn(pg, '#listing-map')
    mb = pg.locator('#listing-map').bounding_box()
    check(mb['width'] <= 390 and mb['height'] >= 300, f'P: the map fits a phone ({mb})')
    pg.click('#nav-toggle'); check(pg.is_visible('#site-nav'), 'P: the mobile menu opens on the detail page')
    s.ctx.close()


# ---------------------------------------------------------------- part 3: accessibility sweep (Q)

# Computed-style contrast audit (WCAG 2.x). Installs window.__a11y.{measure, describe} and returns every visible text
# element that falls short: 4.5:1, or 3:1 for large text (>=24px, or >=18.66px and bold). Foreground alpha and element
# opacity are composited over the stacked backgrounds. Text over an image would be unknowable, so it is reported too.
CONTRAST_JS = r"""
() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();
  function background(el) {
    const chain = [];
    for (let e = el; e; e = e.parentElement) chain.push(e);
    let bg = { r: 255, g: 255, b: 255, a: 1 }, image = false;
    for (let i = chain.length - 1; i >= 0; i--) {
      const cs = getComputedStyle(chain[i]);
      if (cs.backgroundImage !== 'none' && !/^url\("data:image\/svg/.test(cs.backgroundImage)) image = true;
      const c = parse(cs.backgroundColor);
      if (c.a > 0) bg = over(c, bg);
    }
    return { bg, image };
  }
  const opacity = el => { let o = 1; for (let e = el; e; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
  function describe(el) {
    const cls = (el.getAttribute('class') || '').split(/\s+/).filter(Boolean).slice(0, 3).join('.');
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (cls ? '.' + cls : '') + ' "' + (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 28) + '"';
  }
  function shown(el) {
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || e.tagName === 'NOSCRIPT') return false;
    }
    const r = el.getBoundingClientRect();
    return r.width >= 2 && r.height >= 2;
  }
  function measure(el, pseudo) {
    const cs = getComputedStyle(el, pseudo || null);
    const fs = parseFloat(cs.fontSize), fw = parseInt(cs.fontWeight, 10) || 400;
    const large = fs >= 24 || (fs >= 18.66 && fw >= 700);
    const { bg, image } = background(el);
    const fg0 = parse(cs.color);
    const fg = over({ r: fg0.r, g: fg0.g, b: fg0.b, a: fg0.a * opacity(el) * (pseudo ? parseFloat(cs.opacity || 1) : 1) }, bg);
    return { ratio: ratio(fg, bg), need: large ? 3 : 4.5, fs, fw, fg: hex(fg), bg: hex(bg), image };
  }
  window.__a11y = { measure, describe };
  const bad = [];
  let n = 0;
  const judge = (el, label, m) => {
    n++;
    if (m.image) bad.push(label + ': text over an image');
    else if (m.ratio < m.need) bad.push(`${label}: ${m.ratio.toFixed(2)} < ${m.need} (${m.fg} on ${m.bg}, ${m.fs}px/${m.fw})`);
  };
  document.querySelectorAll('body *').forEach(el => {
    if (el instanceof SVGElement || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION', 'IMG'].includes(el.tagName) || !shown(el)) return;
    if (el.closest('button:disabled, [aria-disabled="true"]')) return;       // disabled controls are exempt (WCAG 1.4.3/1.4.11), e.g. the map's zoom-out at minZoom
    if (el.matches('input, select, textarea')) {
      if (el.type === 'hidden' || el.disabled) return;                       // inactive controls are exempt
      judge(el, describe(el) + ' (value)', measure(el));
      if (el.placeholder) judge(el, describe(el) + ' (placeholder)', measure(el, '::placeholder'));
      return;
    }
    if ([...el.childNodes].some(x => x.nodeType === 3 && x.textContent.trim())) judge(el, describe(el), measure(el));
  });
  return { n, bad };
}
"""

# The element in focus: is there a ring, and is it >=3:1 against what is behind it? (The ring sits outside the element,
# so the parent's background counts; a .listing-card-link draws its ring on ::after.)
FOCUS_JS = r"""
() => {
  const a = document.activeElement;
  if (!a || a === document.body) return null;
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  let bg = { r: 255, g: 255, b: 255, a: 1 };
  const chain = []; for (let e = a.parentElement; e; e = e.parentElement) chain.push(e);
  for (let i = chain.length - 1; i >= 0; i--) { const c = parse(getComputedStyle(chain[i]).backgroundColor); if (c.a > 0) bg = over(c, bg); }
  const ring = [getComputedStyle(a), getComputedStyle(a, '::after')].find(cs => cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0);
  let cr = null;
  if (ring) { const f = parse(ring.outlineColor), x = lum(f), y = lum(bg); cr = (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  window.__tabbed = window.__tabbed || new WeakSet();
  const again = window.__tabbed.has(a);                                       // the Tab order has come full circle
  window.__tabbed.add(a);
  return { again, name: a.tagName.toLowerCase() + ' ' + JSON.stringify(((a.textContent || '').trim() || a.getAttribute('aria-label') || '').slice(0, 26)),
           ring: !!ring, cr, filled: a.classList.contains('eb-btn'), map: !!a.closest('.maplibregl-map') };
}
"""

A11Y_PAGES = [
    ('home', '/', '#available-grid article'),
    ('listings', '/listings/', '#listing-grid article'),
    ('detail', '/listings/chs-n101/', '#listing-title'),
    ('building', '/buildings/courthouse-square/', '#neighbor-wall article'),
    ('404', '/404.html', '#not-found-title'),
    ('fallback', '/listing.html?id=chs-n101', '#listing-title'),
]
TENANTS = [{'name': 'Lantern Counseling', 'suite': 'N105', 'category': 'therapy', 'blurb': 'Talk therapy for adults.',
            'website': 'https://example.com', 'phone': '(206) 555-0100', 'email': 'hi@example.com'},
           {'name': 'Sayre & Co', 'suite': 'N107', 'category': 'legal', 'blurb': 'Wills and contracts.'}]


def ax_tree(s):
    return s.ctx.new_cdp_session(s.pg).send('Accessibility.getFullAXTree')['nodes']


def a11y_structure(s, tag):
    """Landmarks, headings and accessible names from the browser's own accessibility tree."""
    nodes = [n for n in ax_tree(s) if not n.get('ignored')]
    role = lambda n: (n.get('role') or {}).get('value')
    name = lambda n: ((n.get('name') or {}).get('value') or '').strip()
    for lm in ('banner', 'main', 'contentinfo'):
        check(sum(1 for n in nodes if role(n) == lm) == 1, f'{tag}: exactly one {lm} landmark')
    navs = [name(n) for n in nodes if role(n) == 'navigation']
    check(all(navs) and len(navs) == len(set(navs)), f'{tag}: every navigation landmark has its own name ({navs})')
    unnamed = [role(n) for n in nodes if role(n) in ('link', 'button', 'textbox', 'combobox', 'checkbox', 'img') and not name(n)]
    check(not unnamed, f'{tag}: controls/images with no accessible name: {unnamed}')
    levels = [int(p['value']['value']) for n in nodes if role(n) == 'heading' for p in n.get('properties', []) if p['name'] == 'level']
    check(levels[:1] == [1] and levels.count(1) == 1, f'{tag}: exactly one h1, and it comes first ({levels[:6]})')
    check(all(b - a <= 1 for a, b in zip(levels, levels[1:])), f'{tag}: heading levels never skip ({levels})')


def a11y_page(s, name, path, ready, wide):
    """Everything Q checks on one page at one width."""
    tag = f'Q {name}@{1440 if wide else 390}'
    pg = s.pg
    pg.goto(BASE + path, wait_until='networkidle')
    pg.wait_for_selector(ready, timeout=10000)
    pg.wait_for_timeout(250)
    doc = pg.evaluate("""() => ({
      lang: document.documentElement.lang,
      theme: (document.querySelector('meta[name=theme-color]') || {}).content,
      icon: (document.querySelector('link[rel=icon]') || {}).getAttribute('href'),
      h1: document.querySelectorAll('h1').length,
      noAlt: [...document.querySelectorAll('img:not([alt])')].length,
      unlabeled: [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(e => !e.closest('.hidden') && !(e.labels && e.labels.length) && !e.getAttribute('aria-label')).length,
      dupIds: [...document.querySelectorAll('[id]')].map(e => e.id).filter((id, i, all) => all.indexOf(id) !== i),
      hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 })""")
    check(doc['lang'] == 'en', f'{tag}: <html lang="en">')
    check(doc['theme'] == '#670A2F', f'{tag}: theme-color is Berry ({doc["theme"]})')
    check(doc['icon'] == '/images/brand/monogram-tangerine-badge.svg', f'{tag}: favicon ({doc["icon"]})')
    check(doc['h1'] == 1, f'{tag}: one h1 in the rendered page ({doc["h1"]})')
    check(doc['noAlt'] == 0, f'{tag}: {doc["noAlt"]} <img> without alt')
    check(doc['unlabeled'] == 0, f'{tag}: {doc["unlabeled"]} form control(s) without a label')
    check(not doc['dupIds'], f'{tag}: duplicate ids {doc["dupIds"]}')
    check(not doc['hscroll'], f'{tag}: sideways scroll')
    a11y_structure(s, tag)

    # contrast at rest
    r = pg.evaluate(CONTRAST_JS)
    check(r['n'] >= 10, f'{tag}: the contrast audit looked at {r["n"]} text elements')
    check(not r['bad'], f'{tag}: contrast: {r["bad"][:4]}')

    # the skip link: first Tab stop, appears, passes AA while focused, lands in <main>
    pg.evaluate("window.scrollTo(0, 0); document.activeElement && document.activeElement.blur()")
    pg.keyboard.press('Tab')
    sk = pg.evaluate("""() => { const a = document.activeElement, r = a.getBoundingClientRect();
        return { href: a.getAttribute('href'), text: a.textContent.trim(), w: r.width, h: r.height, x: r.x, y: r.y,
                 m: window.__a11y.measure(a) } }""")
    check(sk['href'] == '#main' and sk['text'] == 'Skip to content', f'{tag}: the first Tab stop is the skip link ({sk["href"]!r} {sk["text"]!r})')
    check(sk['w'] > 60 and sk['h'] > 20 and sk['x'] >= 0 and sk['y'] >= 0, f'{tag}: the skip link shows itself on focus ({sk["w"]}x{sk["h"]})')
    check(sk['m']['ratio'] >= sk['m']['need'], f'{tag}: the skip link passes AA on focus ({sk["m"]})')
    pg.keyboard.press('Enter')
    check(pg.evaluate('location.hash') == '#main', f'{tag}: the skip link jumps to #main')
    pg.keyboard.press('Tab')
    check(pg.evaluate("!!(document.activeElement && document.activeElement.closest('main'))"), f'{tag}: after the skip link, Tab lands inside <main>')

    # every Tab stop has a ring of at least 3:1 (a filled .eb-btn swaps its fill instead). The skip link moved the
    # keyboard's starting point into <main>, so start over from a fresh page.
    pg.goto(BASE + path, wait_until='networkidle')
    pg.wait_for_selector(ready, timeout=10000)
    pg.wait_for_timeout(250)
    pg.evaluate(CONTRAST_JS)        # (re)installs window.__a11y for the hover pass below
    stops, bad_ring = 0, []
    for _ in range(120):
        pg.keyboard.press('Tab')
        f = pg.evaluate(FOCUS_JS)
        if f is None or f['again']:
            break
        stops += 1
        if f['map']:                        # the map, its pins, zoom buttons and credits: a ring is enough (tiles vary behind them)
            if not f['ring']:
                bad_ring.append(f'{f["name"]}: no focus ring')
            continue
        if not f['ring'] and not f['filled']:
            bad_ring.append(f'{f["name"]}: no focus ring')
        elif f['ring'] and f['cr'] < 3:
            bad_ring.append(f'{f["name"]}: ring {f["cr"]:.2f}:1')
    check(stops >= 8, f'{tag}: tabbed through {stops} stops')
    check(not bad_ring, f'{tag}: focus rings: {bad_ring[:4]}')

    # hover (pointer devices only): one of each look of link or button must stay AA while hovered
    if wide:
        done, bad_hover = set(), []
        for h in pg.query_selector_all('a[href], button'):
            box = h.bounding_box()
            if not h.is_visible() or not box or box['width'] < 8 or box['height'] < 8:
                continue                    # not on screen: display:none, or the skip link before it is focused
            sig = pg.evaluate("""e => { const f = e.parentElement && e.parentElement.closest('[class*=bg-eb], [class*=eb-field], .eb-card');
                                        return e.tagName + '|' + e.className + '|' + (f ? f.className : '') }""", h)
            if sig in done:
                continue
            done.add(sig)
            h.scroll_into_view_if_needed(timeout=3000)
            h.hover(timeout=3000)
            for m in pg.evaluate("""e => [e, ...e.querySelectorAll('*')].filter(n => [...n.childNodes].some(x => x.nodeType === 3 && x.textContent.trim()))
                                         .map(n => ({ el: window.__a11y.describe(n), ...window.__a11y.measure(n) }))""", h):
                if m['ratio'] < m['need']:
                    bad_hover.append(f'{m["el"]} {m["ratio"]:.2f}<{m["need"]}')
            pg.mouse.move(0, 0)
        check(len(done) >= 5, f'{tag}: hovered {len(done)} kinds of link/button')
        check(not bad_hover, f'{tag}: hover contrast: {bad_hover[:4]}')


def part3(browser, sessions):
    # ---------- Q: every page type, desktop and phone ----------
    for wide, vp in ((True, {'width': 1440, 'height': 900}), (False, {'width': 390, 'height': 844})):
        s = Session(browser, f'Q{vp["width"]}', viewport=vp); sessions.append(s)
        # the gallery photos are not in the repo yet (the page shows its flat placeholders): answer them so no 404 is logged
        s.ctx.route(re.compile(r'/images/buildings/'), lambda r: r.fulfill(status=200, content_type='image/png', body=TILE_PNG))
        for name, path, ready in A11Y_PAGES:
            a11y_page(s, name, path, ready, wide)
        s.ctx.close()

    # ---------- Q: states that only exist after a click or a failure ----------
    for vp in ({'width': 1440, 'height': 900}, {'width': 390, 'height': 844}):
        w = vp['width']
        s = Session(browser, f'Qstates{w}', viewport=vp); sessions.append(s)
        pg = s.open('/listings/')
        pg.evaluate(CONTRAST_JS)
        if w < 1024:
            pg.click('#mobile-toggle')
        pg.wait_for_selector('.eb-pin', timeout=10000)
        wait_map_drawn(pg, '#map')
        pg.locator('.eb-pin').first.click()
        pg.wait_for_selector('.maplibregl-popup', timeout=5000)
        r = pg.evaluate(CONTRAST_JS)
        check(r['n'] > 20 and not r['bad'], f'Q {w}: open map popup + attribution + zoom buttons: {r["bad"][:3]} ({r["n"]} looked at)')
        s.open('/listings/?type=residential')
        r = pg.evaluate(CONTRAST_JS)
        check(not r['bad'], f'Q {w}: the residential empty state: {r["bad"][:3]}')
        s.open('/listings/?type=commercial&price=750&sqft=1000')      # nothing is both under $750 and over 1,000 sq ft
        check(cards(pg).count() == 0, f'Q {w}: price<=750 with 1,000+ sq ft matches nothing')
        r = pg.evaluate(CONTRAST_JS)
        check(not r['bad'], f'Q {w}: the over-filtered empty state (a disabled beds select is exempt): {r["bad"][:3]}')
        s.ctx.close()

        s = Session(browser, f'Qwall{w}', viewport=vp); sessions.append(s)
        s.ctx.route('**/data/tenants.json', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(TENANTS)))
        pg = s.pg
        pg.goto(BASE + '/buildings/courthouse-square/', wait_until='networkidle')
        pg.wait_for_selector('#neighbor-wall article[data-mode=occupied]')
        pg.wait_for_timeout(700)
        r = pg.evaluate(CONTRAST_JS)
        check(r['n'] > 60 and not r['bad'], f'Q {w}: the building page with a tenant roster (cards, tally, filter pills): {r["bad"][:3]}')
        s.ctx.close()

        s = Session(browser, f'Qdown{w}', feed_status=500, viewport=vp); sessions.append(s)
        s.bad_local = None      # the 500 is the point
        pg = s.pg
        pg.goto(BASE + '/listings/', wait_until='networkidle'); pg.wait_for_timeout(500)
        r = pg.evaluate(CONTRAST_JS)
        check(not r['bad'], f'Q {w}: /listings/ when the feed will not load: {r["bad"][:3]}')
        pg.goto(BASE + '/listing.html?id=chs-n101', wait_until='networkidle'); pg.wait_for_selector('#listing-title')
        r = pg.evaluate(CONTRAST_JS)
        check(not r['bad'], f'Q {w}: the fallback page when the feed will not load: {r["bad"][:3]}')
        s.errors = []           # failed-feed console noise is expected here
        s.ctx.close()

    # ---------- Q: prefers-reduced-motion ----------
    s = Session(browser, 'Qmotion', viewport={'width': 1440, 'height': 900}, reduced_motion='reduce'); sessions.append(s)
    s.ctx.route('**/data/tenants.json', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(TENANTS)))
    pg = s.pg
    for name, path, ready in A11Y_PAGES:
        pg.goto(BASE + path, wait_until='networkidle'); pg.wait_for_selector(ready, timeout=10000)
        m = pg.evaluate("""() => ({ scroll: getComputedStyle(document.documentElement).scrollBehavior,
            moving: [...document.querySelectorAll('body *')].filter(e => !e.closest('.maplibregl-map') &&
              ((getComputedStyle(e).animationName !== 'none' && parseFloat(getComputedStyle(e).animationDuration) > 0) ||
               (getComputedStyle(e).transitionProperty !== 'none' && parseFloat(getComputedStyle(e).transitionDuration) > 0))).length })""")
        check(m['scroll'] == 'auto', f'Q motion {name}: scroll-behavior is {m["scroll"]!r} under reduced motion')
        check(m['moving'] == 0, f'Q motion {name}: {m["moving"]} element(s) animate or transition under reduced motion')
        if name == 'listings':
            pg.wait_for_selector('.eb-pin')
            check(pg.evaluate("(%s)('#map').ebCalm === true" % MAP_JS), 'Q motion: the map has no tile fade or animated pan/zoom under reduced motion')
        if name == 'building':
            # the tally shows its final numbers the moment the wall is drawn (the open suites + 2 tenants)
            want = str(len(LISTINGS) + len(TENANTS))
            got = pg.evaluate("document.getElementById('tally-suites').textContent")
            check(got == want, f'Q motion: the suites tally is {got!r}, expected {want!r} at once')
    s.ctx.close()
    s = Session(browser, 'Qmotion-off', viewport={'width': 1440, 'height': 900}, reduced_motion='no-preference'); sessions.append(s)
    pg = s.open('/listings/')
    pg.wait_for_selector('.eb-pin')
    check(pg.evaluate("(%s)('#map').ebCalm === false" % MAP_JS),
          'Q motion: with no preference the map keeps its animations (so the reduced-motion check above can fail)')
    s.ctx.close()


# ---------------------------------------------------------------- the test

def main():
    from playwright.sync_api import sync_playwright

    os.chdir(ROOT)
    ThreadingServer.allow_reuse_address = True
    httpd = ThreadingServer(('127.0.0.1', PORT), Quiet)
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
        # the basemap is ours: map/vashon.pmtiles, read with Range requests and drawn by MapLibre; attribution is on screen
        wait_map_drawn(pg, '#map')
        check(any(st == 206 and r for st, r in Quiet.range_log), f'A: the archive is read with Range requests (206): {Quiet.range_log[:4]}')
        check(all(st in (200, 206) for st, _ in Quiet.range_log), f'A: every archive request succeeded: {Quiet.range_log[:6]}')
        outside = [u for u in s.requests if not u.startswith((BASE, 'data:', 'blob:')) and not u.startswith(('https://fonts.googleapis.com/', 'https://fonts.gstatic.com/'))]
        check(not outside, f'A: nothing but the site (and fonts) was asked for: {outside[:3]}')
        attr = re.sub(r'\s+', ' ', pg.text_content('.maplibregl-ctrl-attrib'))
        check('© OpenStreetMap' in attr and 'Protomaps' in attr, f'A: attribution reads {attr!r}')
        check(pg.is_visible('.maplibregl-ctrl-attrib'), 'A: attribution is visible')
        check(pg.get_attribute('.maplibregl-ctrl-attrib a[href*="openstreetmap.org"]', 'href') == 'https://www.openstreetmap.org/copyright',
              'A: attribution links OpenStreetMap to its copyright page (the ODbL asks for it)')
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
        pg.wait_for_selector('.eb-pin')
        wait_map_drawn(pg, '#map')
        check(pg.locator('.eb-pin').count() == len(g), f'E: {pg.locator(".eb-pin").count()} pins, expected {len(g)}')
        check(pg.locator('.eb-pin__count').first.text_content().strip() == str(n_all), 'E: the pin carries the group count')
        pin_label = pg.get_attribute('.eb-pin', 'aria-label') or ''
        check(str(n_all) in pin_label and pg.get_attribute('.eb-pin', 'tabindex') == '0' and pg.get_attribute('.eb-pin', 'role') == 'button',
              f'E: pin is keyboard reachable and named ({pin_label!r})')
        # the basemap really draws, in brand colors: island (Cream) against water (A7C8D8), nothing pure white or black
        pg.evaluate("(%s)('#map').jumpTo({center: [-122.46, 47.42], zoom: 11})" % MAP_JS)
        wait_map_drawn(pg, '#map')
        colors = {tuple(int(v) for v in k.split(',')): n for k, n in pg.evaluate(PIXELS_JS, '#map').items()}
        total = sum(colors.values())
        water = sum(n for c, n in colors.items() if close_to(c, (0xA7, 0xC8, 0xD8)))
        cream = sum(n for c, n in colors.items() if close_to(c, (0xF1, 0xEC, 0xE9)))
        check(water / total > 0.08 and cream / total > 0.08, f'E: the canvas shows water {water}/{total} and land {cream}/{total} in the brand colors: {sorted(colors.items(), key=lambda kv: -kv[1])[:4]}')
        check(not any(c[:3] in ((255, 255, 255), (0, 0, 0)) or c[3] == 0 for c in colors), f'E: no pure white, pure black or empty pixels on the canvas: {[c for c in colors if c[:3] in ((255,255,255),(0,0,0)) or c[3]==0][:3]}')
        feats = pg.evaluate("(%s)('#map').queryRenderedFeatures({layers: ['earth', 'water', 'roads_major', 'landuse_park']}).map(f => f.layer.id)" % MAP_JS)
        check({'earth', 'water'} <= set(feats), f'E: the earth and water of the archive are drawn ({sorted(set(feats))})')
        # labels: six curated names, quiet, not interactive, hidden by zoom where they would crowd a pin
        labels = pg.eval_on_selector_all('#map .eb-map-label', """els => els.map(e => ({ t: e.textContent, off: e.classList.contains('eb-map-label--off'),
            hidden: e.getAttribute('aria-hidden'), pe: getComputedStyle(e).pointerEvents, ff: getComputedStyle(e).fontFamily }))""")
        check([l['t'] for l in labels] == ['Vashon', 'Burton', 'Dockton', 'Maury Island', 'Vashon Heights ferry', 'Tahlequah ferry'], f'E: place names {[l["t"] for l in labels]}')
        check(all(l['hidden'] == 'true' and l['pe'] == 'none' for l in labels), 'E: place names are decorative (aria-hidden) and not interactive (pointer-events: none)')
        check(not any(l['off'] for l in labels), f'E: at island zoom every name shows ({[l["t"] for l in labels if l["off"]]})')
        check(pg.locator('#map .eb-map-label:not(.eb-map-label--off)').count() == 6 and pg.locator('#map .eb-pin').count() == 1, 'E: names are not pins')
        pg.evaluate("(%s)('#map').jumpTo({center: [-122.46, 47.4471], zoom: 15})" % MAP_JS)
        off = pg.eval_on_selector_all('#map .eb-map-label--off', 'els => els.map(e => e.textContent)')
        check(sorted(off) == ['Maury Island', 'Vashon'], f'E: close in, the town and island names step aside from the pin ({off})')
        # a flat, north-up map locked to the island
        lock = pg.evaluate("""() => { const m = (%s)('#map'), inside = c => [c.lng, c.lat];
            m.jumpTo({center: [-120.0, 40.0], zoom: 11}); const far = inside(m.getCenter());
            m.jumpTo({center: [-124.5, 49.0]}); const far2 = inside(m.getCenter());
            m.fitBounds([[-125, 40], [-120, 50]], {animate: false}); const fit = inside(m.getCenter());
            m.jumpTo({zoom: 3}); const lo = m.getZoom(); m.jumpTo({zoom: 20}); const hi = m.getZoom();
            return { far, far2, fit, lo, hi, bounds: m.getMaxBounds().toArray(), minz: m.getMinZoom(), maxz: m.getMaxZoom(),
                     rotate: m.dragRotate.isEnabled(), pitch: m.getPitch() }; }""" % MAP_JS)
        in_island = lambda c: -122.62 <= c[0] <= -122.30 and 47.28 <= c[1] <= 47.57
        check(in_island(lock['far']) and in_island(lock['far2']) and in_island(lock['fit']), f'E: jumpTo / fitBounds far away leave the center on the island ({lock["far"]}, {lock["far2"]}, {lock["fit"]})')
        check(lock['bounds'] == [[-122.62, 47.28], [-122.3, 47.57]], f'E: the pan limit is the island box ({lock["bounds"]})')
        check((lock['lo'], lock['hi'], lock['minz'], lock['maxz']) == (11, 15.5, 11, 15.5), f'E: zoom is held to 11..15.5 ({lock["lo"]}..{lock["hi"]})')
        check(lock['rotate'] is False and lock['pitch'] == 0, 'E: rotation is off and the map is flat')
        pg.evaluate("(%s)('#map').jumpTo({center: [-122.46, 47.4471], zoom: 15})" % MAP_JS)
        box = pg.locator('#map').bounding_box()
        sx, sy = box['x'] + box['width'] * 0.3, box['y'] + box['height'] * 0.3
        pg.mouse.move(sx, sy); pg.mouse.down(button='right'); pg.mouse.move(sx + 140, sy + 60, steps=8); pg.mouse.up(button='right')
        pg.keyboard.down('Control'); pg.mouse.move(sx, sy); pg.mouse.down(); pg.mouse.move(sx + 100, sy + 80, steps=8); pg.mouse.up(); pg.keyboard.up('Control')
        pg.evaluate("(%s)('#map').getCanvas().focus()" % MAP_JS)
        pg.keyboard.down('Shift'); pg.keyboard.press('ArrowRight'); pg.keyboard.press('ArrowUp'); pg.keyboard.up('Shift')
        pg.wait_for_timeout(300)
        bp = pg.evaluate("(%s)('#map')" % MAP_JS + ".getBearing() + ',' + (%s)('#map').getPitch()" % MAP_JS)
        check(bp == '0,0', f'E: right-drag, ctrl-drag and shift-arrows cannot rotate or tilt the map (bearing,pitch = {bp})')
        # the wheel zooms only once the map has been clicked or focused (the page scrolls otherwise)
        check(pg.evaluate("(%s)('#map').scrollZoom.isEnabled()" % MAP_JS) is True, 'E: the wheel zooms once the map is focused')
        pg.mouse.move(5, 5)
        pg.wait_for_timeout(100)
        pg.evaluate("(%s)('#map').getCanvas().blur()" % MAP_JS)
        check(pg.evaluate("(%s)('#map').scrollZoom.isEnabled()" % MAP_JS) is False, 'E: and stops again when focus leaves')
        pg.evaluate("(%s)('#map').jumpTo({center: [-122.46, 47.4471], zoom: 15})" % MAP_JS)
        pg.wait_for_timeout(300)
        pg.locator('.eb-pin').first.click()
        pg.wait_for_selector('.maplibregl-popup .eb-pop-item')
        items = popup_items(pg)
        ids = list(g.values())[0]
        check(len(items) == len(ids) == n_all, f'E: popup lists {len(items)} entries, expected {len(ids)}')
        check([i['href'] for i in items] == [f'/listings/{x}/' for x in ids], f'E: popup links {[i["href"] for i in items]}')
        check([i['rent'] for i in items] == [money(next(L for L in LISTINGS if L['id'] == x)['rent']) + '/mo' for x in ids],
              f'E: popup rents {[i["rent"] for i in items]}')
        check(pg.get_attribute('.maplibregl-popup', 'class').find('eb-popup') >= 0, 'E: popup carries the brand class')
        check(pg.evaluate("document.activeElement.closest('.maplibregl-popup') === null"), 'E: a mouse click does not pull focus into the popup (no stray ring)')
        audit(pg, '.maplibregl-popup', 'E popup')
        fits = pg.evaluate("""() => { const c = document.getElementById('map').getBoundingClientRect(), p = document.querySelector('.maplibregl-popup').getBoundingClientRect();
                                      return p.left >= c.left && p.right <= c.right && p.top >= c.top && p.bottom <= c.bottom; }""")
        check(fits, 'E: the popup sits fully inside the map frame')
        # Escape closes the popup; Enter on a focused pin opens it and moves the keyboard into it; Escape returns to the pin
        pg.keyboard.press('Escape')
        check(pg.locator('.maplibregl-popup').count() == 0, 'E: Escape closes the popup')
        pg.locator('.eb-pin').first.focus()
        pg.keyboard.press('Enter')
        pg.wait_for_selector('.maplibregl-popup .eb-pop-item')
        check(pg.evaluate("document.activeElement.classList.contains('eb-pop-link')"), 'E: opened from the keyboard, focus moves to the first link in the popup')
        pg.keyboard.press('Escape')
        check(pg.locator('.maplibregl-popup').count() == 0 and pg.evaluate("document.activeElement.classList.contains('eb-pin')"),
              'E: Escape from inside the popup closes it and returns focus to the pin')
        pg.locator('.eb-pin').first.focus()
        pg.keyboard.press('Enter')
        pg.wait_for_selector('.maplibregl-popup .eb-pop-item')
        pg.locator('.maplibregl-popup-close-button').focus()
        pg.keyboard.press('Enter')
        check(pg.locator('.maplibregl-popup').count() == 0 and pg.evaluate("document.activeElement.classList.contains('eb-pin')"),
              'E: the close button works from the keyboard and returns focus to the pin')
        pg.locator('.eb-pin').first.click()
        pg.wait_for_selector('.maplibregl-popup .eb-pop-item')
        # pins follow the filter: $750 leaves a smaller group
        pg.select_option('#f-price', '750')
        try:
            pg.wait_for_selector('.maplibregl-popup', state='detached', timeout=3000)
            closed = True
        except Exception:
            closed = False
        check(closed, 'E: popup closes when its pin is re-rendered')
        pg.locator('.eb-pin').first.click()
        pg.wait_for_selector('.maplibregl-popup .eb-pop-item')
        got = [i['href'] for i in popup_items(pg)]
        check(sorted(got) == sorted(f'/listings/{x}/' for x in expected(LISTINGS, price=750)), f'E: filtered popup lists {got}')
        pg.select_option('#f-sqft', '1000')   # nothing this big in the feed
        if not expected(LISTINGS, price=750, sqft=1000):
            check(pg.locator('.eb-pin').count() == 0, 'E: no results means no pins')

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
        check(geo['headerOnTop'], 'J: the header stays above the map')
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

        # ---------- K: the map will not load: still a perfectly good list ----------
        s = Session(browser, 'K', viewport={'width': 1440, 'height': 900}); sessions.append(s)
        s.ctx.route('**/js/vendor/maplibre-gl.js', lambda r: r.abort())
        pg = s.pg
        pg.goto(BASE + '/listings/', wait_until='networkidle')
        s.settle()
        check(cards(pg).count() == n_all, 'K: cards render without MapLibre')
        check(not pg.is_visible('#map-pane') and pg.get_attribute('#split', 'data-nomap') == '1', 'K: the map pane steps aside')
        pg.select_option('#f-price', '750')
        check(cards(pg).count() == len(expected(LISTINGS, price=750)), 'K: filters still work without MapLibre')
        s.errors = [e for e in s.errors if 'Failed to load resource' not in e]   # the aborted request itself is the point
        s.ctx.close()

        # no WebGL (an old phone, a locked-down browser): the same list-only page, and no errors
        s = Session(browser, 'K-nogl', viewport={'width': 1440, 'height': 900}); sessions.append(s)
        s.ctx.add_init_script("""const real = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function (type, ...rest) { return /webgl/.test(type) ? null : real.call(this, type, ...rest); };""")
        pg = s.pg
        pg.goto(BASE + '/listings/', wait_until='networkidle')
        s.settle()
        check(cards(pg).count() == n_all and pg.get_attribute('#split', 'data-nomap') == '1' and not pg.is_visible('#map-pane'),
              'K: without WebGL the page is the list and the map pane steps aside')
        s.ctx.close()

        # only the basemap is missing (no archive, no PMTiles library, no style): the Cream map, its pins, names and popup still work
        basemap_down = (('archive', '**/map/vashon.pmtiles', lambda r: r.abort()),
                        ('pmtiles-js', '**/js/vendor/pmtiles.js', lambda r: r.abort()),
                        ('archive-404', '**/map/vashon.pmtiles', lambda r: r.fulfill(status=404, body='nope')),
                        ('style-404', '**/map/style.json', lambda r: r.fulfill(status=404, body='nope')))
        for tag, pattern, handler in basemap_down:
            s = Session(browser, f'K-{tag}', viewport={'width': 1440, 'height': 900}); sessions.append(s)
            s.bad_local = None          # the missing file is the point
            s.ctx.route(pattern, handler)
            pg = s.open('/listings/')
            pg.wait_for_selector('.eb-pin', timeout=10000)
            pg.wait_for_timeout(800)
            check(pg.locator('.eb-pin').count() == 1 and pg.locator('#map .eb-map-label').count() == 6, f'K {tag}: the pin and the six names are there without a basemap')
            bg = pg.evaluate("getComputedStyle(document.getElementById('map')).backgroundColor")
            check(bg == CREAM, f'K {tag}: the map is Cream when the basemap is missing ({bg})')
            check(pg.evaluate("(%s)('#map').queryRenderedFeatures().length === 0" % MAP_JS), f'K {tag}: and nothing is drawn from a missing archive')
            pg.locator('.eb-pin').first.click()
            pg.wait_for_selector('.maplibregl-popup .eb-pop-item')
            check(len(popup_items(pg)) == n_all, f'K {tag}: the popup still lists every suite')
            pg.select_option('#f-price', '750')
            check(pg.locator('.eb-pin').count() == 1, f'K {tag}: filters still move the pins')
            s.errors = [e for e in s.errors if 'Failed to load resource' not in e]   # the browser logs the failed request itself
            s.ctx.close()

        # ---------- I: synthetic feed (homes, a future date, a null coordinate) ----------
        feed = synthetic_feed(); all_l = feed['listings']
        s = Session(browser, 'I', feed=feed, viewport={'width': 1440, 'height': 900}); sessions.append(s)
        pg = s.open()
        check(cards(pg).count() == len(all_l), f'I: {cards(pg).count()} cards, expected {len(all_l)}')
        g = groups(all_l)
        check(g and len(g) == 3, f'I: synthetic coordinates make 3 groups, got {len(g)}')
        pg.wait_for_selector('.eb-pin')
        check(pg.locator('.eb-pin').count() == 3, f'I: {pg.locator(".eb-pin").count()} pins; the null-coordinate home must not get one')
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
        check(pg.locator('.eb-pin').count() == 2, 'I: pins follow the beds filter')
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
        check(pg.locator('.maplibregl-map').count() == 0, 'H: the map is not built until it is on screen')
        check(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'H: no sideways page scroll in List view')
        bar = pg.evaluate("document.getElementById('filter-bar').getBoundingClientRect().height")
        check(bar < 90, f'H: the sticky filter bar stays short on a phone ({bar}px)')
        pg.click('#mobile-toggle')
        pg.wait_for_selector('.maplibregl-map')
        pg.wait_for_selector('.eb-pin')
        wait_map_drawn(pg, '#map')
        mb = pg.locator('#map').bounding_box()
        check(pg.is_visible('#map') and mb['height'] > 400 and mb['width'] > 300, f'H: Map view shows a full-height map ({mb})')
        check(not pg.is_visible('#listing-grid'), 'H: the list is hidden in Map view')
        check(pg.inner_text('#mobile-toggle').strip() == 'List', 'H: the pill now reads "List"')
        check(pg.locator('.eb-pin').count() == 1, 'H: the pin is on the mobile map')
        pill = pg.locator('#mobile-toggle').bounding_box()
        attrib = pg.locator('.maplibregl-ctrl-attrib').bounding_box()
        overlap = not (pill['x'] + pill['width'] <= attrib['x'] or attrib['x'] + attrib['width'] <= pill['x']
                       or pill['y'] + pill['height'] <= attrib['y'] or attrib['y'] + attrib['height'] <= pill['y'])
        check(not overlap, f'H: the pill does not cover the map attribution ({pill} vs {attrib})')
        check(pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'H: no sideways page scroll in Map view')
        pg.locator('.eb-pin').first.click()
        pg.wait_for_selector('.maplibregl-popup .eb-pop-item')
        pb = pg.locator('.maplibregl-popup-content').bounding_box()
        check(pb['x'] >= 0 and pb['x'] + pb['width'] <= 390, f'H: the popup fits a phone screen ({pb})')
        audit(pg, '#mobile-toggle-wrap', 'H pill')
        pg.click('#mobile-toggle')
        check(pg.is_visible('#listing-grid') and not pg.is_visible('#map'), 'H: List returns to the cards')
        check(pg.inner_text('#mobile-toggle').strip() == 'Map', 'H: the pill reads "Map" again')
        # filters carry over to the mobile map
        pg.select_option('#f-price', '750')
        pg.click('#mobile-toggle')
        pg.locator('.eb-pin').first.click()
        pg.wait_for_function("document.querySelectorAll('.maplibregl-popup').length === 1")
        check(len(popup_items(pg)) == len(expected(LISTINGS, price=750)), 'H: the mobile map shows the filtered set')
        s.ctx.close()

        part2(browser, sessions)
        part3(browser, sessions)

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
          f'G flat brand, H mobile, I synthetic feed, J details, K no map; '
          f'L static page, M inquiry form, N fallback, O structured data, P flat brand + mobile; '
          f'Q accessibility sweep)')


if __name__ == '__main__':
    main()
