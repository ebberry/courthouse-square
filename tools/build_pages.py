#!/usr/bin/env python3
"""Static page generator for the E. Berry site.

The owner runs this locally and commits the output; Netlify never builds.
Stdlib only, so it runs anywhere Python 3 does.

Reads   data/buildings.json, data/listings.json, and the canonical page shell in index.html
        (the EB:HEADER / EB:FOOTER / EB:SHELL-STYLES blocks), plus tools/templates/*.
Writes  buildings/<id>/index.html   one landing page per building   (tools/templates/building.tmpl.html)
        sitemap.xml                 home, /listings/, every listing and every building page

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

# Per-building location copy (ferry directions and nearby landmarks). It lives here, not in the template,
# so the template stays building-agnostic; a building with no entry simply omits those two blocks.
# TODO: move into data/buildings.json (optional `directions` / `nearby` fields) when the owner is ready.
LOCATION_COPY = {
    'courthouse-square': {
        'directions': [
            ('Fauntleroy (West Seattle)',
             "About 15 minutes south on Vashon Hwy SW. You'll come straight up the island and find us on the right."),
            ('Point Defiance (Tacoma)',
             'About 20 minutes north on Vashon Hwy SW from the south-end dock.'),
        ],
        'nearby': [
            'Vashon Athletic Center, across the street.',
            'Vashon schools, walking distance.',
            'King County Metro bus stop, at the corner.',
        ],
    },
}


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
        'listings': listings_doc['listings'],
        'updated': listings_doc['updated'],
        'shell': extract_shell(read_text(os.path.join(ROOT, 'index.html'))),
        'building_template': load_template('building.tmpl.html'),
        'building_parts': load_parts('building.parts.tmpl.html'),
    }


# ---------------------------------------------------------------- building pages

def og_image_for(building):
    """First gallery photo if the file exists right now, else the shared social card. Absolute URL."""
    for path in building.get('gallery', []):
        if os.path.exists(os.path.join(ROOT, path.lstrip('/'))):
            return SITE + path, False
    return SITE + FALLBACK_OG_IMAGE, True


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

    copy = LOCATION_COPY.get(bid, {})
    directions_block = nearby_block = ''
    if copy.get('directions'):
        items = '\n'.join(parts['direction_item'].substitute(label=esc(l), text=esc(t))
                          for l, t in copy['directions'])
        directions_block = parts['directions_block'].substitute(items=indent_block(items, 4))
    if copy.get('nearby'):
        items = '\n'.join(parts['nearby_item'].substitute(text=esc(t)) for t in copy['nearby'])
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

def render_listing_pages(ctx):
    """Phase 5 fills this in: one listings/<slug>/index.html per listings.json entry, rendered from a new
    tools/templates/listing.tmpl.html the same way render_building_pages() works. Returns {path: text}.
    sitemap.xml already lists /listings/<slug>/ for every listing, so nothing else needs to change."""
    return {}


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
    # Phase 5: listing pages render here
    files.update(render_listing_pages(ctx))
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
    """buildings/<id>/index.html files that exist in the repo (to spot orphans of removed buildings)."""
    base = os.path.join(ROOT, 'buildings')
    found = set()
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if os.path.isfile(os.path.join(base, name, 'index.html')):
                found.add(f'buildings/{name}/index.html')
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
        problems.append(f'{rel}: committed but no longer generated (its building left buildings.json; delete it)')

    if problems:
        print(f'FAIL: {len(problems)} problem(s) out of {len(files)} generated file(s)')
        for p in problems:
            print(f'  - {p}')
        return 1
    print(f'OK: {len(files)} generated file(s) match the committed output')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='Generate the E. Berry building pages and sitemap.xml.')
    ap.add_argument('--check', action='store_true',
                    help='regenerate to a temp dir and compare with the committed files; exit 1 if stale')
    args = ap.parse_args(argv)

    files = build_files()
    if args.check:
        return check_files(files)
    changed = write_files(files, ROOT)
    for rel in sorted(files):
        print(f"{'wrote    ' if rel in changed else 'unchanged'} {rel}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
