/* Lease Builder — staff tool.
 *
 * Reads the checklist form on /lease/builder.html and generates, entirely in
 * the browser (vendored pdf-lib, no server):
 *
 *   1. The signature-ready lease package: a dynamically laid-out, filled
 *      Lease Terms Sheet (sections that don't apply are omitted and the
 *      document reflows), followed by the pages of the posted standard lease
 *      (/lease/lease.pdf, Standard Lease Terms + Definitions).
 *
 *   2. A two-page record: the completed checklist (including what was
 *      omitted) on page one, and the suite's full CAM & cost calculations
 *      on page two.
 *
 * Layout mirrors the reportlab styling in tools/build_lease_docs.py:
 * Times-Bold headings, Helvetica body, the evergreen/sand palette.
 */
(function () {
  'use strict';

  const { PDFDocument, StandardFonts, rgb } = PDFLib;

  // ---------- identity constants (keep in sync with tools/build_lease_docs.py) ----------
  const ENTITY       = 'Courthouse Square Vashon LLC';
  const ENTITY_LONG  = ENTITY + ', a Washington Limited Liability Company';
  const BUILDING     = 'Courthouse Square';
  const ADDR         = '19001 Vashon Hwy SW, Vashon Island, WA 98070';
  const FORM_VERSION = 'Version 1.3';
  const FORM_VDATE   = 'June 12, 2026';
  const LANDLORD_NOTICE = ENTITY + ', c/o Bangasser & Associates, Inc., ' + ADDR +
                          '. Courtesy email: leasing@courthousesquarevashon.com';

  // ---------- palette ----------
  const C = h => rgb(((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255);
  const INK  = C(0x1e3128);
  const INK2 = C(0x243b2f);
  const MUTE = C(0x4a443b);
  const LINE = C(0xbcd0c2);
  const RUST = C(0xb4521f);

  // ---------- page geometry (US letter, 0.85in side margins like the PDFs) ----------
  const PAGE_W = 612, PAGE_H = 792;
  const M_LEFT = 61.2, M_RIGHT = 61.2, M_TOP = 58, M_BOTTOM = 76;
  const BODY_W = PAGE_W - M_LEFT - M_RIGHT;

  // ---------- state ----------
  let vacData = { asOf: '', buildingSqft: 0, suites: [] };

  const $ = id => document.getElementById(id);
  const val = id => ($(id) ? $(id).value.trim() : '');
  const num = id => { const n = parseFloat(val(id)); return isFinite(n) ? n : 0; };

  const fmtMoney = n => '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtInt   = n => Number(n).toLocaleString('en-US');

  // "2026-07-01" -> "July 1, 2026" (parsed by parts; avoids UTC day-shift)
  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    if (!m) return iso || '';
    return new Date(+m[1], +m[2] - 1, +m[3])
      .toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  }

  // Standard fonts encode WinAnsi only — replace anything outside Latin-1.
  function safe(s) {
    return String(s == null ? '' : s)
      .replace(/[‘’]/g, "'").replace(/[“”]/g, '"')
      .replace(/–/g, '-').replace(/—/g, '--').replace(/…/g, '...')
      .replace(/[^\x00-\xFF]/g, '?');
  }

  // ============================================================
  // Flow: a tiny cursor-based layout engine over pdf-lib
  // ============================================================
  class Flow {
    constructor(doc, fonts, footerLeft) {
      this.doc = doc; this.f = fonts; this.footerLeft = footerLeft;
      this.pages = [];
      this.newPage();
    }
    newPage() {
      this.page = this.doc.addPage([PAGE_W, PAGE_H]);
      this.pages.push(this.page);
      this.y = PAGE_H - M_TOP;
    }
    ensure(h) { if (this.y - h < M_BOTTOM) this.newPage(); }
    gap(h) { this.y -= h; }

    wrap(text, font, size, width) {
      const words = safe(text).split(/\s+/).filter(Boolean);
      const lines = []; let cur = '';
      for (const w of words) {
        const t = cur ? cur + ' ' + w : w;
        if (font.widthOfTextAtSize(t, size) <= width) cur = t;
        else { if (cur) lines.push(cur); cur = w; }
      }
      if (cur) lines.push(cur);
      return lines.length ? lines : [''];
    }

    text(str, o = {}) {
      const font = o.font || this.f.body, size = o.size || 10;
      const width = o.width || BODY_W, x = o.x || M_LEFT;
      const lh = o.lineHeight || size * 1.45;
      const lines = this.wrap(str, font, size, width);
      this.ensure(lines.length * lh + (o.spaceAfter || 0));
      for (const ln of lines) {
        this.y -= lh;
        this.page.drawText(ln, { x, y: this.y, size, font, color: o.color || INK });
      }
      this.y -= (o.spaceAfter || 0);
    }

    title(str)   { this.gap(4); this.text(str, { font: this.f.serifBold, size: 21, color: INK, lineHeight: 25, spaceAfter: 2 }); }
    sub(str)     { this.text(str, { font: this.f.body, size: 9.5, color: MUTE, lineHeight: 13 }); }
    section(str) { this.ensure(46); this.gap(14); this.text(str, { font: this.f.serifBold, size: 12.5, color: INK2, lineHeight: 15, spaceAfter: 3 }); }

    rule(color = LINE, thickness = 0.6) {
      this.ensure(10); this.y -= 6;
      this.page.drawLine({ start: { x: M_LEFT, y: this.y }, end: { x: PAGE_W - M_RIGHT, y: this.y }, thickness, color });
      this.y -= 4;
    }

    // Bold label in a fixed left column, wrapped value beside it.
    labeled(label, value, o = {}) {
      const size = o.size || 10, labelW = o.labelW || 150;
      const lh = size * 1.4;
      const vLines = this.wrap(value || '', this.f.body, size, BODY_W - labelW - 6);
      const h = Math.max(1, vLines.length) * lh + 3;
      this.ensure(h);
      const yStart = this.y - lh;
      this.page.drawText(safe(label), { x: M_LEFT, y: yStart, size, font: this.f.bold, color: INK });
      let yy = this.y;
      for (const ln of vLines) {
        yy -= lh;
        this.page.drawText(ln, { x: M_LEFT + labelW + 6, y: yy, size, font: this.f.body, color: INK });
      }
      this.y -= h;
    }

    // Signature line: label + long rule to write on.
    sigLine(label, o = {}) {
      const size = 10, lh = 22, labelW = o.labelW || 118;
      this.ensure(lh);
      this.y -= lh;
      this.page.drawText(safe(label), { x: M_LEFT, y: this.y, size, font: this.f.bold, color: INK });
      const x1 = M_LEFT + labelW, x2 = o.short ? M_LEFT + labelW + 160 : PAGE_W - M_RIGHT;
      this.page.drawLine({ start: { x: x1, y: this.y - 2 }, end: { x: x2, y: this.y - 2 }, thickness: 0.8, color: INK });
    }

    // Right-aligned money table row for the CAM page.
    tableRow(cells, cols, o = {}) {
      const size = o.size || 10, lh = size * 1.55;
      this.ensure(lh);
      this.y -= lh;
      cells.forEach((cell, i) => {
        const font = (o.boldCols || []).includes(i) || o.bold ? this.f.bold : this.f.body;
        const t = safe(cell);
        let x = cols[i].x;
        if (cols[i].align === 'right') x = cols[i].x + cols[i].w - font.widthOfTextAtSize(t, size);
        this.page.drawText(t, { x, y: this.y, size, font, color: o.color || INK });
      });
    }

    stampFooters(label) {
      const n = this.pages.length;
      this.pages.forEach((pg, i) => {
        pg.drawLine({ start: { x: M_LEFT, y: 44.6 }, end: { x: PAGE_W - M_RIGHT, y: 44.6 }, thickness: 0.5, color: LINE });
        pg.drawText(safe(this.footerLeft), { x: M_LEFT, y: 36, size: 7.5, font: this.f.body, color: MUTE });
        const t = `${label ? label + ' - ' : ''}Page ${i + 1} of ${n}`;
        pg.drawText(t, { x: PAGE_W - M_RIGHT - this.f.body.widthOfTextAtSize(t, 7.5), y: 36, size: 7.5, font: this.f.body, color: MUTE });
      });
    }
  }

  async function makeDoc() {
    const doc = await PDFDocument.create();
    const fonts = {
      serifBold: await doc.embedFont(StandardFonts.TimesRomanBold),
      body:      await doc.embedFont(StandardFonts.Helvetica),
      bold:      await doc.embedFont(StandardFonts.HelveticaBold),
      italic:    await doc.embedFont(StandardFonts.HelveticaOblique),
    };
    return { doc, fonts };
  }

  // ============================================================
  // Collect + derive everything from the form
  // ============================================================
  function collect() {
    const unit = val('f-suite');
    const suiteAddr = unit ? `19001 Vashon Hwy SW, Suite ${unit}, Vashon Island, WA 98070` : ADDR;
    const d = {
      tenant: val('f-tenant'),
      tenantAddr: val('f-tenant-addr') || suiteAddr,
      guarantor: val('f-guarantor'),
      guarantorAddr: val('f-guarantor-addr'),
      unit, suiteAddr,
      sqft: num('f-sqft'),
      share: num('f-share'),
      start: val('f-start'),
      rentStart: val('f-rent-start') || val('f-start'),
      end: val('f-end'),
      renewal: val('f-renewal'),
      nnn: $('f-type-nnn').checked,
      rent: num('f-rent'),
      cam: num('f-cam'),
      util: num('f-util'),
      escalation: val('f-escalation'),
      deposit: num('f-deposit'),
      directUtil: val('f-direct-util'),
      firstMonth: num('f-first-month'),
      gfd: $('f-gfd').checked,
      use: val('f-use'),
      delivery: val('f-delivery') || 'As-Is',
      exclusive: val('f-exclusive'),
      stipulations: val('f-stipulations'),
      noticeName: val('f-notice-name') || val('f-tenant'),
      noticeAddr: val('f-notice-addr') || suiteAddr,
      noticeEmail: val('f-notice-email'),
      exA: $('f-ex-a').checked,
      tiAllowance: val('f-ti-allowance'),
      tiComplete: val('f-ti-complete'),
      tiScope: val('f-ti-scope'),
      exE: val('f-ex-e'),
    };
    d.hasTI = !!(d.tiAllowance || d.tiComplete || d.tiScope);
    d.exhibits = [];
    if (d.exA)      d.exhibits.push('Exhibit A: Outline of the Premises (floor plan), attached separately');
    if (d.guarantor) d.exhibits.push('Exhibit B: Unconditional Guaranty of Lease');
    if (d.hasTI)    d.exhibits.push('Exhibit C: Tenant Work Letter (terms below)');
    if (d.nnn)      d.exhibits.push('Exhibit D: NNN Lease Amendment, attached separately');
    if (d.exE)      d.exhibits.push('Exhibit E: ' + d.exE);
    return d;
  }

  function validate(d) {
    const errs = [];
    if (!d.tenant) errs.push('Tenant legal name is required.');
    if (!d.unit)   errs.push('Choose a suite.');
    if (!d.start)  errs.push('Lease Start Date is required.');
    if (!d.end)    errs.push('Expiration Date is required.');
    if (!d.use)    errs.push('Permitted Use is required.');
    if (!(d.rent > 0)) errs.push('Base Rent must be greater than zero.');
    if (d.start && d.end && d.end <= d.start) errs.push('Expiration Date must be after the Start Date.');
    return errs;
  }

  // ============================================================
  // Document 1: signature-ready lease package
  // ============================================================
  async function buildLeasePackage(d) {
    const { doc, fonts } = await makeDoc();
    const F = new Flow(doc, fonts, `${ENTITY}    ${FORM_VERSION}, ${FORM_VDATE}`);

    F.title('Lease Terms Sheet');
    F.sub(`${ENTITY} - ${ADDR}`);
    F.sub(`${FORM_VERSION} - ${FORM_VDATE}`);
    F.gap(6);
    F.text('The specific, negotiated terms of this lease. Where this Terms Sheet is silent, the ' +
           'Standard Lease Terms and the Definitions & Glossary (attached, and posted at ' +
           'courthousesquarevashon.com/lease/) control; in the event of a conflict, this Terms Sheet prevails.',
           { size: 8.5, color: MUTE, lineHeight: 12 });
    F.rule();

    F.section('1. The Parties');
    F.labeled('Landlord:', ENTITY_LONG);
    F.labeled('Tenant (entity):', d.tenant);
    F.labeled('Tenant address:', d.tenantAddr);
    if (d.guarantor) F.labeled('Guarantor(s):', d.guarantor);

    F.section('2. The Premises');
    F.labeled('Property / Building:', BUILDING);
    F.labeled('Address / Suite:', d.suiteAddr);
    if (d.sqft)  F.labeled('Approximate square footage:', fmtInt(d.sqft));
    if (d.share) F.labeled('Proportionate Share:', d.share.toFixed(2) + '%');

    F.section('3. The Term');
    F.labeled('Lease Start Date:', fmtDate(d.start));
    F.labeled('Rent Commencement Date:', fmtDate(d.rentStart));
    F.labeled('Lease Expiration Date:', fmtDate(d.end));
    if (d.renewal) F.labeled('Renewal options:', d.renewal);

    F.section('4. Financial Obligations');
    F.labeled('Lease type:', d.nnn ? 'Triple Net (NNN) - see Exhibit D' : 'CAM Pass-Through (standard)');
    F.labeled('Initial Base Rent:', fmtMoney(d.rent) + ' per month');
    if (d.escalation) F.labeled('Rent escalation:', d.escalation);
    if (!d.nnn) {
      F.labeled('Estimated CAM / month:', fmtMoney(d.cam));
      if (d.util) F.labeled('Shared utilities / month:', fmtMoney(d.util));
    }
    if (d.directUtil) F.labeled('Direct utilities (Tenant-paid):', d.directUtil);
    F.labeled('Security Deposit:', fmtMoney(d.deposit));
    if (d.firstMonth) F.labeled('First month Rent & CAM:', fmtMoney(d.firstMonth));
    if (d.gfd) F.text('The refundable $100 Good Faith Deposit submitted with the Letter of Intent is credited toward the amounts due upon signing.',
                      { size: 8.5, color: MUTE, lineHeight: 12 });

    F.section('5. Operations & Special Conditions');
    F.labeled('Permitted Use:', d.use);
    F.labeled('Delivery condition:', d.delivery);
    if (d.exclusive)    F.labeled('Exclusive use:', d.exclusive);
    if (d.stipulations) F.labeled('Special stipulations:', d.stipulations);

    F.section('6. Notice Addresses');
    F.text('Landlord: ' + LANDLORD_NOTICE, { size: 10 });
    F.gap(2);
    F.labeled('Tenant notice name:', d.noticeName);
    F.labeled('Tenant notice address:', d.noticeAddr);
    if (d.noticeEmail) F.labeled('Tenant courtesy email:', d.noticeEmail);

    F.section('7. Incorporation and Merger');
    F.text(`This Lease Terms Sheet, together with its Exhibits, the Standard Lease Terms, and the Definitions & ` +
           `Glossary (${FORM_VERSION}, ${FORM_VDATE}, posted at courthousesquarevashon.com/lease/), constitutes ` +
           'the entire Commercial Lease Agreement and supersedes the Letter of Intent. In the event of any ' +
           'conflict between this Terms Sheet and the online Standard Lease Terms or Definitions, this Terms ' +
           'Sheet prevails.', { size: 10 });

    F.section('8. Index of Exhibits');
    if (d.exhibits.length) {
      for (const ex of d.exhibits) F.text('-  ' + ex, { size: 10, lineHeight: 15 });
    } else {
      F.text('No exhibits are attached to this Lease Terms Sheet.', { size: 10, font: F.f.italic });
    }

    if (d.hasTI) {
      F.section('Exhibit C: Tenant Work Letter');
      if (d.tiAllowance) F.labeled('TI allowance:', d.tiAllowance.startsWith('$') ? d.tiAllowance : '$' + d.tiAllowance);
      if (d.tiComplete)  F.labeled('Substantial completion by:', fmtDate(d.tiComplete));
      if (d.tiScope)     F.labeled("Scope of Tenant's Work:", d.tiScope);
    }

    // Signatures (guarantor block only when a guarantor exists).
    F.ensure(200);
    F.section('Signatures');
    F.gap(4);
    F.text('LANDLORD: ' + ENTITY, { font: F.f.bold, size: 10 });
    F.sigLine('Signature:'); F.sigLine('Printed name / title:'); F.sigLine('Date:', { short: true });
    F.gap(10);
    F.text('TENANT: ' + d.tenant, { font: F.f.bold, size: 10 });
    F.sigLine('Signature:'); F.sigLine('Printed name / title:'); F.sigLine('Date:', { short: true });
    if (d.guarantor) {
      F.gap(10);
      F.text('PERSONAL GUARANTOR: ' + d.guarantor, { font: F.f.bold, size: 10 });
      F.sigLine('Signature:'); F.sigLine('Printed name / title:'); F.sigLine('Date:', { short: true });
      F.labeled('Guarantor home address:', d.guarantorAddr || '');
    }

    F.stampFooters('Lease Terms Sheet');

    // Append the posted standard lease (Standard Lease Terms + Definitions).
    const stdBytes = await fetch('/lease/lease.pdf').then(r => {
      if (!r.ok) throw new Error('Could not load /lease/lease.pdf');
      return r.arrayBuffer();
    });
    const std = await PDFDocument.load(stdBytes);
    const copied = await doc.copyPages(std, std.getPageIndices());
    copied.forEach(p => doc.addPage(p));

    doc.setTitle(`Commercial Lease - ${ENTITY} - ${d.tenant} - Suite ${d.unit}`);
    return doc.save();
  }

  // ============================================================
  // Document 2: two-page record (checklist + CAM calculations)
  // ============================================================
  async function buildRecord(d) {
    const { doc, fonts } = await makeDoc();
    const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    const F = new Flow(doc, fonts, `${ENTITY}    Lease preparation record    Generated ${today}`);
    const NA = 'Not applicable - omitted from the lease';
    const na = (label, v) => v ? F.labeled(label, v) : F.labeled(label, NA, {});

    // ---------- page 1: the completed checklist ----------
    F.title('Lease Checklist');
    F.sub(`${d.tenant} - Suite ${d.unit} - prepared ${today}`);
    F.gap(2);
    F.text('Record of the information used to prepare the lease. Items marked "not applicable" were ' +
           'omitted from the generated Lease Terms Sheet.', { size: 8.5, color: MUTE, lineHeight: 12 });
    F.rule();

    const size = { size: 9.3, labelW: 168 };
    F.text('Parties', { font: F.f.bold, size: 10.5, color: INK2, spaceAfter: 1 });
    F.labeled('Tenant legal name:', d.tenant, size);
    F.labeled('Tenant address:', d.tenantAddr, size);
    d.guarantor ? F.labeled('Guarantor:', d.guarantor + (d.guarantorAddr ? ' - ' + d.guarantorAddr : ''), size)
                : F.labeled('Guarantor:', NA, size);
    F.gap(5);
    F.text('Premises & Term', { font: F.f.bold, size: 10.5, color: INK2, spaceAfter: 1 });
    F.labeled('Suite:', `${d.unit} - ${d.suiteAddr}`, size);
    F.labeled('Approximate sq ft:', fmtInt(d.sqft), size);
    F.labeled('Proportionate Share:', d.share.toFixed(2) + '%', size);
    F.labeled('Start / Rent start:', fmtDate(d.start) + '  /  ' + fmtDate(d.rentStart), size);
    F.labeled('Expiration:', fmtDate(d.end), size);
    d.renewal ? F.labeled('Renewal options:', d.renewal, size) : F.labeled('Renewal options:', NA, size);
    F.gap(5);
    F.text('Financial', { font: F.f.bold, size: 10.5, color: INK2, spaceAfter: 1 });
    F.labeled('Lease type:', d.nnn ? 'Triple Net (NNN)' : 'CAM Pass-Through (standard)', size);
    F.labeled('Base Rent / month:', fmtMoney(d.rent), size);
    d.escalation ? F.labeled('Escalation:', d.escalation, size) : F.labeled('Escalation:', NA, size);
    F.labeled('Estimated CAM / month:', fmtMoney(d.cam), size);
    F.labeled('Shared utilities / month:', fmtMoney(d.util), size);
    F.labeled('Direct utilities:', d.directUtil || NA, size);
    F.labeled('Security Deposit:', fmtMoney(d.deposit), size);
    F.labeled('First month Rent & CAM:', fmtMoney(d.firstMonth), size);
    F.labeled('Good Faith Deposit credit:', d.gfd ? '$100.00 credited at signing' : NA, size);
    F.gap(5);
    F.text('Operations & Notices', { font: F.f.bold, size: 10.5, color: INK2, spaceAfter: 1 });
    F.labeled('Permitted Use:', d.use, size);
    F.labeled('Delivery condition:', d.delivery, size);
    d.exclusive ? F.labeled('Exclusive use:', d.exclusive, size) : F.labeled('Exclusive use:', NA, size);
    d.stipulations ? F.labeled('Special stipulations:', d.stipulations, size) : F.labeled('Special stipulations:', NA, size);
    F.labeled('Tenant notices:', d.noticeName + ', ' + d.noticeAddr + (d.noticeEmail ? ', ' + d.noticeEmail : ''), size);
    F.gap(5);
    F.text('Exhibits', { font: F.f.bold, size: 10.5, color: INK2, spaceAfter: 1 });
    d.exhibits.length
      ? d.exhibits.forEach(ex => F.labeled('Included:', ex, size))
      : F.labeled('Exhibits:', 'None attached', size);

    // ---------- page 2: CAM & cost calculations ----------
    F.newPage();
    F.title('CAM & Cost Calculations');
    F.sub(`Suite ${d.unit} - ${BUILDING}, ${ADDR}`);
    F.gap(2);
    F.text(`Figures from the ${fmtDate(vacData.asOf)} pricing data (data/vacancies.json). CAM and shared-utility ` +
           'amounts are estimates, collected monthly and subject to the annual review and reconciliation ' +
           'described in Article 1 of the Standard Lease Terms.', { size: 8.5, color: MUTE, lineHeight: 12 });
    F.rule();

    F.section('Proportionate Share');
    F.labeled('Suite rentable area:', fmtInt(d.sqft) + ' sq ft');
    F.labeled('Building rentable area:', fmtInt(vacData.buildingSqft) + ' sq ft');
    F.labeled('Proportionate Share:', `${fmtInt(d.sqft)} / ${fmtInt(vacData.buildingSqft)} = ${d.share.toFixed(2)}%`);

    F.section('Monthly Recurring Costs');
    const cols = [
      { x: M_LEFT,       w: 190, align: 'left'  },
      { x: M_LEFT + 200, w: 90,  align: 'right' },
      { x: M_LEFT + 300, w: 90,  align: 'right' },
      { x: M_LEFT + 400, w: 90,  align: 'right' },
    ];
    const perSq = v => d.sqft ? '$' + (v / d.sqft).toFixed(2) : '-';
    F.tableRow(['', 'Monthly', 'Annual', 'Per sq ft / mo'], cols, { bold: true, size: 9, color: INK2 });
    F.rule(LINE, 0.5);
    F.tableRow(['Base Rent', fmtMoney(d.rent), fmtMoney(d.rent * 12), perSq(d.rent)], cols);
    F.tableRow(['Estimated CAM Charges', fmtMoney(d.cam), fmtMoney(d.cam * 12), perSq(d.cam)], cols);
    F.tableRow(['Shared utilities (est.)', fmtMoney(d.util), fmtMoney(d.util * 12), perSq(d.util)], cols);
    F.rule(LINE, 0.5);
    const allIn = d.rent + d.cam + d.util;
    F.tableRow(['Total monthly (all-in)', fmtMoney(allIn), fmtMoney(allIn * 12), perSq(allIn)], cols, { bold: true });

    F.section('CAM Detail');
    F.labeled('Estimated CAM / month:', fmtMoney(d.cam));
    F.labeled('CAM rate:', d.sqft ? `${fmtMoney(d.cam)} / ${fmtInt(d.sqft)} sq ft = $${(d.cam / d.sqft).toFixed(3)} per sq ft per month` : '-');
    F.labeled('Estimated CAM / year:', fmtMoney(d.cam * 12));
    F.text('CAM Charges cover the suite\'s Proportionate Share of taxes, insurance, maintenance and ' +
           'common-area utilities, management, and qualifying capital improvements, as defined in Article 1 ' +
           'of the Standard Lease Terms. Estimated payments are reconciled annually against actual costs.',
           { size: 8.5, color: MUTE, lineHeight: 12 });

    F.section('Due at Signing');
    const cols2 = [ { x: M_LEFT, w: 290, align: 'left' }, { x: M_LEFT + 300, w: 120, align: 'right' } ];
    F.tableRow(['First month Rent & CAM', fmtMoney(d.firstMonth)], cols2);
    F.tableRow(['Security Deposit', fmtMoney(d.deposit)], cols2);
    if (d.gfd) F.tableRow(['Less: Good Faith Deposit credit', '-' + fmtMoney(100)], cols2);
    F.rule(LINE, 0.5);
    F.tableRow(['Total due at signing', fmtMoney(d.firstMonth + d.deposit - (d.gfd ? 100 : 0))], cols2, { bold: true });

    F.stampFooters('Record');
    doc.setTitle(`Lease checklist & CAM record - ${d.tenant} - Suite ${d.unit}`);
    return doc.save();
  }

  // ============================================================
  // Wiring
  // ============================================================
  function download(bytes, filename, linkId) {
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    const a = $(linkId);
    a.href = url; a.download = filename;
    return a;
  }

  const slug = s => s.replace(/[^\w]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'tenant';

  async function generate() {
    const box = $('builder-errors');
    const d = collect();
    const errs = validate(d);
    if (errs.length) {
      box.innerHTML = '<strong>Fix before generating:</strong><br>' + errs.map(e => '&bull; ' + e).join('<br>');
      box.classList.remove('hidden');
      box.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    box.classList.add('hidden');
    const btn = $('generate');
    btn.disabled = true; btn.textContent = 'Generating…';
    try {
      const [leaseBytes, recordBytes] = [await buildLeasePackage(d), await buildRecord(d)];
      const stamp = new Date().toISOString().slice(0, 10);
      const a1 = download(leaseBytes, `CourthouseSquare_Lease_${d.unit}_${slug(d.tenant)}_${stamp}.pdf`, 'dl-lease');
      const a2 = download(recordBytes, `LeaseChecklist_CAM_${d.unit}_${slug(d.tenant)}_${stamp}.pdf`, 'dl-record');
      $('builder-output').classList.remove('hidden');
      a1.click();
      setTimeout(() => a2.click(), 500);
    } catch (err) {
      box.textContent = 'Generation failed: ' + err.message;
      box.classList.remove('hidden');
    } finally {
      btn.disabled = false; btn.textContent = 'Generate lease package & record';
    }
  }

  // ---------- form behavior ----------
  function recomputeShare() {
    const sqft = num('f-sqft');
    if (sqft && vacData.buildingSqft) $('f-share').value = (sqft / vacData.buildingSqft * 100).toFixed(2);
  }
  function recomputeFirstMonth() {
    $('f-first-month').value = (num('f-rent') + num('f-cam') + num('f-util')).toFixed(2);
  }
  function recomputeEnd() {
    const months = $('f-term').value;
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(val('f-start'));
    if (months === 'custom' || !m) return;
    const dt = new Date(+m[1], +m[2] - 1 + parseInt(months, 10), +m[3]);
    dt.setDate(dt.getDate() - 1);
    const pad = n => String(n).padStart(2, '0');
    $('f-end').value = `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
  }

  function onSuiteChange() {
    const s = vacData.suites.find(x => x.unit === val('f-suite'));
    if (!s) return;
    $('f-sqft').value = s.sqft;
    $('f-rent').value = s.rent.toFixed(2);
    $('f-cam').value = s.cam.toFixed(2);
    $('f-util').value = s.utilities.toFixed(2);
    recomputeShare(); recomputeFirstMonth();
  }

  async function init() {
    try {
      const raw = await fetch('/data/vacancies.json', { cache: 'no-cache' }).then(r => r.json());
      vacData = Array.isArray(raw) ? { asOf: '', buildingSqft: 6630, suites: raw } : raw;
    } catch (e) { /* form still usable with manual numbers */ }
    const sel = $('f-suite');
    for (const s of vacData.suites) {
      const o = document.createElement('option');
      o.value = s.unit;
      o.textContent = `${s.unit} - ${fmtInt(s.sqft)} sq ft`;
      sel.appendChild(o);
    }
    $('building-sqft-note').textContent = fmtInt(vacData.buildingSqft || 0);
    sel.addEventListener('change', onSuiteChange);
    $('f-sqft').addEventListener('input', recomputeShare);
    ['f-rent', 'f-cam', 'f-util'].forEach(id => $(id).addEventListener('input', recomputeFirstMonth));
    ['f-start', 'f-term'].forEach(id => $(id).addEventListener('change', recomputeEnd));
    $('f-end').addEventListener('input', () => { $('f-term').value = 'custom'; });
    $('generate').addEventListener('click', generate);
  }

  init();
})();
