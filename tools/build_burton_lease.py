#!/usr/bin/env python3
# Build the Burton Inn lease document set, reusing the house document style
# (fonts, styles, markdown renderer, numbered footer) from build_lease_docs.py.
# The deal is a one-off, single-tenant, whole-building NNN + percentage-rent
# lease, so it has its own two-part form rather than the Courthouse Square
# office boilerplate:
#   - burton-inn/terms-sheet.pdf     Lease Terms Sheet (deal page + exhibits + signatures)
#   - burton-inn/standard-terms.pdf  Standard Lease Terms + Definitions & Glossary
#   - burton-inn/lease.pdf           the two above merged into one signable package

import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, PageBreak

import build_lease_docs as house

ROOT = house.ROOT
BDIR = ROOT + '/burton-inn'


def version_of(md):
    """Pull 'Draft v0.3, July 11, 2026' out of the '**Draft v0.3 — July 11, 2026 — ...**' line."""
    m = re.search(r'\*\*(Draft v[\w.]+)\s+—\s+([^—*]+?)\s+—', md)
    return f'{m.group(1)}, {m.group(2)}' if m else 'Draft'


def check_glyphs(*mds):
    """Fail loudly if any character isn't in the body font (Libre Baskerville).
    Missing glyphs render as empty rectangles ('tofu') in the PDF — e.g. the
    'almost equal' sign, which Baskerville lacks. Catches it before it ships.
    Soft dependency: if fontTools isn't installed, skip with a warning rather
    than block the build (which only needs reportlab)."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print('build_burton_lease: fontTools not installed; skipping glyph check '
              '(pip install fonttools to enable)')
        return
    import unicodedata
    cmap = TTFont(ROOT + '/fonts/LibreBaskerville-400.ttf').getBestCmap()
    missing = {ch for md in mds for ch in md if ord(ch) > 0x7F and ord(ch) not in cmap}
    if missing:
        lines = [f"  U+{ord(c):04X} {c!r}  {unicodedata.name(c, '?')}" for c in sorted(missing)]
        raise SystemExit("build_burton_lease: characters missing from Libre Baskerville "
                         "(would render as tofu). Replace them:\n" + "\n".join(lines))


def build(story, out, title, footer):
    doc = SimpleDocTemplate(out, pagesize=letter,
                            leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            title=title)
    doc.build(story, canvasmaker=house.footer_canvas(footer))
    print('wrote', out)


if __name__ == '__main__':
    with open(BDIR + '/terms-sheet.md') as f:
        ts_md = f.read()
    with open(BDIR + '/standard-terms.md') as f:
        st_md = f.read()
    ver = version_of(ts_md)
    check_glyphs(ts_md, st_md)

    build(house.md_to_story(ts_md), BDIR + '/terms-sheet.pdf',
          'The Burton Inn — Lease Terms Sheet',
          f'The Burton Inn — Lease Terms Sheet    {ver}')
    build(house.md_to_story(st_md), BDIR + '/standard-terms.pdf',
          'The Burton Inn — Standard Lease Terms',
          f'The Burton Inn — Standard Lease Terms    {ver}')
    # Combined signable package: Terms Sheet, then Standard Terms on a fresh page,
    # with continuous page numbering across the whole instrument.
    build(house.md_to_story(ts_md) + [PageBreak()] + house.md_to_story(st_md),
          BDIR + '/lease.pdf',
          'The Burton Inn — Commercial Lease Agreement',
          f'The Burton Inn — Commercial Lease Agreement    {ver}')
