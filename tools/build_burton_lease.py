#!/usr/bin/env python3
# Build the Burton Inn lease document set, reusing the house document style
# (fonts, styles, markdown renderer, numbered footer) from build_lease_docs.py.
#
# Architecture (Two-Tier Value-Sharing Lease, keep Sections 2/3 & 3/3 identical):
#   - Section 1/3 = burton-inn/terms-sheet.md  (Articles 1-9, signatures, and
#               Exhibits A-J; Exhibit H, Addendum, carries every modification of
#               Section 2/3, each citing the Article it modifies).
#   - Sections 2/3 & 3/3 = forms/two-tier-v2.1.md  (Standard Lease Terms +
#               Definitions & Glossary Terms, Version 2.1, September 19, 2026) —
#               the shared form, reused VERBATIM, never copied or edited here.
#
# Outputs:
#   - burton-inn/terms-sheet.pdf   Section 1/3 alone (with Exhibits)
#   - burton-inn/lease.pdf         full package: Section 1/3, then Sections 2/3 & 3/3

import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, PageBreak

import build_lease_docs as house

ROOT = house.ROOT
BDIR = ROOT + '/burton-inn'
STANDARD_FORM = ROOT + '/forms/two-tier-v2.1.md'   # Sections 2/3 & 3/3, Version 2.1


def version_of(md):
    """Pull 'Draft v0.7, July 14, 2026' out of the '**Draft v0.7 — July 14, 2026 — ...**' line."""
    m = re.search(r'\*\*(Draft v[\w.]+)\s+—\s+([^—*]+?)\s+—', md)
    return f'{m.group(1)}, {m.group(2)}' if m else 'Draft'


def check_glyphs(*mds):
    """Fail loudly if any character isn't in the body font (Libre Baskerville).
    Missing glyphs render as empty rectangles ('tofu') in the PDF. Soft
    dependency: skip with a warning if fontTools isn't installed."""
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
    with open(STANDARD_FORM) as f:
        form_md = f.read()          # Sections 2/3 & 3/3, verbatim v2.1
    ver = version_of(ts_md)         # Section 1/3 draft version (the form carries its own v2.1 stamp)
    check_glyphs(ts_md, form_md)

    # Section 1/3 on its own.
    build(house.md_to_story(ts_md), BDIR + '/terms-sheet.pdf',
          'The Burton Inn — Section 1/3',
          f'The Burton Inn — Section 1/3    {ver}')

    # Full signable package: Section 1/3, then Sections 2/3 & 3/3 on a fresh
    # page, with continuous page numbering.
    build(house.md_to_story(ts_md) + [PageBreak()] + house.md_to_story(form_md),
          BDIR + '/lease.pdf',
          'The Burton Inn — Two-Tier Value-Sharing Lease',
          f'The Burton Inn — Two-Tier Lease    {ver}')
