#!/usr/bin/env python3
"""Static page generator for the E. Berry site.

The owner runs this locally and commits the output; Netlify never builds.
Stdlib only, so it runs anywhere Python 3 does.

Reads   data/buildings.json, data/listings.json, and the canonical page shell in index.html
        (the EB:HEADER / EB:FOOTER / EB:SHELL-STYLES blocks), plus tools/templates/*.
Writes  buildings/<id>/index.html   one landing page per building   (tools/templates/building.tmpl.html)
        listings/<id>/index.html    one detail page per listing     (tools/templates/listing.tmpl.html)
        listing.html                the noindex client-side fallback for feed listings with no page yet
                                    (tools/templates/listing-fallback.tmpl.html; js/listing-detail.js draws it)
        404.html                    the not-found page Netlify serves for any unknown URL (tools/templates/404.tmpl.html)
        owners/index.html           the owners page, /owners/ (tools/templates/owners.tmpl.html)
        technology/index.html       the "Our technology" page about Ledger, /technology/ (tools/templates/technology.tmpl.html)
        fair-housing/index.html     the fair housing statement, /fair-housing/ (tools/templates/fair-housing.tmpl.html + legal.parts.tmpl.html)
        privacy/index.html          the privacy notice, /privacy/ (tools/templates/privacy.tmpl.html); its form field lists are read from the forms' markup
        accessibility/index.html    the accessibility statement, /accessibility/ (tools/templates/accessibility.tmpl.html)
        sitemap.xml                 home, /listings/, /owners/, /technology/, the three legal pages, every listing and every building page (not the 404)

Run:    python3 tools/build_pages.py           regenerate the committed pages
        python3 tools/build_pages.py --check   regenerate into a temp dir and byte-compare against the
                                               committed files (exit 1 and list what is stale); also run in CI

Re-run it whenever data/buildings.json, data/listings.json, a template, or the shell in index.html changes.
Tailwind sees classes in tools/templates/*.html, so keep markup that carries classes in the templates and
not in this file.
"""

import argparse
import difflib
import html
import json
import math
import os
import re
import shutil
import sys
import tempfile
from string import Template
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'tools', 'templates')

SITE = 'https://eberryvashon.com'
FALLBACK_OG_IMAGE = '/images/og-card-eberry.png'        # 1200x630
FIELD_COLORS = ('berry', 'tangerine', 'sky', 'mustard', 'sage', 'sand')   # .eb-field-<color> in tailwind.src.css
# /lease/ has no #downloads anchor and lease/ is frozen, so the "Download the PDFs" link lands on the first
# download button, which carries this id (tools/check_site.py verifies it still exists).
LEASE_DOWNLOADS_ANCHOR = 'lease-pdf-link'

ADDRESS_RE = re.compile(r'^(?P<street>[^,]+),\s*(?P<city>[^,]+),\s*(?P<region>[A-Z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?$')

# ---------------------------------------------------------------- helpers

def esc(s):
    """Escape any JSON-sourced text for HTML (text and attribute context)."""
    return html.escape(str(s), quote=True)


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def load_json(rel):
    return json.loads(read_text(os.path.join(ROOT, rel)))


def indent_block(text, n):
    """Indent every line after the first by n spaces (the first line sits after the placeholder's own indent)."""
    pad = ' ' * n
    return ('\n' + pad).join(text.split('\n'))


def fail(msg):
    sys.exit(f'build_pages: {msg}')


def load_template(name):
    return Template(read_text(os.path.join(TEMPLATES, name)))


def load_parts(name):
    """Split a partials file on '<!-- @part NAME -->' lines into {NAME: Template}."""
    text = read_text(os.path.join(TEMPLATES, name))
    pieces = re.split(r'^<!-- @part (\w+) -->\n', text, flags=re.M)
    # pieces = [preamble, name1, body1, name2, body2, ...]
    return {pieces[i]: Template(pieces[i + 1].rstrip('\n')) for i in range(1, len(pieces), 2)}


def extract_shell(index_html):
    """Pull the canonical shell (header, footer, shell styles) out of index.html, verbatim."""
    def grab(start, end, label):
        m = re.search(start + r'.*?' + end, index_html, re.S)
        if not m:
            fail(f'index.html has no {label} block (were the EB: markers changed?)')
        return m.group(0)
    return {
        'shell_styles': grab(r'<!-- EB:SHELL-STYLES[^>]*-->', r'</style>', 'EB:SHELL-STYLES'),
        'header': grab(r'<!-- EB:HEADER[^>]*-->', r'<!-- /EB:HEADER -->', 'EB:HEADER'),
        'footer': grab(r'<!-- EB:FOOTER[^>]*-->', r'<!-- /EB:FOOTER -->', 'EB:FOOTER'),
    }


def load_context():
    buildings_doc = load_json('data/buildings.json')
    listings_doc = load_json('data/listings.json')
    index_html = read_text(os.path.join(ROOT, 'index.html'))
    return {
        'buildings': buildings_doc['buildings'],
        'buildings_by_id': {b['id']: b for b in buildings_doc['buildings']},
        'listings': listings_doc['listings'],
        'updated': listings_doc['updated'],
        'shell': extract_shell(index_html),
        'building_template': load_template('building.tmpl.html'),
        'building_parts': load_parts('building.parts.tmpl.html'),
        'listing_template': load_template('listing.tmpl.html'),
        'listing_parts': load_parts('listing.parts.tmpl.html'),
        'listing_fallback_template': load_template('listing-fallback.tmpl.html'),
        'not_found_template': load_template('404.tmpl.html'),
        'owners_template': load_template('owners.tmpl.html'),
        'technology_template': load_template('technology.tmpl.html'),
        'legal_parts': load_parts('legal.parts.tmpl.html'),
        'fair_housing_template': load_template('fair-housing.tmpl.html'),
        'privacy_template': load_template('privacy.tmpl.html'),
        'accessibility_template': load_template('accessibility.tmpl.html'),
        'forms': {f['name']: form_labels(index_html if f['source'] == 'index.html' else read_text(os.path.join(ROOT, f['source'])),
                                         f['name'], f['source']) for f in PRIVACY_FORMS},
    }


# ---------------------------------------------------------------- building pages

def first_existing_image(paths):
    """First of these site paths whose file exists right now, else the shared social card. Absolute URL."""
    for path in paths:
        if os.path.exists(os.path.join(ROOT, path.lstrip('/'))):
            return SITE + path, False
    return SITE + FALLBACK_OG_IMAGE, True


def og_image_for(building):
    """First gallery photo if the file exists right now, else the shared social card. Absolute URL."""
    return first_existing_image(building.get('gallery', []))


def json_ld_for(building, canonical, meta_description, og_image, addr):
    data = {
        '@context': 'https://schema.org',
        '@type': 'LocalBusiness',
        'name': building['name'],
        'description': meta_description,
        'url': canonical,
        'email': 'me@ebberry.com',
        'image': og_image,
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': addr['street'],
            'addressLocality': addr['city'],
            'addressRegion': addr['region'],
            'postalCode': addr['zip'],
            'addressCountry': 'US',
        },
        'geo': {
            '@type': 'GeoCoordinates',
            'latitude': building['lat'],
            'longitude': building['lng'],
        },
        'parentOrganization': {
            '@type': 'Organization',
            'name': 'E. Berry Property Management',
            'url': SITE + '/',
        },
    }
    # '<' escaped so no data value can ever close the <script> element.
    return json.dumps(data, indent=2, ensure_ascii=False).replace('<', '\\u003c')


def location_copy(b):
    """(directions, nearby) from a buildings.json entry: [{name, note}, ...] and [str, ...]; both optional."""
    bid = b['id']
    directions = b.get('directions') or []
    nearby = b.get('nearby') or []
    if not isinstance(directions, list) or not all(
            isinstance(d, dict) and set(d) == {'name', 'note'}
            and all(isinstance(d[k], str) and d[k].strip() for k in d) for d in directions):
        fail(f"buildings.json {bid}: directions must be a list of {{name, note}} objects with non-empty text")
    if not isinstance(nearby, list) or not all(isinstance(t, str) and t.strip() for t in nearby):
        fail(f'buildings.json {bid}: nearby must be a list of non-empty strings')
    return directions, nearby


def render_building_page(b, ctx):
    parts = ctx['building_parts']
    bid = b['id']
    if b.get('fieldColor') not in FIELD_COLORS:
        fail(f"buildings.json {bid}: fieldColor {b.get('fieldColor')!r} not in {FIELD_COLORS}")
    m = ADDRESS_RE.match(b['address'])
    if not m:
        fail(f"buildings.json {bid}: address {b['address']!r} must look like '19001 Vashon Hwy SW, Vashon, WA 98070'")
    addr = m.groupdict()
    city_line = f"{addr['city']}, {addr['region']} {addr['zip']}"

    canonical = f'{SITE}/buildings/{bid}/'
    title = f"{b['name']} — E. Berry Property Management"
    meta_description = (f"{b['name']}, Vashon Island. {b['tagline']} "
                        f"See what's open at {addr['street']}, or let's chat about Vashon sometime.")
    og_image, og_is_fallback = og_image_for(b)
    og_extra = ''
    if og_is_fallback:
        og_extra = ('\n  <meta property="og:image:width" content="1200" />'
                    '\n  <meta property="og:image:height" content="630" />')
    og_extra += (f'\n  <meta property="og:image:alt" content="{esc(b["name"])}, managed by E. Berry Property '
                 f'Management, a part of Windermere Vashon, Vashon Island, WA" />')

    feature_tiles = '\n'.join(parts['feature_tile'].substitute(text=esc(t)) for t in b['featureBullets'])
    gallery_tiles = '\n'.join(
        parts['gallery_tile'].substitute(src=esc(p), alt=esc(f"{b['name']}, photo {i}"))
        for i, p in enumerate(b['gallery'], 1))

    # Ferry directions and "nearby" lines are optional per-building data; a building without them omits the blocks.
    directions, nearby = location_copy(b)
    directions_block = nearby_block = ''
    if directions:
        items = '\n'.join(parts['direction_item'].substitute(label=esc(d['name']), text=esc(d['note']))
                          for d in directions)
        directions_block = parts['directions_block'].substitute(items=indent_block(items, 4))
    if nearby:
        items = '\n'.join(parts['nearby_item'].substitute(text=esc(t)) for t in nearby)
        nearby_block = parts['nearby_block'].substitute(items=indent_block(items, 4))

    suites_section = ''
    if b.get('neighborWall'):
        suites_section = parts['suites_section'].substitute(
            name=esc(b['name']), address_match=esc(b['addressMatch']))

    lease_base = b['leaseUrl'].split('#')[0]
    osm_url = (f"https://www.openstreetmap.org/?mlat={b['lat']}&mlon={b['lng']}"
               f"#map=16/{b['lat']}/{b['lng']}")

    values = {
        'id': esc(bid),
        'name': esc(b['name']),
        'tagline': esc(b['tagline']),
        'description': esc(b['description']),
        'title': esc(title),
        'meta_description': esc(meta_description),
        'canonical': esc(canonical),
        'og_image': esc(og_image),
        'og_image_extra': og_extra,
        'json_ld': indent_block(json_ld_for(b, canonical, meta_description, og_image, addr), 2),
        'field_color': b['fieldColor'],
        'street': esc(addr['street']),
        'city_line': esc(city_line),
        'osm_url': esc(osm_url),
        'lease_url': esc(lease_base),
        'lease_downloads_url': esc(f'{lease_base}#{LEASE_DOWNLOADS_ANCHOR}'),
        'feature_tiles': indent_block(feature_tiles, 6),
        'gallery_tiles': indent_block(gallery_tiles, 6),
        'directions_block': indent_block(directions_block, 8),
        'nearby_block': indent_block(nearby_block, 8),
        'suites_section': suites_section,
        'shell_styles': ctx['shell']['shell_styles'],
        'header': ctx['shell']['header'],
        'footer': ctx['shell']['footer'],
    }
    return ctx['building_template'].substitute(values)


def render_building_pages(ctx):
    """{relative output path: file text} for every building in buildings.json."""
    return {f"buildings/{b['id']}/index.html": render_building_page(b, ctx) for b in ctx['buildings']}


# ---------------------------------------------------------------- listing pages (Phase 5)

LISTING_ID_RE = re.compile(r'^[a-z0-9-]+$')
LISTING_TYPES = ('commercial', 'residential')
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
ISO_DATE_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
# "19001 Vashon Hwy SW, Suite N101, Vashon, WA 98070": everything before the last three parts is the street line.
LISTING_ADDRESS_RE = re.compile(r'^(?P<street>.+),\s*(?P<city>[^,]+),\s*(?P<region>[A-Z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?$')
DEFAULT_LOCALITY = {'city': 'Vashon', 'region': 'WA', 'zip': '98070'}      # when an address does not parse
META_DESCRIPTION_MAX = 200
# js/listing-detail.js mirrors every helper below (money, num, date_fmt, split_address, ...); keep them in step.


def money(n):
    """1181 -> '$1,181' (whole dollars, rounded half up like Intl.NumberFormat)."""
    return f'${int(math.floor(n + 0.5)):,}'


def num(n):
    """1200 -> '1,200'; 1.5 -> '1.5'."""
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    return f'{n:,}'


def date_fmt(iso):
    """'2026-11-01' -> 'Nov 1, 2026'."""
    m = ISO_DATE_RE.match(iso)
    if not m:
        fail(f'date {iso!r} is not YYYY-MM-DD')
    return f'{MONTHS[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}'


def split_address(address):
    """{'street', 'city', 'region', 'zip'}; an address that does not parse is all street, in the default locality."""
    m = LISTING_ADDRESS_RE.match(address)
    if m:
        return m.groupdict()
    return dict(street=address, **DEFAULT_LOCALITY)


def clip_text(text, limit=META_DESCRIPTION_MAX):
    """Collapse whitespace; past `limit` characters cut at a word and add an ellipsis."""
    text = ' '.join(str(text).split())
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(' ', 1)[0].rstrip(',;:.—-') + '…'


PHOTO_URL_RE = re.compile(r'^(https?://|/(?!/))', re.I)


def is_photo_url(p):
    """Only web and site-relative URLs become images (the same rule as safeUrl() in the page scripts)."""
    return isinstance(p, str) and PHOTO_URL_RE.match(p.strip()) is not None


def all_in_feature(L):
    """The 'All-in pricing — rent, CAM & shared utilities' feature, or None."""
    for f in L['features']:
        if str(f).lower().startswith('all-in pricing'):
            return str(f)
    return None


def listing_fact_tiles(L, as_of, parts):
    """Flat fact tiles: size, beds, baths, availability, all-in pricing. `as_of` (the feed's `updated`) stands in
    for 'today' so a regenerated page is reproducible; a date on or before it reads as available now."""
    tiles = []

    def tile(value):
        tiles.append(parts['fact_tile'].substitute(value=esc(value)))

    if L['sqft'] is not None:
        tile(f"{num(L['sqft'])} sq ft")
    if L['beds'] is not None:
        tile(f"{num(L['beds'])} bed")
    if L['baths'] is not None:
        tile(f"{num(L['baths'])} bath")
    tile('Available now' if L['available'] is None or L['available'] <= as_of
         else f"Available {date_fmt(L['available'])}")
    feat = all_in_feature(L)
    if feat:
        note = feat.split(' — ', 1)[1].strip() if ' — ' in feat else ''
        note = note[:1].upper() + note[1:]
        if note:
            tiles.append(parts['fact_tile_note'].substitute(value='All-in pricing', note=esc(note)))
        else:
            tile('All-in pricing')
    return '\n'.join(tiles)


def listing_json_ld(L, canonical, description, og_image, updated, addr):
    about = {
        '@type': 'Residence' if L['type'] == 'residential' else 'Place',
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': addr['street'],
            'addressLocality': addr['city'],
            'addressRegion': addr['region'],
            'postalCode': addr['zip'],
            'addressCountry': 'US',
        },
    }
    if L['lat'] is not None and L['lng'] is not None:
        about['geo'] = {'@type': 'GeoCoordinates', 'latitude': L['lat'], 'longitude': L['lng']}
    data = {
        '@context': 'https://schema.org',
        '@type': 'RealEstateListing',
        'url': canonical,
        'name': L['title'],
        'description': description,
        'datePosted': updated,
        'image': og_image,
        'about': about,
        'offers': {
            '@type': 'Offer',
            'price': L['rent'],
            'priceCurrency': 'USD',
            'availability': 'https://schema.org/InStock',
            'businessFunction': 'http://purl.org/goodrelations/v1#LeaseOut',
        },
    }
    # '<' escaped so no data value can ever close the <script> element.
    return json.dumps(data, indent=2, ensure_ascii=False).replace('<', '\\u003c')


def validate_listing(L):
    lid = L.get('id')
    if not isinstance(lid, str) or not LISTING_ID_RE.match(lid):
        fail(f'listings.json: id {lid!r} must match ^[a-z0-9-]+$ (it becomes a folder name)')
    if L.get('type') not in LISTING_TYPES:
        fail(f"listings.json {lid}: type {L.get('type')!r} not in {LISTING_TYPES}")
    if isinstance(L.get('rent'), bool) or not isinstance(L.get('rent'), (int, float)) or L['rent'] <= 0:
        fail(f"listings.json {lid}: rent {L.get('rent')!r} must be a number > 0")
    for key in ('title', 'address'):
        if not isinstance(L.get(key), str) or not L[key].strip():
            fail(f'listings.json {lid}: {key} is missing')
    for key in ('beds', 'baths', 'sqft', 'available', 'lat', 'lng', 'summary', 'photos', 'features'):
        if key not in L:
            fail(f'listings.json {lid}: missing {key!r}')
    if (L['lat'] is None) != (L['lng'] is None):
        fail(f'listings.json {lid}: lat and lng must both be null or both be numbers')
    if L['available'] is not None and not ISO_DATE_RE.match(str(L['available'])):
        fail(f"listings.json {lid}: available {L['available']!r} must be null or YYYY-MM-DD")


def render_listing_page(L, ctx):
    validate_listing(L)
    parts = ctx['listing_parts']
    lid = L['id']
    commercial = L['type'] == 'commercial'
    addr = split_address(L['address'])
    has_map = L['lat'] is not None and L['lng'] is not None
    updated = ctx['updated']

    canonical = f'{SITE}/listings/{lid}/'
    page_title = f"{L['title']} — {money(L['rent'])}/mo on Vashon — E. Berry Property Management"
    summary = ' '.join(str(L['summary'] or '').split())
    meta_description = clip_text(summary) if summary else (
        f"{L['title']} on Vashon Island for {money(L['rent'])} a month. Let's chat about Vashon sometime.")

    photos = [p.strip() for p in L['photos'] if is_photo_url(p)]
    og_image, og_is_fallback = first_existing_image(photos)
    og_extra = ''
    if og_is_fallback:
        og_extra = ('\n  <meta property="og:image:width" content="1200" />'
                    '\n  <meta property="og:image:height" content="630" />')
    og_alt = (f"{L['title']}, photo 1" if not og_is_fallback else
              'E. Berry Property Management, a part of Windermere Vashon, Vashon Island, WA')
    og_extra += f'\n  <meta property="og:image:alt" content="{esc(og_alt)}" />'

    # Breadcrumb: "Part of <building>" only when buildingId resolves against buildings.json.
    building = ctx['buildings_by_id'].get(L.get('buildingId'))
    building_crumb = ''
    if building:
        building_crumb = parts['building_crumb'].substitute(
            href=esc(f"/buildings/{building['id']}/"), name=esc(building['name']))

    badge = parts['badge_commercial' if commercial else 'badge_home'].substitute()

    tag_part = parts['feature_tag_commercial' if commercial else 'feature_tag_home']
    summary_block = parts['summary_paragraph'].substitute(text=esc(summary)) if summary else ''
    features = [str(f) for f in L['features'] if str(f).strip()]
    features_block = ''
    if features:
        tags = '\n'.join(tag_part.substitute(text=esc(f)) for f in features)
        features_block = parts['features_list'].substitute(tags=indent_block(tags, 2))

    if photos:
        tiles = []
        for i, src in enumerate(photos, 1):
            part = 'photo_tile_wide' if i == 1 and len(photos) % 2 == 1 else 'photo_tile'
            tiles.append(parts[part].substitute(src=esc(src), alt=esc(f"{L['title']}, photo {i}"),
                                                loading='eager' if i == 1 else 'lazy'))
        gallery = parts['photo_grid'].substitute(tiles=indent_block('\n'.join(tiles), 2))
    else:
        gallery = parts['gallery_placeholder'].substitute()

    # Location: the street line and the city line; the map only when there are coordinates.
    city_line = f"{addr['city']}, {addr['region']} {addr['zip']}"
    address_lines = f"{esc(addr['street'])}<br />{esc(city_line)}" if addr['street'] != L['address'] else esc(L['address'])
    if has_map:
        osm_url = (f"https://www.openstreetmap.org/?mlat={L['lat']}&mlon={L['lng']}"
                   f"#map=17/{L['lat']}/{L['lng']}")
        osm_label = 'Open in OpenStreetMap'
        map_block = parts['map_block'].substitute(
            lat=esc(L['lat']), lng=esc(L['lng']), id=esc(lid), title=esc(L['title']), rent=esc(L['rent']))
        map_css = parts['map_css'].substitute()
        map_scripts = parts['map_scripts'].substitute()
        location_layout = parts['location_layout_map'].substitute()
    else:
        osm_url = f"https://www.openstreetmap.org/search?query={quote(L['address'], safe='')}"
        osm_label = 'Find it on OpenStreetMap'
        map_block = map_css = map_scripts = ''
        location_layout = parts['location_layout_plain'].substitute()

    values = {
        'id': esc(lid),
        'building_id': esc(L['buildingId']) if building else '',
        'page_title': esc(page_title),
        'listing_title': esc(L['title']),
        'meta_description': esc(meta_description),
        'canonical': esc(canonical),
        'og_image': esc(og_image),
        'og_image_extra': og_extra,
        'json_ld': indent_block(listing_json_ld(L, canonical, meta_description, og_image, updated, addr), 2),
        'map_css': indent_block(map_css, 2),
        'map_scripts': map_scripts,
        'building_crumb': indent_block(building_crumb, 8),
        'badge': badge,
        'address': esc(L['address']),
        'rent_fmt': esc(money(L['rent'])),
        'fact_tiles': indent_block(listing_fact_tiles(L, updated, parts), 6),
        'gallery': indent_block(gallery, 4),
        'about_label': 'About this space' if commercial else 'About this home',
        'summary_block': indent_block(summary_block, 4),
        'features_block': indent_block(features_block, 4),
        'field_class': 'eb-field-mustard' if commercial else 'eb-field-sand',
        'location_layout': location_layout,
        'address_lines': address_lines,
        'osm_url': esc(osm_url),
        'osm_label': osm_label,
        'map_block': indent_block(map_block, 6),
        'shell_styles': ctx['shell']['shell_styles'],
        'header': ctx['shell']['header'],
        'footer': ctx['shell']['footer'],
    }
    return ctx['listing_template'].substitute(values)


def render_listing_fallback(ctx):
    """/listing.html: the shell plus a loading line; js/listing-detail.js does the rest in the browser."""
    return ctx['listing_fallback_template'].substitute(
        shell_styles=ctx['shell']['shell_styles'], header=ctx['shell']['header'], footer=ctx['shell']['footer'])


def render_not_found(ctx):
    """/404.html: the shell plus a warm dead end. Netlify serves it, with a 404 status, for any URL that matches nothing."""
    return {'404.html': ctx['not_found_template'].substitute(
        shell_styles=ctx['shell']['shell_styles'], header=ctx['shell']['header'], footer=ctx['shell']['footer'])}


def render_listing_pages(ctx):
    """{relative output path: file text}: listings/<id>/index.html for every listings.json entry, plus the
    client-side fallback page listing.html. sitemap.xml already lists /listings/<id>/ for every listing."""
    pages = {}
    for L in ctx['listings']:
        rel = f"listings/{L.get('id')}/index.html"
        if rel in pages:
            fail(f"listings.json: duplicate id {L.get('id')!r}")
        pages[rel] = render_listing_page(L, ctx)
    pages['listing.html'] = render_listing_fallback(ctx)
    return pages


# ---------------------------------------------------------------- owners page (Phase 8)

def owners_json_ld(canonical, meta_description):
    """The owners page is a Service run by the RealEstateAgent the homepage already describes. Deliberately no
    offers / price: the page is contact-first and never quotes a fee."""
    data = {
        '@context': 'https://schema.org',
        '@type': 'Service',
        'name': 'Property management on Vashon Island',
        'serviceType': 'Property management',
        'description': meta_description,
        'url': canonical,
        'areaServed': 'Vashon Island, WA',
        'audience': {'@type': 'Audience', 'audienceType': 'Property owners'},
        'provider': {
            '@type': 'RealEstateAgent',
            'name': 'E. Berry Property Management',
            'url': SITE + '/',
            'email': 'me@ebberry.com',
            'image': SITE + FALLBACK_OG_IMAGE,
            'parentOrganization': {'@type': 'Organization', 'name': 'Windermere Vashon'},
        },
    }
    # '<' escaped so no value can ever close the <script> element.
    return json.dumps(data, indent=2, ensure_ascii=False).replace('<', '\\u003c')


def render_owners_page(ctx):
    """/owners/: the shell plus the owners page. Contact-first, so there is no fee, rate or price data to render."""
    canonical = f'{SITE}/owners/'
    title = 'For Vashon property owners — E. Berry Property Management'
    meta_description = ("Own a home, cottage, or commercial space on Vashon? I'm Elijah Berry, and I'd like to "
                        "manage it for you. Tell me about your property.")
    values = {
        'title': esc(title),
        'meta_description': esc(meta_description),
        'canonical': esc(canonical),
        'og_image': esc(SITE + FALLBACK_OG_IMAGE),
        'json_ld': indent_block(owners_json_ld(canonical, meta_description), 2),
        'shell_styles': ctx['shell']['shell_styles'],
        'header': ctx['shell']['header'],
        'footer': ctx['shell']['footer'],
    }
    return {'owners/index.html': ctx['owners_template'].substitute(values)}


# ---------------------------------------------------------------- technology page (Phase 9)

def technology_json_ld(canonical, meta_description):
    """The technology page is a WebPage about Ledger, published by the RealEstateAgent the homepage already
    describes. Deliberately no offers / price / rating: Ledger is the firm's own software, not a product for sale,
    and the page quotes no numbers."""
    data = {
        '@context': 'https://schema.org',
        '@type': 'WebPage',
        'name': 'Our technology',
        'url': canonical,
        'description': meta_description,
        'inLanguage': 'en-US',
        'isPartOf': {'@type': 'WebSite', 'name': 'E. Berry Property Management', 'url': SITE + '/'},
        'about': {
            '@type': 'SoftwareApplication',
            'name': 'Ledger',
            'applicationCategory': 'BusinessApplication',
            'description': 'Property-management software built for E. Berry Property Management on Vashon Island.',
        },
        'publisher': {
            '@type': 'RealEstateAgent',
            'name': 'E. Berry Property Management',
            'url': SITE + '/',
            'email': 'me@ebberry.com',
            'image': SITE + FALLBACK_OG_IMAGE,
            'parentOrganization': {'@type': 'Organization', 'name': 'Windermere Vashon'},
        },
    }
    # '<' escaped so no value can ever close the <script> element.
    return json.dumps(data, indent=2, ensure_ascii=False).replace('<', '\\u003c')


def render_technology_page(ctx):
    """/technology/: the shell plus the "Our technology" page about Ledger. Every factual claim on it was checked
    against the Ledger source before it shipped (the claim-by-claim table is in the Phase 9 hand-back); the copy
    lives in the template, so a change to it is a change to a reviewed text."""
    canonical = f'{SITE}/technology/'
    title = 'Our technology — E. Berry Property Management'
    meta_description = ("Meet Ledger, built for Vashon Island rentals. Tenants report problems, follow repairs to done "
                        "and pay securely through Stripe; owners see every repair as it happens.")
    values = {
        'title': esc(title),
        'meta_description': esc(meta_description),
        'canonical': esc(canonical),
        'og_image': esc(SITE + FALLBACK_OG_IMAGE),
        'json_ld': indent_block(technology_json_ld(canonical, meta_description), 2),
        'shell_styles': ctx['shell']['shell_styles'],
        'header': ctx['shell']['header'],
        'footer': ctx['shell']['footer'],
    }
    return {'technology/index.html': ctx['technology_template'].substitute(values)}


# ---------------------------------------------------------------- legal pages (Phase 13): /fair-housing/, /privacy/, /accessibility/
#
# EVIDENCE RULE (the same one the technology page lives by): a fact goes on these pages only after it was read on a primary source, and every
# source is linked at the bottom of /fair-housing/. A fact that could not be verified is left off: no deadlines, no statistics, no prices, and a
# phone number only where the agency prints it on its own page. The data below is the ONE place the verified lists live; the templates render
# it, and tools/check_site.py pins an independent copy of each list so that an edit here cannot slip through.
#
# Verified 2026-10-18 (every URL fetched that day):
#   Federal list ........ HUD, "Fair Housing: Rights and Obligations" and "Report Housing Discrimination" (the seven classes, in HUD's words)
#   Washington list ..... RCW 49.60.222(1), app.leg.wa.gov (read in full); source of income RCW 59.18.255(2), (3), (5); screening RCW 59.18.257(1)(a)
#   King County list .... K.C.C. 12.20.040.A (as amended by Ord. 19977, 2025) = "the protected classes as defined in K.C.C. chapter 3.12D" + Section 8 /
#                         other housing subsidy + alternative source of income; K.C.C. 3.12D.005.H defines "protected classes"; 12.20.040.E adds
#                         use of a service or assistive animal. Compiled code "UPDATED: September 9, 2026" (aqua.kingcounty.gov). It applies in
#                         unincorporated King County (K.C.C. 12.20.013), which includes all of Vashon/Maury Island (King County, Community Service Areas).
#                         NOT in the current code, so NOT listed: "ancestry" and "gender" (Ord. 18708 of 2018 had them; 3.12D says "sex" and "ethnicity").
#   Agencies ............ hud.gov/reporthousingdiscrimination (phone 1-800-669-9777); hum.wa.gov/fair-housing (1-800-233-3247, also on its contact page);
#                         kingcounty.gov Civil Rights Program page (206-263-2446, TTY 7-1-1). The county's office is called the "Civil Rights Program" now.
#   Left off on purpose . "no pet fee for assistance animals": HUD rescinded FHEO-2020-01 on 2025-09-17 and reconfirmed it on 2026-05-22, and no current
#                         federal, Washington or King County rule could be verified. Filing deadlines: each agency states its own; none is repeated here.

LEGAL_DATE = '2026-10-18'     # the day these pages were written: the privacy notice's effective date, the accessibility statement's date, and when the sources were checked
MONTH_NAMES = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')

URL_HUD_RIGHTS = 'https://www.hud.gov/stat/fheo/rights-obligations'
URL_HUD_REPORT = 'https://www.hud.gov/reporthousingdiscrimination'
URL_RCW_49_60_222 = 'https://app.leg.wa.gov/RCW/default.aspx?cite=49.60.222'
URL_RCW_59_18_255 = 'https://app.leg.wa.gov/RCW/default.aspx?cite=59.18.255'
URL_RCW_59_18_257 = 'https://app.leg.wa.gov/RCW/default.aspx?cite=59.18.257'
URL_KCC_TITLE_12 = 'https://aqua.kingcounty.gov/council/clerk/code/15_Title_12.htm'
URL_KCC_TITLE_3 = 'https://aqua.kingcounty.gov/council/clerk/code/06_Title_3.htm'
URL_KC_UNINCORPORATED = 'https://kingcounty.gov/en/dept/local-services/governance-leadership/local-government-for-unincorporated-king-county/community-service-areas'
URL_WSHRC = 'https://www.hum.wa.gov/fair-housing'
URL_KC_CIVIL_RIGHTS = 'https://kingcounty.gov/en/dept/executive/governance-leadership/equity-social-justice/civil-rights-program'

# The three protected-class lists on /fair-housing/. Each list is that law's own wording (first letter capitalized). One list, rendered by
# tools/templates/legal.parts.tmpl.html: the page cannot say anything this does not.
PROTECTED_CLASSES = (
    {'key': 'federal', 'label': 'Federal law', 'title': 'The Fair Housing Act',
     'items': ['Race', 'Color', 'National origin', 'Religion', 'Sex', 'Familial status', 'Disability'],
     'note': '',
     'sources': (('HUD, Fair Housing: Rights and Obligations', URL_HUD_RIGHTS),)},
    {'key': 'washington', 'label': 'Washington law', 'title': 'RCW 49.60.222',
     'items': ['Sex', 'Marital status', 'Sexual orientation', 'Race', 'Creed', 'Color', 'National origin',
               'Citizenship or immigration status', 'Families with children status',
               'Honorably discharged veteran or military status',
               'Presence of any sensory, mental, or physical disability',
               'Use of a trained dog guide or service animal by a person with a disability'],
     'note': '',
     'sources': (('RCW 49.60.222', URL_RCW_49_60_222),)},
    {'key': 'king-county', 'label': 'King County code', 'title': 'K.C.C. 12.20.040',
     'items': ['Sex', 'Race', 'Color', 'National origin', 'Ethnicity', 'Religious affiliation', 'Disability', 'Sexual orientation',
               'Gender identity or expression', 'Age (except by minimum age and retirement provisions)',
               'Status as a family caregiver', 'Parental status', 'Marital status',
               "Military status, or status as a veteran who was honorably discharged or who was discharged solely as a result of "
               "the person's sexual orientation or gender identity or expression",
               'Citizenship or immigration status',
               'Participation in the Section 8 program or other housing subsidy program', 'Alternative source of income',
               'Use of a service or assistive animal by an individual with a disability'],
     'note': ("Where federal or state law, a regulation or a government contract authorizes a distinction based on citizenship or "
              "immigration status, the county code does not treat it as an unfair practice."),
     'sources': (('K.C.C. 12.20.040', URL_KCC_TITLE_12), ('K.C.C. 3.12D.005', URL_KCC_TITLE_3))},
)

# Where to take a concern. Website always; phone only where the agency prints it on its own page (see the header comment above).
AGENCIES = (
    {'name': 'HUD: Office of Fair Housing and Equal Opportunity',
     'about': "The federal agency that investigates complaints of housing discrimination under the Fair Housing Act.",
     'url': URL_HUD_REPORT, 'link_text': 'Report housing discrimination', 'phone': '1-800-669-9777', 'phone_note': ''},
    {'name': 'Washington State Human Rights Commission',
     'about': "The state agency that enforces Washington's Law Against Discrimination, including its fair housing rules.",
     'url': URL_WSHRC, 'link_text': 'Fair housing and how to file', 'phone': '1-800-233-3247', 'phone_note': ''},
    {'name': 'King County Civil Rights Program',
     'about': "Investigates discrimination complaints about housing providers in unincorporated King County, which includes Vashon.",
     'url': URL_KC_CIVIL_RIGHTS, 'link_text': 'Civil Rights Program', 'phone': '206-263-2446', 'phone_note': ' (TTY 7-1-1)'},
)

# "Where this comes from" at the bottom of /fair-housing/: everything the page leans on.
LEGAL_SOURCES = (
    ('HUD: Fair Housing, Rights and Obligations', URL_HUD_RIGHTS),
    ('HUD: Report Housing Discrimination', URL_HUD_REPORT),
    ('RCW 49.60.222: unfair practices in real estate transactions (Washington)', URL_RCW_49_60_222),
    ('RCW 59.18.255: source of income (Washington)', URL_RCW_59_18_255),
    ('RCW 59.18.257: tenant screening (Washington)', URL_RCW_59_18_257),
    ('King County Code, Title 12, chapter 12.20: open housing', URL_KCC_TITLE_12),
    ('King County Code, Title 3, chapter 3.12D: protected classes', URL_KCC_TITLE_3),
    ('King County: unincorporated areas, including Vashon/Maury Island', URL_KC_UNINCORPORATED),
    ('Washington State Human Rights Commission: Fair Housing', URL_WSHRC),
    ('King County Civil Rights Program', URL_KC_CIVIL_RIGHTS),
)

# The forms the privacy notice describes. The field lists are READ from the forms' own markup, never typed here: `source` is the file whose
# <form name="..."> is parsed (index.html is the homepage's; the other two are the templates that every listing and the owners page are built from).
PRIVACY_FORMS = (
    {'name': 'inquiry', 'source': 'index.html', 'title': 'The inquiry form',
     'where': 'On the home page and on the Courthouse Square page.',
     'hidden': 'On the Courthouse Square page it also notes which building page you wrote from.'},
    {'name': 'listing-inquiry', 'source': 'tools/templates/listing.tmpl.html', 'title': 'The listing form',
     'where': "At the bottom of each listing's page.",
     'hidden': 'It also notes which listing and building you asked about.'},
    {'name': 'owner-intro', 'source': 'tools/templates/owners.tmpl.html', 'title': 'The owner form',
     'where': 'On the For owners page.',
     'hidden': ''},
)
FORM_LABEL_RE = re.compile(r'<span class="mb-1\.5 block text-base font-medium">(.*?)</span>(?=\s*<(?:input|select|textarea)\b)', re.S)


def long_date(iso):
    """'2026-10-18' -> 'October 18, 2026'."""
    m = ISO_DATE_RE.match(iso)
    if not m:
        fail(f'date {iso!r} is not YYYY-MM-DD')
    return f'{MONTH_NAMES[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}'


def indent_lines(text, n):
    """Prefix every line (the first too) with n spaces."""
    pad = ' ' * n
    return '\n'.join(pad + line if line else line for line in text.split('\n'))


def form_labels(markup, form_name, where):
    """The visible field labels of <form name="form_name"> in `markup`, in order, as a visitor reads them: tags dropped, the required-field
    asterisk dropped ("Name *" -> "Name"), "(optional)" kept. The honeypot has no such label, so it is not listed."""
    m = re.search(r'<form\b[^>]*\bname="' + re.escape(form_name) + r'"[^>]*>(.*?)</form>', markup, re.S)
    if not m:
        fail(f'{where}: no <form name="{form_name}"> to read the privacy notice from')
    labels = []
    for raw in FORM_LABEL_RE.findall(m.group(1)):
        text = ' '.join(html.unescape(re.sub(r'<[^>]+>', '', raw)).split())
        labels.append(re.sub(r'\s*\*$', '', text))
    if not labels:
        fail(f'{where}: <form name="{form_name}"> has no field labels (did the form markup change?)')
    return labels


def legal_json_ld(name, canonical, meta_description):
    """A WebPage published by the firm. No offers, prices, ratings or reviews: these are notices, not products."""
    data = {
        '@context': 'https://schema.org',
        '@type': 'WebPage',
        'name': name,
        'url': canonical,
        'description': meta_description,
        'inLanguage': 'en-US',
        'dateModified': LEGAL_DATE,
        'isPartOf': {'@type': 'WebSite', 'name': 'E. Berry Property Management', 'url': SITE + '/'},
        'publisher': {
            '@type': 'RealEstateAgent',
            'name': 'E. Berry Property Management',
            'url': SITE + '/',
            'email': 'me@ebberry.com',
            'image': SITE + FALLBACK_OG_IMAGE,
            'parentOrganization': {'@type': 'Organization', 'name': 'Windermere Vashon'},
        },
    }
    # '<' escaped so no value can ever close the <script> element.
    return json.dumps(data, indent=2, ensure_ascii=False).replace('<', '\\u003c')


def legal_values(ctx, slug, h1, title_text, meta_description):
    """The placeholders every legal template shares."""
    canonical = f'{SITE}/{slug}/'
    title = f'{title_text} — E. Berry Property Management'
    return {
        'title': esc(title),
        'meta_description': esc(meta_description),
        'canonical': esc(canonical),
        'og_image': esc(SITE + FALLBACK_OG_IMAGE),
        'json_ld': indent_block(legal_json_ld(h1, canonical, meta_description), 2),
        'shell_styles': ctx['shell']['shell_styles'],
        'header': ctx['shell']['header'],
        'footer': ctx['shell']['footer'],
    }


def render_fair_housing_page(ctx):
    """/fair-housing/: the shell plus the fair housing statement. The lists, the agencies and the sources are all rendered from the data above."""
    parts = ctx['legal_parts']
    link = lambda label, href: parts['source_link'].substitute(href=esc(href), label=esc(label))
    cards = []
    for c in PROTECTED_CLASSES:
        items = '\n'.join(parts['class_item'].substitute(text=esc(t)) for t in c['items'])
        note = parts['class_note'].substitute(text=esc(c['note'])) if c['note'] else ''
        cards.append(parts['class_card'].substitute(
            key=esc(c['key']), label=esc(c['label']), title=esc(c['title']), items=indent_lines(items, 4),
            note=note, sources=', '.join(link(label, url) for label, url in c['sources'])).replace('\n\n', '\n'))
    agencies = []
    for a in AGENCIES:
        digits = re.sub(r'\D', '', a['phone'])
        tel = '+' + (digits if len(digits) == 11 else '1' + digits)
        agencies.append(parts['agency'].substitute(
            name=esc(a['name']), about=esc(a['about']), url=esc(a['url']), link_text=esc(a['link_text']),
            tel=esc(tel), phone=esc(a['phone']), phone_note=esc(a['phone_note'])))
    sources = [parts['source_item'].substitute(href=esc(url), label=esc(label)) for label, url in LEGAL_SOURCES]
    values = legal_values(
        ctx, 'fair-housing', 'Fair housing', 'Fair housing',
        "Every home I manage is offered to everyone on the same terms. Here's who the law protects on Vashon, "
        "how I screen, and where to go if something doesn't feel right.")
    values.update({
        'class_cards': indent_lines('\n'.join(cards), 6),
        'agencies': indent_lines('\n'.join(agencies), 10),
        'source_items': indent_lines('\n'.join(sources), 8),
        'checked_date': long_date(LEGAL_DATE),
    })
    return {'fair-housing/index.html': ctx['fair_housing_template'].substitute(values)}


def render_privacy_page(ctx):
    """/privacy/: the shell plus the privacy notice. The form field lists come from the forms' own markup (ctx['forms'])."""
    parts = ctx['legal_parts']
    cards = []
    for f in PRIVACY_FORMS:
        fields = '\n'.join(parts['class_item'].substitute(text=esc(t)) for t in ctx['forms'][f['name']])
        hidden = parts['hidden_note'].substitute(text=esc(f['hidden'])) if f['hidden'] else ''
        cards.append(parts['form_card'].substitute(
            name=esc(f['name']), title=esc(f['title']), where=esc(f['where']), fields=indent_lines(fields, 4),
            hidden_note=hidden).replace('\n\n', '\n'))
    values = legal_values(
        ctx, 'privacy', 'Privacy', 'Privacy',
        "I collect only what you type into my forms, I use it to write back, and I don't sell it. "
        "No cookies, analytics or ads on this site.")
    values.update({'form_cards': indent_lines('\n'.join(cards), 6), 'effective_date': long_date(LEGAL_DATE)})
    return {'privacy/index.html': ctx['privacy_template'].substitute(values)}


def render_accessibility_page(ctx):
    """/accessibility/: the shell plus the accessibility statement."""
    values = legal_values(
        ctx, 'accessibility', 'Accessibility', 'Accessibility',
        "I'm aiming for WCAG 2.1 AA. Here's what the site checks, how the map and the list work together, "
        "and how to tell me when something gets in your way.")
    values.update({'statement_date': long_date(LEGAL_DATE)})
    return {'accessibility/index.html': ctx['accessibility_template'].substitute(values)}


# ---------------------------------------------------------------- sitemap

def render_sitemap(ctx):
    lastmod = ctx['updated']
    urls = [f'{SITE}/', f'{SITE}/listings/', f'{SITE}/owners/', f'{SITE}/technology/',
            f'{SITE}/fair-housing/', f'{SITE}/privacy/', f'{SITE}/accessibility/']
    urls += [f"{SITE}/listings/{quote(L['id'])}/" for L in ctx['listings']]
    urls += [f"{SITE}/buildings/{quote(b['id'])}/" for b in ctx['buildings']]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines += ['  <url>', f'    <loc>{esc(u)}</loc>', f'    <lastmod>{esc(lastmod)}</lastmod>', '  </url>']
    lines.append('</urlset>')
    return {'sitemap.xml': '\n'.join(lines) + '\n'}


# ---------------------------------------------------------------- driver

def build_files():
    ctx = load_context()
    files = {}
    files.update(render_building_pages(ctx))
    files.update(render_listing_pages(ctx))
    files.update(render_not_found(ctx))
    files.update(render_owners_page(ctx))
    files.update(render_technology_page(ctx))
    files.update(render_fair_housing_page(ctx))
    files.update(render_privacy_page(ctx))
    files.update(render_accessibility_page(ctx))
    files.update(render_sitemap(ctx))
    return files


def write_files(files, out_root):
    """Write {relative path: text} under out_root as UTF-8 with LF newlines. Returns the paths that changed."""
    changed = []
    for rel, text in files.items():
        path = os.path.join(out_root, rel)
        data = text.encode('utf-8')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                if f.read() == data:
                    continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        changed.append(rel)
    return changed


def generated_pages_on_disk():
    """buildings/<id>/index.html and listings/<id>/index.html files that exist in the repo (to spot orphans of
    removed buildings and listings). listings/index.html is the hand-maintained index, not generated."""
    found = set()
    for top in ('buildings', 'listings'):
        base = os.path.join(ROOT, top)
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                if os.path.isfile(os.path.join(base, name, 'index.html')):
                    found.add(f'{top}/{name}/index.html')
    return found


def first_difference(old, new):
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), 'committed', 'regenerated', n=0, lineterm=''):
        if line.startswith(('---', '+++', '@@')):
            continue
        return line[:140] if line[1:].strip() else 'whitespace-only change'
    return 'line endings or trailing newline differ'


def check_files(files):
    """Regenerate into a temp dir and byte-compare with the committed output. Prints problems like
    tools/check_site.py does; returns the exit code."""
    problems = []
    tmp = tempfile.mkdtemp(prefix='build_pages_')
    try:
        write_files(files, tmp)
        for rel in sorted(files):
            committed = os.path.join(ROOT, rel)
            fresh = os.path.join(tmp, rel)
            if not os.path.exists(committed):
                problems.append(f'{rel}: missing (run python3 tools/build_pages.py and commit it)')
                continue
            with open(committed, 'rb') as a, open(fresh, 'rb') as b:
                old, new = a.read(), b.read()
            if old != new:
                hint = first_difference(old.decode('utf-8', 'replace'), new.decode('utf-8', 'replace'))
                problems.append(f'{rel}: out of date (run python3 tools/build_pages.py and commit it)'
                                + (f'; first change: {hint}' if hint else ''))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for rel in sorted(generated_pages_on_disk() - set(files)):
        problems.append(f'{rel}: committed but no longer generated (its entry left data/; delete it)')

    if problems:
        print(f'FAIL: {len(problems)} problem(s) out of {len(files)} generated file(s)')
        for p in problems:
            print(f'  - {p}')
        return 1
    print(f'OK: {len(files)} generated file(s) match the committed output')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='Generate the E. Berry building, listing, owners, technology and legal pages and sitemap.xml.')
    ap.add_argument('--check', action='store_true',
                    help='regenerate to a temp dir and compare with the committed files; exit 1 if stale')
    args = ap.parse_args(argv)

    files = build_files()
    if args.check:
        return check_files(files)
    changed = write_files(files, ROOT)
    for rel in sorted(files):
        print(f"{'wrote    ' if rel in changed else 'unchanged'} {rel}")
    for rel in sorted(generated_pages_on_disk() - set(files)):
        print(f'orphan    {rel}  (no longer generated; delete it)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
