#!/usr/bin/env python3
# Build the Burton Inn lease PDF from burton-inn/lease.md, reusing the house
# document style (fonts, styles, markdown renderer, numbered footer) from
# build_lease_docs.py. Deal-specific document — separate from the Courthouse
# Square standard lease set on purpose.

import os, re
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate

import build_lease_docs as house

ROOT = house.ROOT
SRC = ROOT + '/burton-inn/lease.md'
OUT = ROOT + '/burton-inn/lease.pdf'


def footer_from_md(md):
    """Stamp the footer from the version line: '**Draft v0.1 — July 11, 2026 — ...**'."""
    m = re.search(r'\*\*(Draft v[\w.]+)\s+—\s+([^—*]+?)\s+—', md)
    ver, date = (m.group(1), m.group(2)) if m else ('Draft', '')
    return f"The Burton Inn — Commercial Lease Agreement    {ver}, {date}".rstrip(', ')


if __name__ == '__main__':
    with open(SRC) as f:
        md = f.read()
    doc = SimpleDocTemplate(OUT, pagesize=letter,
                            leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            title='The Burton Inn — Commercial Lease Agreement')
    doc.build(house.md_to_story(md), canvasmaker=house.footer_canvas(footer_from_md(md)))
    print('wrote', OUT)
