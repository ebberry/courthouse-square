#!/usr/bin/env python3
# Build the Courthouse Square lease document set (Version 1.2, 2026-06-08):
#   - lease/lease.pdf                  Standard Lease Terms + Definitions (public)
#   - lease/lease-terms-sheet.pdf      Fillable Lease Terms Sheet example (public)
#   - review/letter-of-intent.pdf      Letter of Intent (internal)
#   - review/CourthouseSquare_FullLease_v2026.06.08.pdf  Consolidated, all parts (internal, for deep review)
#
# Pure reportlab + pypdf (no system deps). Absolute paths only (no getcwd).

import re, html
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
                                Table, TableStyle, Flowable, KeepTogether, PageBreak)
from reportlab.pdfgen import canvas as canvaslib
from pypdf import PdfWriter, PdfReader

import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW = ROOT + '/review'
VERSION = 'Version 1.2'
VDATE = 'June 8, 2026'
FOOTER = f'Courthouse Square LLC    {VERSION}, {VDATE}'

INK   = HexColor(0x1e3128)
INK2  = HexColor(0x243b2f)
MUTE  = HexColor(0x4a443b)
LINE  = HexColor(0xbcd0c2)
RUST  = HexColor(0xb4521f)
FIELDBG = HexColor(0xf7f3ea)

# ---------------- styles ----------------
def styles():
    ss = getSampleStyleSheet()
    out = {}
    out['title']   = ParagraphStyle('t', parent=ss['Title'], fontName='Times-Bold',
                                     fontSize=22, textColor=INK, spaceAfter=4, leading=26, alignment=TA_LEFT)
    out['sub']     = ParagraphStyle('sub', fontName='Helvetica', fontSize=10, textColor=MUTE, spaceAfter=2, leading=14)
    out['h2']      = ParagraphStyle('h2', fontName='Times-Bold', fontSize=16, textColor=INK,
                                    spaceBefore=18, spaceAfter=8, leading=20)
    out['h3']      = ParagraphStyle('h3', fontName='Times-Bold', fontSize=12.5, textColor=INK2,
                                    spaceBefore=12, spaceAfter=4, leading=16)
    out['body']    = ParagraphStyle('body', fontName='Helvetica', fontSize=10, textColor=INK,
                                    spaceAfter=7, leading=15)
    out['bullet']  = ParagraphStyle('bullet', parent=out['body'], leftIndent=16, bulletIndent=4, spaceAfter=3)
    out['quote']   = ParagraphStyle('quote', fontName='Helvetica-Oblique', fontSize=10, textColor=INK2,
                                    leftIndent=12, rightIndent=8, spaceBefore=4, spaceAfter=10, leading=15,
                                    borderColor=LINE, borderWidth=0, backColor=HexColor(0xf2f6f3))
    out['label']   = ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=9.5, textColor=INK, leading=13)
    out['small']   = ParagraphStyle('small', fontName='Helvetica', fontSize=8.5, textColor=MUTE, leading=12)
    out['center']  = ParagraphStyle('center', parent=out['body'], alignment=TA_CENTER)
    return out
S = styles()

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
            story.append(Spacer(1, 4)); story.append(HRFlowable(width='100%', thickness=0.6, color=LINE))
            story.append(Spacer(1, 4)); i += 1; continue
        if s.startswith('### '):
            story.append(Paragraph(inline(s[4:]), S['h3'])); i += 1; continue
        if s.startswith('## '):
            story.append(Paragraph(inline(s[3:]), S['h2'])); i += 1; continue
        if s.startswith('# '):
            story.append(Paragraph(inline(s[2:]), S['title'])); i += 1; continue
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
        self.setFont('Helvetica', 7.5); self.setFillColor(MUTE)
        w, _ = letter
        self.drawString(0.85*inch, 0.5*inch, FOOTER)
        self.drawRightString(w - 0.85*inch, 0.5*inch, f'Page {self._pageNumber} of {total}')
        self.setStrokeColor(LINE); self.setLineWidth(0.5)
        self.line(0.85*inch, 0.62*inch, w - 0.85*inch, 0.62*inch)

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
                            title='Courthouse Square LLC Lease Terms Sheet')
    W = letter[0] - 1.7*inch
    st = []
    st.append(Paragraph('Lease Terms Sheet', S['title']))
    st.append(Paragraph('Courthouse Square LLC &#183; 1301 Spring Street, Unit 29H, Seattle, WA 98104', S['sub']))
    st.append(Paragraph(f'{VERSION} &#183; {VDATE}', S['sub']))
    st.append(Spacer(1,6))
    st.append(Paragraph('The specific, negotiated terms of your lease, including signatures and exhibits. '
                        'This is a fillable example. Where this Terms Sheet is silent, the Standard Lease Terms '
                        'and Definitions &#40;posted at courthousesquarevashon.com/lease/&#41; control; in the event of a '
                        'conflict, this Terms Sheet prevails.', S['small']))
    st.append(Spacer(1,6)); st.append(HRFlowable(width='100%', thickness=0.6, color=LINE)); st.append(Spacer(1,8))

    def section(title):
        st.append(Spacer(1,4)); st.append(Paragraph(title, S['h3']))

    section('1. The Parties')
    st.append(labeled('Landlord:', Paragraph('Courthouse Square LLC, a Washington LLC', S['body'])))
    st.append(labeled('Tenant (entity):', TextField('tenant_entity', W-2.05*inch)))
    st.append(labeled('Tenant address:', TextField('tenant_address', W-2.05*inch)))
    st.append(labeled('Guarantor(s):', TextField('guarantor', W-2.05*inch)))
    st.append(Paragraph('If no guaranty is required, write "Intentionally Omitted."', S['small']))

    section('2. The Premises')
    st.append(labeled('Property / Building:', TextField('property_name', W-2.05*inch)))
    st.append(labeled('Address / Suite:', TextField('premises_addr', W-2.05*inch)))
    st.append(labeled('Rentable square footage:', TextField('sqft', 1.6*inch)))

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

    section('6. Notice Addresses')
    st.append(Paragraph('Landlord: Courthouse Square LLC, 1301 Spring Street, Unit 29H, Seattle, WA 98104. '
                        'Courtesy email: leasing@courthousesquarevashon.com', S['body']))
    st.append(labeled('Tenant notice name:', TextField('tn_name', W-2.05*inch)))
    st.append(labeled('Tenant notice address:', TextField('tn_addr', W-2.05*inch)))
    st.append(labeled('Tenant courtesy email:', TextField('tn_email', W-2.05*inch)))

    section('7. Incorporation and Merger')
    st.append(Paragraph('This Lease Terms Sheet, together with its Exhibits, the Standard Lease Terms, and the '
                        'Definitions & Glossary (Version 1.2, June 8, 2026, posted at courthousesquarevashon.com/lease/), '
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
    sig_block('sll', 'LANDLORD: Courthouse Square LLC')
    sig_block('stn', 'TENANT (the business entity)')
    sig_block('sgr', 'PERSONAL GUARANTOR (only if a Guarantor is named in Section 1)')
    st.append(labeled('Guarantor home address:', TextField('sgr_addr', W-2.05*inch, underlined=True)))
    st.append(Spacer(1,6))
    st.append(Paragraph('[Insert notary blocks for the respective signatories, as applicable.]', S['small']))

    st.append(PageBreak())
    section('Index of Exhibits')
    st.append(Paragraph('Check each Exhibit attached to this Lease Terms Sheet. Full exhibit text is provided when '
                        'the exhibit applies.', S['small']))
    st.append(check_row('ex_a', 'Exhibit A: Outline of the Premises (floor plan)'))
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

    doc.build(st)
    print('wrote', path)

# ---------------- Letter of Intent (internal) ----------------
LOI_MD = f"""# Letter of Intent & Lease Application

**Courthouse Square LLC**
1301 Spring Street, Unit 29H, Seattle, Washington 98104
**{VERSION}, {VDATE}**

> This Letter of Intent and Application (this "LOI") outlines the basic proposed terms for a commercial lease and serves as an application for tenancy. This LOI is not a binding lease agreement. A binding legal relationship will only be created upon execution of the formal, written Commercial Lease Agreement (the Lease Terms Sheet, the Standard Lease Terms, and the Definitions) by both parties. The complete Standard Lease Terms and Definitions are posted at courthousesquarevashon.com/lease/.

> **Internal note.** This document is used as an internal intake checklist. Prospects begin by reaching out through the website inquiry form or by emailing leasing@courthousesquarevashon.com; staff complete this LOI with the applicant from there.

## 1. Applicant Information

- Legal business name (the entity)
- DBA (doing business as)
- Entity type and state of formation
- IRS business EIN; Washington UBI
- Primary contact and lease guarantor name
- Contact phone and email
- Current address

## 2. Proposed Lease Terms

- Property / suite address
- Proposed permitted use
- Target lease start date
- Proposed initial lease term
- Proposed lease type: CAM Pass-Through (standard) or Triple Net (NNN)
- Proposed initial Base Rent (per month)
- Estimated CAM Charges (per month, subject to annual reconciliation)
- Proposed security deposit (paid upon signing the final Lease)

## 3. References & Background

- Prior commercial landlord reference 1 (name, contact, property, dates, reason for departure)
- Prior commercial landlord reference 2 (name, contact, property, dates, reason for departure)
- Primary banking reference (bank, branch / contact, relationship duration)
- First-time commercial tenants may provide two business or professional references instead.

## 4. The Good Faith Deposit

To show sincere interest while Landlord processes the application and the parties review the formal Lease, the applicant submits a refundable Good Faith Deposit of $100.00.

- **If a lease is signed:** the deposit is fully credited toward the first month's Rent or Security Deposit.
- **If a lease is not signed:** for any reason (Landlord declines, terms cannot be agreed, or the applicant decides the space is not the right fit), the deposit is refunded in full within three (3) business days.

## 5. Authorization for Credit & Background Check

By signing, the applicant (and the individual primary contact / guarantor) represents that all information provided is true and accurate, and authorizes Landlord and its agents to obtain commercial and personal credit reports, verify bank references, contact the references identified in Section 3, and conduct criminal and background checks necessary to evaluate the application.

## 6. Submission

Completed applications, together with the Good Faith Deposit, are submitted to leasing@courthousesquarevashon.com. Instructions for transmitting the Good Faith Deposit are provided upon receipt of the completed application.

---

*Agreed and authorized by applicant: signature, printed name, title, date.*

*End of the Letter of Intent.*
"""

def build_cover(path):
    doc = SimpleDocTemplate(path, pagesize=letter, topMargin=2.2*inch,
                            leftMargin=0.85*inch, rightMargin=0.85*inch, bottomMargin=0.8*inch)
    st = [Paragraph('Courthouse Square', S['title']),
          Paragraph('Complete Commercial Lease Package', S['h2']),
          Spacer(1,10),
          Paragraph(f'{VERSION} &#183; {VDATE}', S['sub']),
          Spacer(1,16),
          Paragraph('Assembled for review. Contents, in order:', S['body']),
          Paragraph('1. Letter of Intent &amp; Lease Application (internal intake)', S['body']),
          Paragraph('2. Lease Terms Sheet (deal-specific terms, signatures, and exhibits; fillable example)', S['body']),
          Paragraph('3. Standard Lease Terms (the standard terms that apply to every tenant)', S['body']),
          Paragraph('4. Definitions &amp; Glossary', S['body']),
          Spacer(1,16),
          Paragraph('This package is for internal review and is not a public document. The Standard Lease Terms '
                    'and Definitions are posted publicly at courthousesquarevashon.com/lease/; the Letter of Intent '
                    'is an internal checklist.', S['small'])]
    doc.build(st)
    print('wrote', path)

def merge(paths, out):
    w = PdfWriter()
    for p in paths:
        for pg in PdfReader(p).pages:
            w.add_page(pg)
    with open(out,'wb') as f: w.write(f)
    print('wrote', out, '(%d pages)' % len(PdfReader(out).pages))

if __name__ == '__main__':
    import os
    os.makedirs(REVIEW, exist_ok=True)
    # 1. public lease (standard terms + definitions)
    with open(ROOT+'/lease/lease.md') as f: lease_md = f.read()
    build_prose(ROOT+'/lease/lease.pdf', lease_md)
    # 2. fillable terms sheet (public example)
    build_terms_sheet(ROOT+'/lease/lease-terms-sheet.pdf')
    # 3. LOI (internal)
    build_prose(REVIEW+'/letter-of-intent.pdf', LOI_MD)
    # 4. consolidated review package (internal)
    build_cover('/tmp/_cover.pdf')
    merge(['/tmp/_cover.pdf', REVIEW+'/letter-of-intent.pdf', ROOT+'/lease/lease-terms-sheet.pdf', ROOT+'/lease/lease.pdf'],
          REVIEW+'/CourthouseSquare_FullLease_v2026.06.08.pdf')
    print('DONE')
