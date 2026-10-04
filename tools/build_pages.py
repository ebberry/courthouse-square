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
        sitemap.xml                 home, /listings/, every listing and every building page (not the 404)

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
    return {
        'buildings': buildings_doc['buildings'],
        'buildings_by_id': {b['id']: b for b in buildings_doc['buildings']},
        'listings': listings_doc['listings'],
        'updated': listings_doc['updated'],
        'shell': extract_shell(read_text(os.path.join(ROOT, 'index.html'))),
        'building_template': load_template('building.tmpl.html'),
        'building_parts': load_parts('building.parts.tmpl.html'),
        'listing_template': load_template('listing.tmpl.html'),
        'listing_parts': load_parts('listing.parts.tmpl.html'),
        'listing_fallback_template': load_template('listing-fallback.tmpl.html'),
        'not_found_template': load_template('404.tmpl.html'),
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


# ---------------------------------------------------------------- sitemap

def render_sitemap(ctx):
    lastmod = ctx['updated']
    urls = [f'{SITE}/', f'{SITE}/listings/']
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
    ap = argparse.ArgumentParser(description='Generate the E. Berry building and listing pages and sitemap.xml.')
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
