#!/usr/bin/env python3
# Build the Burton Inn projected operating budget (burton-inn/operating-budget.pdf):
# one page, laid out like the Courthouse Square "Exhibit D - Estimated Budget
# Allocations - Tier One" sheet (summary box on top, boxed ledger below, three
# allocation columns), so the owner can read it the same way.
#
# Figures come from the Google Sheet "Financial Projections for Burton Inn -
# Rev 70% (for Tom)" (Inputs and Assumptions tab, as of November 13, 2026).
# Change the INPUTS below and rebuild; every other number is calculated.

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = ROOT + '/burton-inn/operating-budget.pdf'
STAMP = 'eb20261113'

# ---------------- INPUTS (from the projections workbook) ----------------
ROOMS, DAYS, OCC, ADR, ALOS = 4, 365, 0.70, 195, 2.5
OTA_SHARE, OTA_RATE = 0.75, 0.15
REV_DINNERS = 150 * 35 * 2 * 0.85 * 12          # ticket x seats x dinners/mo x fill x 12
REV_BAR = 4 * 50 * 30 * 35                      # nights/wk x weeks x guests x check
REV_BREAKFAST = 4 * 50 * 50 * 13                # mornings/wk x weeks x transactions x ticket
REV_COMMISSARY = 50 * 5 * 50                    # rate x hours/wk x weeks
REV_MISC = 1000 * 12 + 500                      # private events + misc
TAXES, BLDG_INS, MAINT_MO = 8500, 6500, 375
HOUSEKEEPER_HR, HRS_PER_TURN, AMENITIES, LINEN_PER_TURN = 35, 1.5, 6, 20
FNB_COGS, FNB_LABOR = 0.30, 0.32
UTIL_MO, BIZ_INS_MO, SEPTIC, SOFTWARE_MO = 2750, 2000, 3000, 500
CARD_FEE, RESERVE, TIER_TWO = 0.03, 0.03, 0.10

# ---------------- calculations ----------------
nights = ROOMS * DAYS * OCC
turns = nights / ALOS
rev_rooms = nights * ADR
rev_fnb_base = REV_DINNERS + REV_BAR + REV_BREAKFAST + REV_MISC     # COGS/labor base
rev_fnb = rev_fnb_base + REV_COMMISSARY
rev = rev_rooms + rev_fnb

# (label, shared, rooms, food & beverage)
SECTIONS = [
    ('Property Costs - Tier One', [
        ('Real estate taxes (actual) **', TAXES, 0, 0),
        ('Building insurance **', BLDG_INS, 0, 0),
        ('Routine maintenance and upkeep **', MAINT_MO * 12, 0, 0),
    ], 'Total Property Costs'),
    ('Utilities', [
        ('Power, water, garbage, internet *', UTIL_MO * 12, 0, 0),
        ('Septic service ***', SEPTIC, 0, 0),
    ], 'Total Utilities'),
    ('Operational Expenses', [
        ('Housekeeping labor', 0, turns * HOUSEKEEPER_HR * HRS_PER_TURN, 0),
        ('Laundry and linens', 0, turns * LINEN_PER_TURN, 0),
        ('Room amenities', 0, nights * AMENITIES, 0),
        ('Booking platform commissions', 0, rev_rooms * OTA_SHARE * OTA_RATE, 0),
        ('Food and beverage cost of goods', 0, 0, rev_fnb_base * FNB_COGS),
        ('Kitchen, bar and counter labor', 0, 0, rev_fnb_base * FNB_LABOR),
        ('Credit card fees', 0, rev_rooms * CARD_FEE, rev_fnb * CARD_FEE),
        ('Business insurance and licenses', BIZ_INS_MO * 12, 0, 0),
        ('Software, POS and marketing', SOFTWARE_MO * 12, 0, 0),
    ], 'Total Operational Expenses'),
]
reserve = rev * RESERVE
rent = rev * TIER_TWO

def money(x, dash=True):
    return '-' if (dash and abs(x) < 0.005) else f'{x:,.2f}'
def pct(x):
    return f'{x * 100:.1f}%'

sec_tot = [[sum(r[i] for r in rows) for i in (1, 2, 3)] for _, rows, _ in SECTIONS]
col_tot = [sum(s[i] for s in sec_tot) for i in range(3)]
col_tot[0] += reserve
budget = sum(col_tot)

# ---------------- styles ----------------
GRAY = colors.Color(0.30, 0.30, 0.30)
FN, FB = 'Helvetica', 'Helvetica-Bold'
def P(text, font=FB, size=8, align=TA_LEFT, color=colors.black):
    return Paragraph(text, ParagraphStyle('p', fontName=font, fontSize=size, leading=size + 2,
                                          alignment=align, textColor=color))
W = [12, 60, 38, 200, 12, 50, 12, 50, 12, 50]      # ledger columns (496 pt)

# ---------------- summary box ----------------
def summary():
    cw = [110, 200, 62, 62, 62]
    d = [
        [P('OPERATING', size=7.5, align=TA_CENTER, color=GRAY), P('<i>"THE BURTON INN"</i>, VASHON ISLAND', align=TA_RIGHT, color=GRAY),
         P('SHARED', align=TA_CENTER, color=GRAY), P('INN ROOMS', align=TA_CENTER, color=GRAY), P('FOOD &amp; BEV', align=TA_CENTER, color=GRAY)],
        [P('ESTIMATED TOTALS', size=7.5, align=TA_CENTER, color=GRAY), P('SHARE OF REVENUE', align=TA_RIGHT, color=GRAY),
         P('100.0%', align=TA_CENTER, color=GRAY), P(pct(rev_rooms / rev), align=TA_CENTER, color=GRAY), P(pct(rev_fnb / rev), align=TA_CENTER, color=GRAY)],
        [P('STABILIZED YEAR', size=7.5, align=TA_CENTER, color=GRAY), P('PROJECTED GROSS REVENUE', align=TA_RIGHT, color=GRAY),
         P(f'${rev:,.0f}', align=TA_CENTER, color=GRAY), P(f'${rev_rooms:,.0f}', align=TA_CENTER, color=GRAY), P(f'${rev_fnb:,.0f}', align=TA_CENTER, color=GRAY)],
        [P(f'${budget:,.2f}', color=GRAY), P('ANNUAL BUDGET SUMMARY', align=TA_RIGHT, color=GRAY)] +
        [P(f'${c:,.2f}', align=TA_CENTER, color=GRAY) for c in col_tot],
        [P(f'${budget / 12:,.2f}', color=GRAY), P('MONTHLY ALLOCATION', align=TA_RIGHT, color=GRAY)] +
        [P(f'${c / 12:,.2f}', align=TA_CENTER, color=GRAY) for c in col_tot],
        ['', P('COST AS % OF REVENUE', align=TA_RIGHT, color=GRAY),
         P(pct(col_tot[0] / rev), align=TA_CENTER, color=GRAY), P(pct(col_tot[1] / rev_rooms), align=TA_CENTER, color=GRAY),
         P(pct(col_tot[2] / rev_fnb), align=TA_CENTER, color=GRAY)],
    ]
    t = Table(d, colWidths=cw, rowHeights=[15] * 6)
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
        ('LINEBELOW', (0, 2), (-1, 2), 0.9, colors.black),
        ('LINEBELOW', (2, 4), (-1, 4), 0.6, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return t

# ---------------- ledger ----------------
def ledger():
    d, st = [], []
    def cells(vals, bold=False):
        f = FB if bold else FN
        out = []
        for v in vals:
            out += [P('$', f, 8), P(money(v), f, 8, TA_RIGHT)]
        return out
    def add(row, grid=True):
        d.append(row); i = len(d) - 1
        if grid:
            st.append(('GRID', (0, i), (-1, i), 0.5, colors.black))
        return i
    i = add(['', '', '', P('ANNUAL BUDGET DETAILS', size=7.5, align=TA_RIGHT, color=GRAY),
             P('SHARED', size=7.5, align=TA_CENTER, color=GRAY), '', P('INN ROOMS', size=7.5, align=TA_CENTER, color=GRAY), '',
             P('FOOD &amp; BEV', size=7.5, align=TA_CENTER, color=GRAY), ''], grid=False)
    st += [('SPAN', (0, i), (2, i)), ('SPAN', (4, i), (5, i)), ('SPAN', (6, i), (7, i)), ('SPAN', (8, i), (9, i)),
           ('LINEBELOW', (0, i), (-1, i), 0.9, colors.black)]
    for (title, rows, total_label), tot in zip(SECTIONS, sec_tot):
        s = sum(tot)
        i = add(['', '', P(pct(s / budget), FB, 8.5, TA_RIGHT), P(title, FB, 8.5)] + [''] * 6, grid=False)
        st += [('SPAN', (0, i), (1, i)), ('SPAN', (3, i), (9, i)), ('LINEBELOW', (0, i), (-1, i), 0.9, colors.black)]
        for label, a, b, c in rows:
            line = a + b + c
            add([P('$', FN, 8), P(money(line), FN, 8, TA_RIGHT), P(pct(line / s), FN, 8, TA_RIGHT), P(label, FN, 8.5)] + cells([a, b, c]))
        i = add([P('$', FB, 8), P(money(s), FB, 8, TA_RIGHT), P('100.0%', FB, 8, TA_RIGHT), P(total_label, FB, 8, TA_RIGHT)] + cells(tot, True))
        st.append(('LINEABOVE', (0, i), (-1, i), 0.9, colors.black))
        i = add([''] * 10, grid=False)
        st.append(('LINEBELOW', (0, i), (-1, i), 0.9, colors.black))
    add([P('$', FB, 8), P(money(reserve), FB, 8, TA_RIGHT), P(pct(reserve / budget), FB, 8, TA_RIGHT),
         P('3% Repair and Replacement Reserve', FB, 8.5, TA_RIGHT)] + cells([reserve, 0, 0], True))
    add([''] * 10)
    i = add([P('$', FB, 8), P(money(budget), FB, 8, TA_RIGHT), P('100.0%', FB, 8, TA_RIGHT),
             P('TOTAL ANNUAL OPERATING BUDGET', FB, 8, TA_CENTER)] +
            [x for c in col_tot for x in (P(f'${c:,.2f}', FB, 8, TA_CENTER), '')])
    st += [('SPAN', (4, i), (5, i)), ('SPAN', (6, i), (7, i)), ('SPAN', (8, i), (9, i)),
           ('LINEABOVE', (0, i), (-1, i), 1.2, colors.black)]
    t = Table(d, colWidths=W, rowHeights=[14] * len(d))
    t.setStyle(TableStyle(st + [
        ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return t

# ---------------- rent and result ----------------
def result():
    total = budget + rent
    rows = [('Tier Two rent to owner (10% of gross revenue)', rent, False),
            ('TOTAL COST INCLUDING RENT', total, True),
            ('PROJECTED GROSS REVENUE', rev, True),
            ('NET AFTER ALL COSTS', rev - total, True)]
    d = [['', '', P('% REV.', size=7, align=TA_RIGHT, color=GRAY), P('RENT AND RESULT', size=7.5, align=TA_RIGHT, color=GRAY)]]
    for label, v, bold in rows:
        f = FB if bold else FN
        d.append([P('$', f, 8), P(money(v), f, 8, TA_RIGHT), P(pct(v / rev), f, 8, TA_RIGHT),
                  P(label, f, 8.5 if not bold else 8, TA_RIGHT if bold else TA_LEFT)])
    t = Table(d, colWidths=W[:4], rowHeights=[14] * len(d), hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.2, colors.black), ('GRID', (0, 1), (-1, -1), 0.5, colors.black),
        ('SPAN', (0, 0), (1, 0)), ('LINEBELOW', (0, 0), (-1, 0), 0.9, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return t

def footer(canvas, doc):
    canvas.setFont(FN, 8.5)
    canvas.drawString(40, 34, 'Burton Inn - Projected Operating Budget')

if __name__ == '__main__':
    doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=52, rightMargin=52, topMargin=52, bottomMargin=50,
                            title='The Burton Inn - Projected Annual Operating Budget')
    note = lambda s: P(s, FB, 8, TA_LEFT)
    story = [
        P('THE BURTON INN', FB, 12.5, TA_CENTER, GRAY), Spacer(1, 4),
        P('PROJECTED ANNUAL OPERATING BUDGET - STABILIZED YEAR', FB, 12.5, TA_CENTER, GRAY), Spacer(1, 3),
        P(STAMP, FB, 7, TA_RIGHT), Spacer(1, 1),
        summary(), Spacer(1, 12), ledger(), Spacer(1, 10), result(), Spacer(1, 10),
        note('* Billed to tenant; copies to owner'),
        note('** Tier One: paid by tenant at actual cost'),
        note('*** Placeholder until the septic service contract is quoted'),
        note(f'Stabilized year: {OCC:.0%} occupancy at ${ADR} a night. Year 1 is projected at 75% and Year 2 at 90% of stabilized revenue.'),
    ]
    for f in story:
        if isinstance(f, Table) and f.hAlign != 'LEFT':
            f.hAlign = 'CENTER'
    doc.build(story, onFirstPage=footer)
    print('wrote', OUT)
    print(f'revenue {rev:,.2f} rooms {rev_rooms:,.2f} fnb {rev_fnb:,.2f} budget {budget:,.2f} '
          f'rent {rent:,.2f} net {rev - budget - rent:,.2f}')
