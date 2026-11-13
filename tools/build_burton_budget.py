#!/usr/bin/env python3
# Build the Burton Inn Exhibit D (burton-inn/operating-budget.pdf).
#   Page 1: projected annual operating budget for the stabilized target year,
#           laid out like the Courthouse Square "Exhibit D - Estimated Budget
#           Allocations - Tier One" sheet (summary box, boxed ledger, three
#           allocation columns).
#   Page 2: the same lines for Year 1 (kitchen opens mid-year), rooms only,
#           the conservative floor, and the target, with rent and what is left.
#
# Revenue assumptions are the prospectus cases. Cost rates come from the Google
# Sheet "Financial Projections for Burton Inn - Rev 70% (for Tom)". Upkeep and
# utility lines are low estimates (no bills or quotes yet; the tenant does most
# upkeep labor). Change the INPUTS and rebuild; every other number is
# calculated. The prospectus numbers are derived from model() too, and the same
# inputs are in the Google Sheet "Burton Inn - Exhibit D - Projected Operating
# Budget" (Assumptions tab).

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = ROOT + '/burton-inn/operating-budget.pdf'
STAMP = 'eb20261113'

# ---------------- INPUTS ----------------
CASES = {
    'target': dict(occ=0.50, adr=215,
                   bar=18 * 38 * 4 * 42,            # covers x check x nights/wk x weeks
                   dinners=150 * 35 * 24 * 0.85,    # ticket x seats x dinners a year x share sold
                   breakfast=40 * 10 * 4 * 42,      # sales x average sale x mornings/wk x weeks
                   commissary=50 * 5 * 50,          # rate x hours/wk x weeks
                   misc=7000),
    'floor':  dict(occ=0.36, adr=210,
                   bar=12.5 * 38 * 4 * 42,
                   dinners=150 * 35 * 16 * 0.55,
                   breakfast=20 * 9 * 4 * 42,
                   commissary=32 * 2 * 50,
                   misc=6820),
}
ROOMS, DAYS, ALOS = 4, 365, 2.5
OTA_SHARE, OTA_RATE = 0.75, 0.15
PROPERTY = [                                        # Tier One: paid by tenant at actual cost
    ('Real estate taxes (actual) **', 8500),
    ('Building insurance **', 6500),
    ('Cleaning and maintenance **', 1200),
    ('Fire and safety **', 600),
    ('HVAC maintenance and repairs **', 900),
    ('Landscaping and grounds **', 600),
    ('Repairs - general **', 1200),
]
UTILITIES = [
    ('Electricity *', 21000),
    ('Natural gas (water heater) *', 1800),
    ('Water *', 3600),
    ('Garbage *', 2400),
    ('Recycling *', 1200),
    ('Internet and phone *', 3000),
    ('Pest control', 1200),
]
HOUSEKEEPER_HR, HRS_PER_TURN, AMENITIES, LINEN_PER_TURN = 35, 1.5, 6, 20
FNB_COGS, FNB_LABOR = 0.30, 0.32
BIZ_INS, SOFTWARE = 24000, 6000
CARD_FEE, CONTINGENCY, TIER_TWO, TIER_TWO_MIN = 0.03, 0.10, 0.10, 19800
YEAR1_ROOMS, YEAR1_FNB = 0.75, 0.375                # staged opening: rooms 75%; kitchen and bar 75% x 6/12
RAMP = [None, 0.90, 1.00, 1.03, 1.03 ** 2]          # Lease Years 2-5 as a share of a stabilized year

# ---------------- calculations ----------------
def model(case, year1=False, rooms_only=False):
    """Revenue, every budget line (shared, rooms, food & beverage), and totals for one case.
    year1: staged opening, no rent minimum. rooms_only: the kitchen and bar never open."""
    c = CASES[case]
    rs, fs = (YEAR1_ROOMS, YEAR1_FNB) if year1 else (1, 0) if rooms_only else (1, 1)
    nights = ROOMS * DAYS * c['occ'] * rs
    turns = nights / ALOS
    m = {k: v * fs for k, v in c.items() if k in ('bar', 'dinners', 'breakfast', 'commissary', 'misc')}
    m.update(occ=c['occ'], adr=c['adr'], nights=nights, turns=turns)
    m['rev_rooms'] = nights * c['adr']
    m['fnb_base'] = m['dinners'] + m['bar'] + m['breakfast'] + m['misc']      # cost of goods / labor base
    m['rev_fnb'] = m['fnb_base'] + m['commissary']
    m['rev'] = m['rev_rooms'] + m['rev_fnb']
    m['sections'] = [
        ('Property Costs - Tier One', [(l, a, 0, 0) for l, a in PROPERTY], 'Total Property Costs'),
        ('Utilities', [(l, a, 0, 0) for l, a in UTILITIES], 'Total Utilities'),
        ('Operational Expenses', [
            ('Housekeeping labor', 0, turns * HOUSEKEEPER_HR * HRS_PER_TURN, 0),
            ('Laundry and linens', 0, turns * LINEN_PER_TURN, 0),
            ('Room amenities', 0, nights * AMENITIES, 0),
            ('Booking platform commissions', 0, m['rev_rooms'] * OTA_SHARE * OTA_RATE, 0),
            ('Food and beverage cost of goods', 0, 0, m['fnb_base'] * FNB_COGS),
            ('Kitchen, bar and counter labor', 0, 0, m['fnb_base'] * FNB_LABOR),
            ('Credit card fees', 0, m['rev_rooms'] * CARD_FEE, m['rev_fnb'] * CARD_FEE),
            ('Business insurance and licenses', BIZ_INS, 0, 0),
            ('Software, POS and marketing', SOFTWARE, 0, 0),
        ], 'Total Operational Expenses'),
    ]
    m['sec_tot'] = [[sum(r[i] for r in rows) for i in (1, 2, 3)] for _, rows, _ in m['sections']]
    sub = [sum(s[i] for s in m['sec_tot']) for i in range(3)]
    m['contingency'] = [x * CONTINGENCY for x in sub]
    m['col_tot'] = [sub[i] + m['contingency'][i] for i in range(3)]
    m['budget'] = sum(m['col_tot'])
    m['tier_one'] = sum(m['sec_tot'][0])
    m['opex'] = m['budget'] - m['tier_one']           # operating costs before occupancy cost
    m['tier_two'] = m['rev'] * TIER_TWO if year1 else max(TIER_TWO_MIN, m['rev'] * TIER_TWO)
    m['net'] = m['rev'] - m['budget'] - m['tier_two']
    return m

# ---------------- styles ----------------
GRAY = colors.Color(0.30, 0.30, 0.30)
FN, FB = 'Helvetica', 'Helvetica-Bold'
RH = 12.6                                           # ledger row height
def P(text, font=FB, size=8, align=TA_LEFT, color=colors.black):
    return Paragraph(text, ParagraphStyle('p', fontName=font, fontSize=size, leading=size + 2,
                                          alignment=align, textColor=color))
def money(x, dash=True):
    if dash and abs(x) < 0.005:
        return '-'
    return f'({-x:,.2f})' if x < 0 else f'{x:,.2f}'
def pct(x):
    return f'{x * 100:.1f}%'
PAD = [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
       ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
       ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]
W = [12, 60, 38, 200, 12, 50, 12, 50, 12, 50]       # page 1 ledger columns (496 pt)

# ---------------- page 1: summary box ----------------
def summary(m):
    g = lambda t, a=TA_CENTER, s=8: P(t, size=s, align=a, color=GRAY)
    rev, rr, rf, ct, budget = m['rev'], m['rev_rooms'], m['rev_fnb'], m['col_tot'], m['budget']
    d = [
        [g('OPERATING', s=7.5), g('<i>"THE BURTON INN"</i>, VASHON ISLAND', TA_RIGHT), g('SHARED'), g('INN ROOMS'), g('FOOD &amp; BEV')],
        [g('ESTIMATED TOTALS', s=7.5), g('SHARE OF REVENUE', TA_RIGHT), g('100.0%'), g(pct(rr / rev)), g(pct(rf / rev))],
        [g('STABILIZED YEAR', s=7.5), g('PROJECTED GROSS REVENUE', TA_RIGHT), g(f'${rev:,.0f}'), g(f'${rr:,.0f}'), g(f'${rf:,.0f}')],
        [g(f'${budget:,.2f}', TA_LEFT), g('ANNUAL BUDGET SUMMARY', TA_RIGHT)] + [g(f'${c:,.2f}') for c in ct],
        [g(f'${budget / 12:,.2f}', TA_LEFT), g('MONTHLY ALLOCATION', TA_RIGHT)] + [g(f'${c / 12:,.2f}') for c in ct],
        ['', g('COST AS % OF REVENUE', TA_RIGHT), g(pct(ct[0] / rev)), g(pct(ct[1] / rr)), g(pct(ct[2] / rf))],
    ]
    t = Table(d, colWidths=[110, 200, 62, 62, 62], rowHeights=[14.5] * 6)
    t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 1.2, colors.black),
                           ('LINEBELOW', (0, 2), (-1, 2), 0.9, colors.black),
                           ('LINEBELOW', (2, 4), (-1, 4), 0.6, colors.black),
                           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                           ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    return t

# ---------------- page 1: ledger ----------------
def ledger(m):
    d, st = [], []
    budget = m['budget']
    def cells(vals, bold=False):
        f = FB if bold else FN
        return [x for v in vals for x in (P('$', f, 8), P(money(v), f, 8, TA_RIGHT))]
    def add(row, grid=True):
        d.append(row); i = len(d) - 1
        if grid:
            st.append(('GRID', (0, i), (-1, i), 0.5, colors.black))
        return i
    hdr = lambda t: P(t, size=7.5, align=TA_CENTER, color=GRAY)
    i = add(['', '', '', P('ANNUAL BUDGET DETAILS', size=7.5, align=TA_RIGHT, color=GRAY),
             hdr('SHARED'), '', hdr('INN ROOMS'), '', hdr('FOOD &amp; BEV'), ''], grid=False)
    st += [('SPAN', (0, i), (2, i)), ('SPAN', (4, i), (5, i)), ('SPAN', (6, i), (7, i)), ('SPAN', (8, i), (9, i)),
           ('LINEBELOW', (0, i), (-1, i), 0.9, colors.black)]
    for (title, rows, total_label), tot in zip(m['sections'], m['sec_tot']):
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
    cont = sum(m['contingency'])
    add([P('$', FB, 8), P(money(cont), FB, 8, TA_RIGHT), P(pct(cont / budget), FB, 8, TA_RIGHT),
         P('10% Contingency Reserve', FB, 8.5, TA_RIGHT)] + cells(m['contingency'], True))
    add([''] * 10)
    i = add([P('$', FB, 8), P(money(budget), FB, 8, TA_RIGHT), P('100.0%', FB, 8, TA_RIGHT),
             P('TOTAL ANNUAL OPERATING BUDGET', FB, 8, TA_CENTER)] +
            [x for c in m['col_tot'] for x in (P(f'${c:,.2f}', FB, 8, TA_CENTER), '')])
    st += [('SPAN', (4, i), (5, i)), ('SPAN', (6, i), (7, i)), ('SPAN', (8, i), (9, i)),
           ('LINEABOVE', (0, i), (-1, i), 1.2, colors.black)]
    t = Table(d, colWidths=W, rowHeights=[RH] * len(d))
    t.setStyle(TableStyle(st + [('BOX', (0, 0), (-1, -1), 1.2, colors.black)] + PAD))
    return t

# ---------------- page 2: Year 1, floor, target ----------------
def cases_table(ms):
    """ms = [year 1, rooms only, floor, target] models. One column each."""
    d, st = [], []
    n = len(ms)
    WC = [190] + [12, 64.5] * n
    def row(label, vals, bold=False, fmt=money, grid=True, align=TA_LEFT):
        f = FB if bold else FN
        r = [P(label, f, 8.5, align)]
        for v in vals:
            r += [P('$' if fmt is money else '', f, 8), P(fmt(v), f, 8, TA_RIGHT)]
        d.append(r); i = len(d) - 1
        if grid:
            st.append(('GRID', (0, i), (-1, i), 0.5, colors.black))
        return i
    def head(title):
        d.append([P(title, FB, 8.5)] + [''] * (2 * n)); i = len(d) - 1
        st.extend([('SPAN', (0, i), (-1, i)), ('LINEBELOW', (0, i), (-1, i), 0.9, colors.black),
                   ('LINEABOVE', (0, i), (-1, i), 0.9, colors.black)])
    hdr = lambda t: P(t, size=7.5, align=TA_CENTER, color=GRAY)
    d.append([P('ANNUAL BUDGET BY CASE', size=7.5, align=TA_RIGHT, color=GRAY),
              hdr('YEAR 1<br/>(kitchen mid-year)'), '', hdr('ROOMS ONLY<br/>(no kitchen)'), '',
              hdr('FLOOR<br/>(stabilized)'), '', hdr('TARGET<br/>(stabilized)'), ''])
    st += [('SPAN', (2 * k + 1, 0), (2 * k + 2, 0)) for k in range(n)]
    head('Projected Revenue')
    row('Inn rooms', [m['rev_rooms'] for m in ms])
    row('Food and beverage', [m['rev_fnb'] for m in ms])
    row('Projected Gross Revenue', [m['rev'] for m in ms], True, align=TA_RIGHT)
    for k, (title, rows, total_label) in enumerate(ms[0]['sections']):
        head(title)
        for j, r in enumerate(rows):
            row(r[0], [sum(m['sections'][k][1][j][1:]) for m in ms])
        row(total_label, [sum(m['sec_tot'][k]) for m in ms], True, align=TA_RIGHT)
    head('Budget, Rent and Result')
    row('10% Contingency Reserve', [sum(m['contingency']) for m in ms])
    row('TOTAL ANNUAL OPERATING BUDGET', [m['budget'] for m in ms], True, align=TA_RIGHT)
    row('Tier Two rent to owner ****', [m['tier_two'] for m in ms])
    row('TOTAL COST INCLUDING RENT', [m['budget'] + m['tier_two'] for m in ms], True, align=TA_RIGHT)
    row('NET AFTER ALL COSTS', [m['net'] for m in ms], True, align=TA_RIGHT)
    row('Rent and property costs as a share of revenue', [(m['tier_two'] + m['tier_one']) / m['rev'] for m in ms], fmt=pct)
    t = Table(d, colWidths=WC, rowHeights=[22] + [RH] * (len(d) - 1))
    t.setStyle(TableStyle(st + [('BOX', (0, 0), (-1, -1), 1.2, colors.black),
                                ('LINEBELOW', (0, 0), (-1, 0), 0.9, colors.black)] + PAD))
    return t

def footer(canvas, doc):
    canvas.setFont(FN, 8.5)
    canvas.drawString(40, 30, f'Burton Inn Exhibit D - Projected Operating Budget - page {doc.page} of 2')

if __name__ == '__main__':
    T, F, Y1, RO = model('target'), model('floor'), model('target', year1=True), model('target', rooms_only=True)
    doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=52, rightMargin=52, topMargin=46, bottomMargin=46,
                            title='The Burton Inn - Exhibit D - Projected Annual Operating Budget')
    note = lambda s: P(s, FB, 7.6, TA_LEFT)
    title = lambda s, sz: P(s, FB, sz, TA_CENTER, GRAY)
    story = [
        title('THE BURTON INN', 12.5), Spacer(1, 4),
        title('EXHIBIT D - PROJECTED ANNUAL OPERATING BUDGET - STABILIZED YEAR', 11.5), Spacer(1, 3),
        P(STAMP, FB, 7, TA_RIGHT), Spacer(1, 1),
        summary(T), Spacer(1, 10), ledger(T), Spacer(1, 8),
        note('* Billed to tenant; copies to owner'),
        note('** Tier One: paid by tenant at actual cost'),
        note('Utility and upkeep figures are estimates until bills and quotes are in. Most upkeep labor is done by the tenant.'),
        note(f"Stabilized year at the target case: {T['occ']:.0%} occupancy at ${T['adr']} a night. Year 1 and the floor case are on page 2."),
        PageBreak(),
        title('THE BURTON INN', 12.5), Spacer(1, 4),
        title('EXHIBIT D - YEAR 1, ROOMS ONLY, FLOOR AND TARGET', 11.5), Spacer(1, 12),
        cases_table([Y1, RO, F, T]), Spacer(1, 8),
        note('Year 1: target case with a staged opening. Rooms reach 75% of a stabilized year; the kitchen and bar open halfway through the year.'),
        note('Rooms only: target-case rooms for a full year with the kitchen and bar not open.'),
        note(f"Floor: {F['occ']:.0%} occupancy at ${F['adr']} a night, with a slower bar, fewer dinners and half the breakfast trade."),
        note('Fixed costs are shown for a full year in every case.'),
        note('**** 10% of gross revenue. No minimum in Lease Year 1; from 2028, not less than $19,800 a year. Before the $70,000 rent advance is credited.'),
    ]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print('wrote', OUT)
    for name, m in (('year1', Y1), ('rooms only', RO), ('floor', F), ('target', T)):
        print(f"{name}: rev {m['rev']:,.0f} budget {m['budget']:,.2f} rent {m['tier_two']:,.2f} net {m['net']:,.2f} "
              f"cov {(m['rev'] - m['opex']) / (m['tier_two'] + m['tier_one']):.2f}")
