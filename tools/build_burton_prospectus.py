#!/usr/bin/env python3
# Build the Burton Inn "Rent Basis & Owner Return" prospectus
# (burton-inn/prospectus.md -> burton-inn/prospectus.pdf) in the house style.
#
# The house markdown renderer has no tables or write-in space, so this adds
# three block types on top of it:
#   | a | b |        pipe tables (header row, then |---|--:| alignment row)
#   [[notes:N]]      a "NOTES" label followed by N ruled lines to write on
#   [[lines:N]]      N ruled lines, no label
#   [[pagebreak]]    start a new page
# Everything else is passed to the house renderer unchanged.

import re
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether, PageBreak

import build_lease_docs as house
from build_burton_lease import BDIR, version_of, check_glyphs, build

S = house.S
WIDTH = 6.8 * inch
CELL = ParagraphStyle('cell', parent=S['body'], fontSize=8.3, leading=11.6, spaceAfter=0)
CELL_R = ParagraphStyle('cellr', parent=CELL, alignment=TA_RIGHT)
HEAD = ParagraphStyle('head', fontName='Jost-Medium', fontSize=7.6, leading=10.5, textColor=house.INK)
HEAD_R = ParagraphStyle('headr', parent=HEAD, alignment=TA_RIGHT)
NOTE = ParagraphStyle('note', fontName='Jost-Medium', fontSize=7.2, leading=10, textColor=house.MUTE)


def ruled_lines(n, label=None):
    out = [Spacer(1, 4)]
    if label:
        out.append(Paragraph(house.tracked(label), NOTE))
    for _ in range(n):
        out.append(Spacer(1, 21))
        out.append(HRFlowable(width='100%', thickness=0.5, color=house.LINE))
    out.append(Spacer(1, 8))
    return [KeepTogether(out)]


def table(rows):
    cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows]
    header, align, body = cells[0], cells[1], cells[2:]
    right = [a.endswith(':') for a in align]
    ncol = len(header)
    # Column widths from content length: numbers stay narrow, prose gets room.
    def weight(j):
        longest = max(len(re.sub(r'\*', '', r[j])) for r in [header] + body)
        return max(longest, 9) ** 0.72
    w = [weight(j) for j in range(ncol)]
    widths = [WIDTH * x / sum(w) for x in w]
    data = [[Paragraph(house.inline(h).upper(), HEAD_R if right[j] else HEAD)
             for j, h in enumerate(header)]]
    for r in body:
        data.append([Paragraph(house.inline(c), CELL_R if right[j] else CELL)
                     for j, c in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [('VALIGN', (0, 0), (-1, -1), 'TOP'),
             ('LINEBELOW', (0, 0), (-1, 0), 0.9, house.RUST),
             ('LINEBELOW', (0, 1), (-1, -1), 0.4, house.LINE),
             ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
             ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]
    for i, r in enumerate(body, start=1):
        if re.match(r'\*\*[^*]*total', r[0], re.I):       # total rows get a tint
            style.append(('BACKGROUND', (0, i), (-1, i), house.FIELDBG))
    t.setStyle(TableStyle(style))
    block = [Spacer(1, 2), t, Spacer(1, 9)]
    return [KeepTogether(block)] if len(body) <= 14 else block


def story(md):
    out, buf = [], []
    def flush():
        if buf:
            out.extend(house.md_to_story('\n'.join(buf))); buf.clear()
    lines = md.split('\n')
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = re.fullmatch(r'\[\[(notes|lines):(\d+)\]\]', s)
        if m:
            flush()
            out.extend(ruled_lines(int(m.group(2)), 'Notes' if m.group(1) == 'notes' else None))
            i += 1; continue
        if s == '[[pagebreak]]':
            flush(); out.append(PageBreak()); i += 1; continue
        if s.startswith('|'):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append(lines[i]); i += 1
            out.extend(table(rows)); continue
        buf.append(lines[i]); i += 1
    flush()
    return out


if __name__ == '__main__':
    with open(BDIR + '/prospectus.md') as f:
        md = f.read()
    check_glyphs(md)
    ver = version_of(md)
    build(story(md), BDIR + '/prospectus.pdf',
          'The Burton Inn — Rent Basis & Owner Return',
          f'The Burton Inn — Rent Basis & Owner Return    {ver}')
