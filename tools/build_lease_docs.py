#!/usr/bin/env python3
# Build the Courthouse Square lease document set (Version 1.2, 2026-06-08):
#   - lease/lease.pdf                  Standard Lease Terms + Definitions (public)
#   - lease/lease-terms-sheet.pdf      Fillable Lease Terms Sheet example (public)
#   - review/letter-of-intent.pdf      Letter of Intent (internal)
#   - review/CourthouseSquare_FullLease_v2026.06.08.pdf  Consolidated, all parts (internal, for deep review)
#
# Pure reportlab + pypdf (no system deps). Absolute paths only (no getcwd).

import re, html
from reportlab import rl_config
# Deterministic output: fixed timestamps and document IDs so rebuilding without
# content changes produces byte-identical PDFs (keeps git diffs honest).
rl_config.invariant = 1
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
                                Table, TableStyle, Flowable, KeepTogether, PageBreak)
from reportlab.pdfgen import canvas as canvaslib
# pypdf is imported lazily inside merge(): only the consolidated review PDF needs
# it, so generating the fillable forms never depends on it being installed.

import os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW = ROOT + '/review'

# Single source of truth for entity/address/version: data/identity.json.
# The whole document set moved to one version track at v1.5 (JMS redlines,
# June 29, 2026); the temporary v1.2/v1.3 split is over.
with open(ROOT + '/data/identity.json') as _f:
    IDENT = json.load(_f)
VERSION = IDENT['version']
VDATE   = IDENT['versionDate']
FOOTER  = f"{IDENT['entity']}    {VERSION}, {VDATE}"

# Aliases kept so the form-builder code reads naturally.
FORM_ENTITY  = IDENT['entity']
FORM_ADDR    = IDENT['buildingAddress']
NOTICE_ADDR  = IDENT['noticeAddress']
NOTICE_CO    = IDENT['noticeCareOf']
FORM_VERSION = VERSION
FORM_VDATE   = VDATE
FORM_FOOTER  = FOOTER

INK   = HexColor(0x1e3128)
INK2  = HexColor(0x243b2f)
MUTE  = HexColor(0x4a443b)
LINE  = HexColor(0xbcd0c2)
RUST  = HexColor(0xb4521f)
FIELDBG = HexColor(0xf7f3ea)

# ---------------- typefaces ----------------
# Midcentury pairing: Jost (a Futura revival) for display/labels, Libre
# Baskerville for body text — the classic 1960s agency combination. The TTFs
# live in /fonts and are shared with the in-browser Lease Builder.
FONTS = ROOT + '/fonts'
pdfmetrics.registerFont(TTFont('Jost',        FONTS + '/Jost-400.ttf'))
pdfmetrics.registerFont(TTFont('Jost-Medium', FONTS + '/Jost-500.ttf'))
pdfmetrics.registerFont(TTFont('Jost-Semi',   FONTS + '/Jost-600.ttf'))
pdfmetrics.registerFont(TTFont('Baskerville',        FONTS + '/LibreBaskerville-400.ttf'))
pdfmetrics.registerFont(TTFont('Baskerville-Bold',   FONTS + '/LibreBaskerville-700.ttf'))
pdfmetrics.registerFont(TTFont('Baskerville-Italic', FONTS + '/LibreBaskerville-Italic.ttf'))
# Make <b>/<i> inside Paragraphs resolve to the right cuts.
addMapping('Baskerville', 0, 0, 'Baskerville')
addMapping('Baskerville', 1, 0, 'Baskerville-Bold')
addMapping('Baskerville', 0, 1, 'Baskerville-Italic')
addMapping('Baskerville', 1, 1, 'Baskerville-Bold')

def tracked(s):
    """Letterspaced caps for display type: 'LEASE' -> 'L E A S E'.
    Non-breaking spaces so Paragraph doesn't collapse the tracking."""
    NB = '\u00a0'  # non-breaking space
    return (NB.join(list(s.upper().replace(' ', '~')))).replace(NB + '~' + NB, NB * 3)

# ---------------- styles (midcentury: Jost display / Baskerville text) ----------------
def styles():
    out = {}
    # Document title: big letterspaced Futura-style caps.
    out['title']   = ParagraphStyle('t', fontName='Jost-Semi', fontSize=23, textColor=INK,
                                    spaceAfter=6, leading=28, alignment=TA_LEFT)
    # Metadata line under titles.
    out['sub']     = ParagraphStyle('sub', fontName='Jost', fontSize=9, textColor=MUTE,
                                    spaceAfter=2, leading=13)
    # Part heading (STANDARD LEASE TERMS / DEFINITIONS & GLOSSARY).
    out['h2']      = ParagraphStyle('h2', fontName='Jost-Semi', fontSize=15, textColor=INK,
                                    spaceBefore=22, spaceAfter=8, leading=19)
    # Article heading: rust index + tracked caps (assembled in md_to_story).
    out['h3']      = ParagraphStyle('h3', fontName='Jost-Medium', fontSize=11, textColor=INK2,
                                    spaceBefore=16, spaceAfter=5, leading=15)
    out['body']    = ParagraphStyle('body', fontName='Baskerville', fontSize=9.2, textColor=INK,
                                    spaceAfter=7, leading=14.5)
    out['bullet']  = ParagraphStyle('bullet', parent=out['body'], leftIndent=16, bulletIndent=4,
                                    spaceAfter=3, bulletColor=RUST)
    out['quote']   = ParagraphStyle('quote', fontName='Baskerville-Italic', fontSize=9.2, textColor=INK2,
                                    leftIndent=14, rightIndent=10, spaceBefore=4, spaceAfter=10, leading=14.5,
                                    borderColor=RUST, borderWidth=0, backColor=HexColor(0xf2f6f3),
                                    borderPadding=(6, 8, 6, 8))
    out['label']   = ParagraphStyle('label', fontName='Jost-Medium', fontSize=8.6, textColor=INK, leading=12.5)
    out['small']   = ParagraphStyle('small', fontName='Baskerville-Italic', fontSize=8, textColor=MUTE, leading=11.5)
    out['center']  = ParagraphStyle('center', parent=out['body'], alignment=TA_CENTER)
    return out
S = styles()

def dual_rule():
    """The midcentury double rule: a strong evergreen bar over a thin rust line."""
    return [Spacer(1, 5),
            HRFlowable(width='100%', thickness=2.2, color=INK, spaceAfter=2),
            HRFlowable(width='100%', thickness=0.7, color=RUST),
            Spacer(1, 8)]

def form_section(st, title):
    """Numbered form-section heading: rust index + tracked caps + thin rule.
    Titles arrive possibly pre-escaped; long titles skip tracking (NBSPs
    can't wrap, so tracked text must fit one line)."""
    plain = html.unescape(title)
    m = re.match(r'(\d+)\.\s*(.*)', plain)
    idx, rest = (m.group(1), m.group(2)) if m else (None, plain)
    disp = tracked(rest) if len(rest) <= 34 else rest.upper()
    markup = html.escape(disp, quote=False)
    if idx:
        markup = (f'<font color="#b4521f">{idx}</font>'
                  f'<font color="#bcd0c2">&nbsp;&#183;&nbsp;</font>' + markup)
    st.append(Spacer(1, 6))
    st.append(Paragraph(markup, S['h3']))
    st.append(HRFlowable(width='100%', thickness=0.5, color=LINE, spaceAfter=5))

def title_para(text):
    """Tracked display title (accepts pre-escaped text)."""
    return Paragraph(html.escape(tracked(html.unescape(text)), quote=False), S['title'])

def article_heading(text):
    """'Article 9: Default and Remedies' -> rust 'ARTICLE 9' + tracked title."""
    m = re.match(r'(Article \d+):\s*(.*)', text)
    if m:
        markup = (f'<font color="#b4521f">{tracked(m.group(1))}</font>'
                  f'<font color="#bcd0c2">&nbsp;&nbsp;|&nbsp;&nbsp;</font>{html.escape(m.group(2).upper(), quote=False)}')
        return Paragraph(markup, S['h3'])
    return Paragraph(html.escape(text.upper(), quote=False), S['h3'])

def inline(text):
    """Escape, then convert **bold** and *italic* to reportlab markup."""
    text = html.escape(text, quote=False)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    return text

def md_to_story(md):
    story = []
    lines = md.split('\n')
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s == '':
            i += 1; continue
        if s == '---':
            story.extend(dual_rule()); i += 1; continue
        if s.startswith('### '):
            story.append(article_heading(s[4:])); i += 1; continue
        if s.startswith('## '):
            story.append(Paragraph(html.escape(tracked(s[3:]), quote=False), S['h2']))
            story.append(HRFlowable(width='100%', thickness=0.7, color=RUST, spaceAfter=6))
            i += 1; continue
        if s.startswith('# '):
            story.append(Paragraph(html.escape(tracked(s[2:]), quote=False), S['title'])); i += 1; continue
        if s.startswith('> '):
            story.append(Paragraph(inline(s[2:]), S['quote'])); i += 1; continue
        if s.startswith('- '):
            items = []
            while i < len(lines) and lines[i].strip().startswith('- '):
                items.append(lines[i].strip()[2:]); i += 1
            for it in items:
                story.append(Paragraph(inline(it), S['bullet'], bulletText='•'))
            continue
        # plain paragraph (single line)
        story.append(Paragraph(inline(s), S['body'])); i += 1
    return story

# ---------------- numbered canvas (Page N of M + footer) ----------------
class NumberedCanvas(canvaslib.Canvas):
    footer_text = FOOTER   # overridden per-document via footer_canvas()
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._saved = []
    def showPage(self):
        self._saved.append(dict(self.__dict__)); self._startPage()
    def save(self):
        n = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st); self._draw_footer(n); super().showPage()
        super().save()
    def _draw_footer(self, total):
        w, _ = letter
        self.setStrokeColor(LINE); self.setLineWidth(0.5)
        self.line(0.85*inch, 0.62*inch, w - 0.85*inch, 0.62*inch)
        # Rust tick on the rule: a small midcentury signature.
        self.setStrokeColor(RUST); self.setLineWidth(1.4)
        self.line(0.85*inch, 0.62*inch, 0.85*inch + 18, 0.62*inch)
        self.setFont('Jost', 6.8); self.setFillColor(MUTE)
        t = self.beginText(0.85*inch, 0.5*inch)
        t.setCharSpace(0.7)
        t.textOut(getattr(self, 'footer_text', FOOTER).upper())
        self.drawText(t)
        pg = f'PAGE {self._pageNumber} OF {total}'
        # right-aligned with the same tracking
        width = pdfmetrics.stringWidth(pg, 'Jost', 6.8) + 0.7 * len(pg)
        t2 = self.beginText(w - 0.85*inch - width, 0.5*inch)
        t2.setCharSpace(0.7)
        t2.textOut(pg)
        self.drawText(t2)

def footer_canvas(footer):
    """A NumberedCanvas subclass that stamps a specific footer string."""
    return type('FooterCanvas', (NumberedCanvas,), {'footer_text': footer})

def build_prose(path, md):
    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=0.85*inch, rightMargin=0.85*inch,
                            topMargin=0.8*inch, bottomMargin=0.8*inch,
                            title='Courthouse Square LLC')
    doc.build(md_to_story(md), canvasmaker=NumberedCanvas)
    print('wrote', path)

# ---------------- fillable form pieces ----------------
class FieldBase(Flowable):
    _counter = [0]
    def __init__(self, name, width, height=15):
        super().__init__(); self.name=name; self.width=width; self.height=height
    def wrap(self, *a): return (self.width, self.height)

class TextField(FieldBase):
    def __init__(self, name, width, height=15, multiline=False, underlined=False):
        super().__init__(name, width, height); self.multiline=multiline; self.underlined=underlined
    def draw(self):
        ff = self.canv.acroForm
        flags = 'multiline' if self.multiline else ''
        if self.underlined:
            ff.textfield(name=self.name, x=0, y=0, width=self.width, height=self.height,
                         borderStyle='underlined', borderWidth=0.75, borderColor=INK,
                         fillColor=None, fontName='Helvetica', fontSize=9, relative=True,
                         fieldFlags=flags, maxlen=200)
        else:
            ff.textfield(name=self.name, x=0, y=0, width=self.width, height=self.height,
                         borderStyle='inset', borderWidth=0.75, borderColor=LINE,
                         fillColor=FIELDBG, fontName='Helvetica', fontSize=9, relative=True,
                         fieldFlags=flags, maxlen=2000)

class CheckField(FieldBase):
    def __init__(self, name, size=11):
        super().__init__(name, size, size); self.size=size
    def draw(self):
        self.canv.acroForm.checkbox(name=self.name, x=0, y=0, size=self.size,
                                    borderStyle='inset', borderWidth=0.75, borderColor=INK,
                                    fillColor=FIELDBG, checked=False, relative=True, fieldFlags='')

def labeled(label, field, label_w=2.05*inch):
    """Return a single-row table: bold label + field flowable, baseline-aligned."""
    t = Table([[Paragraph(label, S['label']), field]], colWidths=[label_w, None])
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                           ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                           ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    return t

def check_row(name, text):
    t = Table([[CheckField(name), Paragraph(text, S['body'])]], colWidths=[0.3*inch, None])
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                           ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                           ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
    return t

def build_terms_sheet(path):
    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=0.85*inch, rightMargin=0.85*inch,
                            topMargin=0.8*inch, bottomMargin=0.8*inch,
                            title=f'{FORM_ENTITY} Lease Terms Sheet')
    W = letter[0] - 1.7*inch
    st = []
    st.append(title_para('Lease Terms Sheet'))
    st.append(Paragraph(f'{FORM_ENTITY} &#183; {FORM_ADDR}', S['sub']))
    st.append(Paragraph(f'{FORM_VERSION} &#183; {FORM_VDATE}', S['sub']))
    st.append(Spacer(1,6))
    st.append(Paragraph('The specific, negotiated terms of your lease, including signatures and exhibits. '
                        'This is a fillable example. Where this Terms Sheet is silent, the Standard Lease Terms '
                        'and Definitions &#40;posted at courthousesquarevashon.com/lease/&#41; control; in the event of a '
                        'conflict, this Terms Sheet prevails.', S['small']))
    st.append(Spacer(1,6)); st.append(HRFlowable(width='100%', thickness=0.6, color=LINE)); st.append(Spacer(1,8))

    def section(title):
        form_section(st, title)

    section('1. The Parties')
    st.append(labeled('Landlord:', Paragraph(f'{FORM_ENTITY}, a Washington Limited Liability Company', S['body'])))
    st.append(labeled('Tenant (entity):', TextField('tenant_entity', W-2.05*inch)))
    st.append(labeled('Tenant address:', TextField('tenant_address', W-2.05*inch)))
    st.append(labeled('Guarantor(s):', TextField('guarantor', W-2.05*inch)))
    st.append(Paragraph('If no guaranty is required, write "Intentionally Omitted."', S['small']))

    section('2. The Premises')
    st.append(labeled('Property / Building:', TextField('property_name', W-2.05*inch)))
    st.append(labeled('Address / Suite:', TextField('premises_addr', W-2.05*inch)))
    st.append(labeled('Approximate square footage:', TextField('sqft', 1.6*inch)))
    st.append(labeled('Legal Description:', Paragraph('See Exhibit A, attached', S['body'])))

    section('3. The Term')
    st.append(labeled('Lease Start Date:', TextField('start_date', 2.0*inch)))
    st.append(labeled('Rent Commencement Date:', TextField('rent_comm', 2.0*inch)))
    st.append(labeled('Lease Expiration Date:', TextField('exp_date', 2.0*inch)))
    st.append(labeled('Renewal options:', TextField('renewal', W-2.05*inch)))

    section('4. Financial Obligations')
    st.append(Paragraph('Lease type:', S['label']))
    st.append(check_row('type_cam', 'CAM Pass-Through (standard for multi-tenant)'))
    st.append(check_row('type_nnn', 'Triple Net, NNN (single-tenant; see Exhibit D)'))
    st.append(Spacer(1,3))
    st.append(labeled('Initial Base Rent:', TextField('base_rent', 2.0*inch)))
    st.append(labeled('Rent escalation:', TextField('escalation', W-2.05*inch)))
    st.append(labeled('Estimated CAM / month:', TextField('cam_est', 2.0*inch)))
    st.append(labeled('Proportionate Share:', TextField('prop_share', 1.4*inch)))
    st.append(labeled('Direct utilities (Tenant-paid):', TextField('utilities', W-2.05*inch)))
    st.append(labeled('Security Deposit:', TextField('deposit', 2.0*inch)))
    st.append(labeled('First month Rent & CAM:', TextField('first_month', 2.0*inch)))
    st.append(Paragraph('The refundable $100 Good Faith Deposit submitted with the Letter of Intent is credited '
                        'toward the amounts due upon signing.', S['small']))

    section('5. Operations & Special Conditions')
    st.append(labeled('Permitted Use:', TextField('permitted_use', W-2.05*inch)))
    st.append(labeled('Delivery condition:', TextField('delivery', W-2.05*inch, height=28, multiline=True)))
    st.append(labeled('Exclusive use (if any):', TextField('exclusive', W-2.05*inch)))
    st.append(Paragraph('Special stipulations:', S['label']))
    st.append(TextField('special', W, height=46, multiline=True))
    st.append(Spacer(1,4))

    section('6. Notices')
    st.append(Paragraph('All notices under this Lease shall be in writing and effective (i) when delivered in '
                        'person or via overnight courier to the other party, or (ii) three (3) days after being '
                        'sent by registered or certified mail to the other party at the address set forth in this '
                        'Section.', S['body']))
    st.append(Paragraph(f'Notice to Landlord: {FORM_ENTITY}, {NOTICE_CO.replace("&", "&amp;")}, {NOTICE_ADDR}. '
                        f'Courtesy email: {IDENT["email"]}', S['body']))
    st.append(Paragraph('Notice to Tenant:', S['label']))
    st.append(labeled('Tenant notice name:', TextField('tn_name', W-2.05*inch)))
    st.append(labeled('Tenant notice address:', TextField('tn_addr', W-2.05*inch)))
    st.append(labeled('Tenant courtesy email:', TextField('tn_email', W-2.05*inch)))

    section('7. Incorporation and Merger')
    st.append(Paragraph(f'This Lease Terms Sheet, together with its Exhibits, the Standard Lease Terms, and the '
                        f'Definitions &amp; Glossary ({FORM_VERSION}, {FORM_VDATE}, posted at courthousesquarevashon.com/lease/), '
                        'constitutes the entire Commercial Lease Agreement and supersedes the Letter of Intent. In the event '
                        'of any conflict between this Terms Sheet and the online Standard Lease Terms or Definitions, this '
                        'Terms Sheet prevails.', S['body']))

    st.append(PageBreak())
    section('Signatures')
    def sig_block(prefix, role):
        st.append(Spacer(1,8)); st.append(Paragraph(role, S['label']))
        st.append(labeled('Signature:', TextField(prefix+'_sig', W-2.05*inch, underlined=True)))
        st.append(labeled('Printed name / title:', TextField(prefix+'_name', W-2.05*inch, underlined=True)))
        st.append(labeled('Date:', TextField(prefix+'_date', 2.2*inch, underlined=True)))
    sig_block('sll', f'LANDLORD: {FORM_ENTITY}')
    sig_block('stn', 'TENANT (the business entity)')
    sig_block('sgr', 'PERSONAL GUARANTOR (only if a Guarantor is named in Section 1)')
    st.append(labeled('Guarantor home address:', TextField('sgr_addr', W-2.05*inch, underlined=True)))
    st.append(Spacer(1,6))
    st.append(Paragraph('[Insert notary blocks for the respective signatories, as applicable.]', S['small']))

    st.append(PageBreak())
    section('Index of Exhibits')
    st.append(Paragraph('Check each Exhibit attached to this Lease Terms Sheet. Full exhibit text is provided when '
                        'the exhibit applies.', S['small']))
    st.append(check_row('ex_a', 'Exhibit A: Legal Description'))
    st.append(check_row('ex_b', 'Exhibit B: Unconditional Guaranty of Lease (if a Guarantor is named)'))
    st.append(check_row('ex_c', 'Exhibit C: Tenant Work Letter / build-out specs (if applicable)'))
    st.append(check_row('ex_d', 'Exhibit D: NNN Lease Amendment (if Triple Net is elected)'))
    st.append(Table([[CheckField('ex_e'), Paragraph('Exhibit E: Other:', S['body']), TextField('ex_e_text', 2.6*inch)]],
                    colWidths=[0.3*inch, 1.1*inch, None],
                    style=TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                                      ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                                      ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)])))

    section('Exhibit C: Tenant Work Letter (fill-in)')
    st.append(labeled('TI allowance (if any):', TextField('ti_allowance', 2.0*inch)))
    st.append(labeled('Substantial completion by:', TextField('ti_complete', 2.0*inch)))
    st.append(Paragraph('Scope of Tenant\'s Work:', S['label']))
    st.append(TextField('ti_scope', W, height=46, multiline=True))
    st.append(Spacer(1,6))
    st.append(Paragraph('Exhibits B (Guaranty) and D (NNN Amendment) carry standard text supplied when they apply; '
                        'their key terms appear in the Standard Lease Terms and Definitions.', S['small']))

    doc.build(st, canvasmaker=footer_canvas(FORM_FOOTER))
    print('wrote', path)

# ---------------- Letter of Intent (internal, fillable) ----------------
def build_loi_form(path):
    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=0.85*inch, rightMargin=0.85*inch,
                            topMargin=0.8*inch, bottomMargin=0.8*inch,
                            title=f'{FORM_ENTITY} Letter of Intent & Lease Application')
    W = letter[0] - 1.7*inch
    st = []
    st.append(title_para('Letter of Intent &amp; Lease Application'))
    st.append(Paragraph(f'{FORM_ENTITY} &#183; {FORM_ADDR}', S['sub']))
    st.append(Paragraph(f'{FORM_VERSION} &#183; {FORM_VDATE}', S['sub']))
    st.append(Spacer(1,6))
    st.append(Paragraph(
        'This Letter of Intent and Application (this &#8220;LOI&#8221;) outlines the basic proposed terms for a '
        'commercial lease and serves as an application for tenancy. It is not a binding lease agreement; a binding '
        'relationship arises only upon execution of the formal, written Commercial Lease Agreement (the Lease Terms '
        'Sheet, the Standard Lease Terms, and the Definitions) by both parties. The complete Standard Lease Terms '
        'and Definitions are posted at courthousesquarevashon.com/lease/.', S['small']))
    st.append(Spacer(1,4))
    st.append(Paragraph(
        '<b>How to apply.</b> Complete this form (and, if requested by Landlord, the Experian Credit Application) '
        'and email it to leasing@courthousesquarevashon.com, or start with the shorter inquiry form at '
        'courthousesquarevashon.com and our staff will help you finish it.', S['quote']))
    st.append(Spacer(1,6)); st.append(HRFlowable(width='100%', thickness=0.6, color=LINE)); st.append(Spacer(1,8))

    def section(title):
        form_section(st, title)

    def field(label, name, height=15, multiline=False):
        """Prompt on its own line, with a fill-in field directly beneath it."""
        st.append(Paragraph(label, S['label']))
        st.append(TextField(name, W, height=height, multiline=multiline, underlined=not multiline))
        st.append(Spacer(1,7))

    section('1. Applicant Information')
    field('Legal business name (the entity)', 'loi_legal_name')
    field('DBA (doing business as)', 'loi_dba')
    field('Entity type and state of formation', 'loi_entity_type')
    field('IRS business EIN; Washington UBI', 'loi_ein_ubi')
    field('Primary contact and lease guarantor name', 'loi_contact_name')
    field('Contact phone and email', 'loi_contact_info')
    field('Current address', 'loi_current_addr')

    section('2. Proposed Lease Terms')
    field('Property / suite address', 'loi_premises')
    field('Proposed permitted use', 'loi_use')
    field('Target lease start date', 'loi_start')
    field('Proposed initial lease term', 'loi_term')
    st.append(Paragraph('Proposed lease type:', S['label']))
    st.append(check_row('loi_type_cam', 'CAM Pass-Through (standard)'))
    st.append(check_row('loi_type_nnn', 'Triple Net (NNN)'))
    st.append(Spacer(1,5))
    field('Proposed initial Base Rent (per month)', 'loi_base_rent')
    field('Estimated CAM Charges (per month, subject to annual reconciliation)', 'loi_cam')
    field('Proposed security deposit (paid upon signing the final Lease)', 'loi_deposit')
    field('Additional requests or special terms &#8212; plain language is fine, one per line '
          '(e.g. &#8220;we have a small office dog&#8221;, &#8220;need to hang a sign over the door&#8221;)',
          'loi_notes', height=46, multiline=True)

    section('3. References &amp; Background')
    field('Prior commercial landlord reference 1 (name, contact, property, dates, reason for departure)',
          'loi_ref1', height=34, multiline=True)
    field('Prior commercial landlord reference 2 (name, contact, property, dates, reason for departure)',
          'loi_ref2', height=34, multiline=True)
    field('Primary banking reference (bank, branch / contact, relationship duration)',
          'loi_bank', height=28, multiline=True)
    st.append(Paragraph('First-time commercial tenants may provide two business or professional references instead.', S['small']))

    section('4. The Good Faith Deposit')
    st.append(Paragraph(
        'To show sincere interest while Landlord processes the application and the parties review the formal Lease, '
        'the applicant submits a refundable Good Faith Deposit of $100.00.', S['body']))
    st.append(Paragraph(
        '&#8226;&nbsp; <b>If a lease is signed:</b> the deposit is fully credited toward the first month&#8217;s Rent '
        'or Security Deposit.', S['body']))
    st.append(Paragraph(
        '&#8226;&nbsp; <b>If a lease is not signed</b> for any reason (Landlord declines, terms cannot be agreed, or '
        'the applicant decides the space is not the right fit): the deposit is refunded in full within three (3) '
        'business days.', S['body']))

    section('5. Authorization for Credit &amp; Background Check [If Requested by Landlord]')
    st.append(Paragraph(
        'By signing, the applicant (and the individual primary contact / guarantor) represents that all information '
        'provided is true and accurate, and authorizes Landlord and its agents to obtain commercial and personal '
        'credit reports, verify bank references, contact the references identified in Section 3, and conduct criminal '
        'and background checks necessary to evaluate the application. If requested by Landlord, Applicant is also '
        'completing and submitting a signed Experian Credit Application (attached to this Lease Application), along '
        f'with a check made payable to {FORM_ENTITY} for the amount below to cover the cost of the Experian Credit '
        'Report(s). If Applicant is operating as a separate entity, reports will be obtained for both the business '
        'name and the Applicant, personally.', S['body']))
    st.append(labeled('Experian Credit Report fee:', TextField('loi_experian_fee', 1.6*inch), label_w=2.05*inch))

    section('6. Submission')
    st.append(Paragraph(
        'Completed applications, together with the Good Faith Deposit, are submitted to '
        'leasing@courthousesquarevashon.com. Instructions for transmitting the Good Faith Deposit are provided upon '
        'receipt of the completed application.', S['body']))
    st.append(Spacer(1,10))
    st.append(Paragraph('Agreed and authorized by applicant:', S['label']))
    st.append(labeled('Signature:', TextField('loi_sig', W-2.05*inch, underlined=True)))
    st.append(labeled('Printed name / title:', TextField('loi_sig_name', W-2.05*inch, underlined=True)))
    st.append(labeled('Date:', TextField('loi_sig_date', 2.2*inch, underlined=True)))

    doc.build(st, canvasmaker=footer_canvas(FORM_FOOTER))
    print('wrote', path)

def build_cover(path):
    doc = SimpleDocTemplate(path, pagesize=letter, topMargin=2.2*inch,
                            leftMargin=0.85*inch, rightMargin=0.85*inch, bottomMargin=0.8*inch)
    num = lambda n: f'<font color="#b4521f">{n}</font>&nbsp;&nbsp;&nbsp;'
    st = [HRFlowable(width=40, thickness=3, color=RUST, spaceAfter=14, hAlign='LEFT'),
          Paragraph(html.escape(tracked('Courthouse Square'), quote=False), S['title']),
          Paragraph(html.escape(tracked('Vashon'), quote=False),
                    ParagraphStyle('cv', fontName='Jost-Medium', fontSize=10, textColor=MUTE, spaceAfter=8, leading=14)),
          *dual_rule(),
          Spacer(1,8),
          Paragraph(html.escape(tracked('Complete Commercial Lease Package'), quote=False), S['h2']),
          Spacer(1,6),
          Paragraph(f'{FORM_VERSION} &#183; {FORM_VDATE}', S['sub']),
          Spacer(1,20),
          Paragraph('<i>Assembled for review. Contents, in order:</i>', S['body']),
          Spacer(1,4),
          Paragraph(num(1) + 'Letter of Intent &amp; Lease Application (applicant intake; fillable)', S['body']),
          Paragraph(num(2) + 'Lease Terms Sheet (deal-specific terms, signatures, and exhibits; fillable example)', S['body']),
          Paragraph(num(3) + 'Standard Lease Terms (the standard terms that apply to every tenant)', S['body']),
          Paragraph(num(4) + 'Definitions &amp; Glossary', S['body']),
          Spacer(1,16),
          Paragraph('This consolidated package is for internal review. Its parts are published individually at '
                    'courthousesquarevashon.com/lease/: the Standard Lease Terms and Definitions, the fillable Lease '
                    'Terms Sheet, and the fillable Letter of Intent &amp; Application.', S['small']),
          Spacer(1,6),
          Paragraph(f'All parts are stamped {VERSION}, {VDATE} (incorporates the June 28, 2026 attorney redlines).', S['small'])]
    doc.build(st)
    print('wrote', path)

def merge(paths, out):
    # Imported lazily: only the consolidated review PDF needs pypdf.
    from pypdf import PdfWriter, PdfReader
    w = PdfWriter()
    for p in paths:
        w.append(p)   # append() (not add_page) carries AcroForm fields through the merge
    with open(out,'wb') as f: w.write(f)
    print('wrote', out, '(%d pages)' % len(PdfReader(out).pages))

if __name__ == '__main__':
    import os, tempfile
    os.makedirs(REVIEW, exist_ok=True)
    # 1. public standard lease (Standard Lease Terms + Definitions) — v1.2, pending redlines
    with open(ROOT+'/lease/lease.md') as f: lease_md = f.read()
    build_prose(ROOT+'/lease/lease.pdf', lease_md)
    # 2. fillable Lease Terms Sheet (public example) — v1.3
    build_terms_sheet(ROOT+'/lease/lease-terms-sheet.pdf')
    # 3. fillable Letter of Intent & Application (public) — v1.3
    build_loi_form(ROOT+'/lease/letter-of-intent.pdf')
    # 4. consolidated review package (internal)
    cover = os.path.join(tempfile.gettempdir(), '_chs_cover.pdf')
    build_cover(cover)
    import datetime
    vtag = datetime.datetime.strptime(VDATE, '%B %d, %Y').strftime('v%Y.%m.%d')
    merge([cover, ROOT+'/lease/letter-of-intent.pdf', ROOT+'/lease/lease-terms-sheet.pdf', ROOT+'/lease/lease.pdf'],
          REVIEW+f'/CourthouseSquare_FullLease_{vtag}.pdf')
    print('DONE')
