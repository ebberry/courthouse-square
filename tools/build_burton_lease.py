#!/usr/bin/env python3
# Build the Burton Inn lease document set, reusing the house document style
# (fonts, styles, markdown renderer, numbered footer) from build_lease_docs.py.
#
# Architecture (Option A — keep Parts 2 & 3 consistent):
#   - Part 1  = burton-inn/terms-sheet.md  (Terms Sheet §1-9, signatures, and
#               Exhibits A-D; Exhibit D is the Triple-Net / Percentage-Rent /
#               Single-Tenant Amendment that carries all deal-specific terms).
#   - Parts 2 & 3 = lease/lease.md  (the Courthouse Square Standard Lease Terms
#               + Definitions & Glossary, Version 1.5) — the vetted master form,
#               reused VERBATIM, not copied into burton-inn/ so it cannot drift.
#
# Outputs:
#   - burton-inn/terms-sheet.pdf   Part 1 alone (deal page + exhibits + amendment)
#   - burton-inn/lease.pdf         full package: Part 1, then the v1.5 form
# The standalone v1.5 form PDF is lease/lease.pdf (built by build_lease_docs.py);
# the Burton package does not emit its own copy, keeping a single source.

import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, PageBreak

import build_lease_docs as house

ROOT = house.ROOT
BDIR = ROOT + '/burton-inn'
STANDARD_FORM = ROOT + '/lease/lease.md'   # v1.5 Standard Lease Terms + Definitions (Parts 2 & 3)


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
        form_md = f.read()          # Parts 2 & 3, verbatim v1.5
    ver = version_of(ts_md)         # Part 1 draft version (Parts 2 & 3 carry their own v1.5 stamp)
    check_glyphs(ts_md, form_md)

    # Part 1 on its own.
    build(house.md_to_story(ts_md), BDIR + '/terms-sheet.pdf',
          'The Burton Inn — Lease Terms Sheet',
          f'The Burton Inn — Lease Terms Sheet    {ver}')

    # Full signable package: Part 1, then the v1.5 Standard Lease Terms +
    # Definitions on a fresh page, with continuous page numbering.
    build(house.md_to_story(ts_md) + [PageBreak()] + house.md_to_story(form_md),
          BDIR + '/lease.pdf',
          'The Burton Inn — Commercial Lease Agreement',
          f'The Burton Inn — Commercial Lease Agreement    {ver}')
