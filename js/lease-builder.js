/* Lease Builder — staff tool.
 *
 * Reads the checklist form on /lease/builder.html and generates, entirely in
 * the browser (vendored pdf-lib + fontkit, no server):
 *
 *   1. The signature-ready lease package: a filled Lease Terms Sheet in the
 *      midcentury house style (Jost display / Libre Baskerville text),
 *      followed by any attached exhibits, followed by the pages of the
 *      posted standard lease (/lease/lease.pdf). Optional items left blank
 *      are treated as not applicable and omitted; the document reflows.
 *
 *   2. A two-page record: the completed checklist on page one (omissions
 *      documented), the suite's full CAM & cost calculations on page two.
 *      Always exactly two pages: the layout steps down type sizes and
 *      truncates free-text overflow rather than spill to page three.
 *
 * Also: import (drag a filled Letter of Intent PDF, a previously generated
 * record PDF, or a .json deal file to prefill), localStorage draft autosave,
 * a deal.json embedded inside every record PDF (making any record
 * re-loadable), mid-month proration, and invisible e-sign anchor tags
 * (/sn1/../ds3/) at the signature lines for DocuSign-style auto-placement.
 */
(function () {
  'use strict';

  const { PDFDocument, StandardFonts, rgb } = PDFLib;

  // ---------- identity ----------
  // Fetched from /data/identity.json at init (single source of truth, shared
  // with tools/build_lease_docs.py). These literals are the offline fallback
  // and are cross-checked against identity.json by tools/check_site.py.
  const IDENT = {
    entity: 'Courthouse Square Vashon LLC',
    entityLong: 'Courthouse Square Vashon LLC, a Washington Limited Liability Company',
    building: 'Courthouse Square',
    buildingAddress: '19001 Vashon Hwy SW, Vashon Island, WA 98070',
    noticeAddress: '20704 Vashon Highway SW, Vashon Island, WA 98070',
    noticeCareOf: 'c/o Bangasser & Associates, Inc.',
    email: 'leasing@courthousesquarevashon.com',
    version: 'Version 1.5',
    versionDate: 'June 29, 2026',
  };
  const landlordNotice = () =>
    `${IDENT.entity}, ${IDENT.noticeCareOf}, ${IDENT.noticeAddress}. Courtesy email: ${IDENT.email}`;
  const NOTICE_SERVICE =
    'All notices under this Lease shall be in writing and effective (i) when delivered in person or via ' +
    'overnight courier to the other party, or (ii) three (3) days after being sent by registered or ' +
    'certified mail to the other party at the address set forth in this Section.';

  // ---------- palette ----------
  const C = h => rgb(((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255);
  const INK  = C(0x1e3128);
  const INK2 = C(0x243b2f);
  const MUTE = C(0x4a443b);
  const LINE = C(0xbcd0c2);
  const RUST = C(0xb4521f);
  const WHITE = rgb(1, 1, 1);

  // ---------- page geometry ----------
  const PAGE_W = 612, PAGE_H = 792;
  const M_LEFT = 61.2, M_RIGHT = 61.2, M_TOP = 58, M_BOTTOM = 76;
  const BODY_W = PAGE_W - M_LEFT - M_RIGHT;

  // ---------- state ----------
  let vacData = { asOf: '', buildingSqft: 6630, suites: [] };
  let fontBytes = null;      // fetched TTFs, shared across generations
  const exhibitUploads = {}; // key -> {name, bytes}
  const exhibitAuto = {};    // key -> url found on the site

  const $ = id => document.getElementById(id);
  const val = id => ($(id) ? $(id).value.trim() : '');
  const num = id => { const n = parseFloat(val(id)); return isFinite(n) ? n : 0; };

  const fmtMoney = n => '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtInt   = n => Number(n).toLocaleString('en-US');
  const slug = s => s.replace(/[^\w]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'tenant';

  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    if (!m) return iso || '';
    return new Date(+m[1], +m[2] - 1, +m[3])
      .toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  }

  function safe(s) {
    return String(s == null ? '' : s)
      .replace(/[‘’]/g, "'").replace(/[“”]/g, '"')
      .replace(/–/g, '-').replace(/—/g, '--').replace(/…/g, '...')
      .replace(/[^\x00-\xFF]/g, '?');
  }

  // Letterspaced caps for display type. Drawn only via Flow.line() (no wrap).
  const tracked = s => s.toUpperCase().split('').join(' ').replace(/ {3}/g, '   ');

  // Mid-month proration: portion of the rent-commencement month actually occupied.
  function prorationFor(rentStart, monthly) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(rentStart || '');
    if (!m) return null;
    const day = +m[3];
    if (day === 1) return null;
    const dim = new Date(+m[1], +m[2], 0).getDate();
    const days = dim - day + 1;
    const monthName = new Date(+m[1], +m[2] - 1, day)
      .toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    return { days, dim, monthName, amount: Math.round(monthly * days / dim * 100) / 100 };
  }

  // ============================================================
  // Fonts: midcentury pairing, matching tools/build_lease_docs.py
  // ============================================================
  async function loadFontBytes() {
    if (fontBytes) return fontBytes;
    const names = ['Jost-500', 'Jost-600', 'LibreBaskerville-400', 'LibreBaskerville-700', 'LibreBaskerville-Italic'];
    const all = await Promise.all(names.map(n =>
      fetch(`/fonts/${n}.ttf`).then(r => { if (!r.ok) throw new Error(n); return r.arrayBuffer(); })));
    fontBytes = Object.fromEntries(names.map((n, i) => [n, all[i]]));
    return fontBytes;
  }

  async function makeDoc() {
    const doc = await PDFDocument.create();
    try {
      if (!window.fontkit) throw new Error('fontkit missing');
      doc.registerFontkit(window.fontkit);
      const fb = await loadFontBytes();
      return { doc, fonts: {
        display: await doc.embedFont(fb['Jost-600'], { subset: true }),
        label:   await doc.embedFont(fb['Jost-500'], { subset: true }),
        body:    await doc.embedFont(fb['LibreBaskerville-400'], { subset: true }),
        bold:    await doc.embedFont(fb['LibreBaskerville-700'], { subset: true }),
        italic:  await doc.embedFont(fb['LibreBaskerville-Italic'], { subset: true }),
      }};
    } catch (e) {
      // Offline/older-browser fallback: standard fonts, same layout.
      return { doc, fonts: {
        display: await doc.embedFont(StandardFonts.HelveticaBold),
        label:   await doc.embedFont(StandardFonts.HelveticaBold),
        body:    await doc.embedFont(StandardFonts.TimesRoman),
        bold:    await doc.embedFont(StandardFonts.TimesRomanBold),
        italic:  await doc.embedFont(StandardFonts.TimesRomanItalic),
      }};
    }
  }

  // ============================================================
  // Flow: cursor layout engine
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

    // Single line, no wrapping (used for tracked display type).
    line(str, o = {}) {
      const font = o.font || this.f.body, size = o.size || 10;
      const lh = o.lineHeight || size * 1.35;
      this.ensure(lh + (o.spaceAfter || 0));
      this.y -= lh;
      this.page.drawText(safe(str), { x: o.x || M_LEFT, y: this.y, size, font, color: o.color || INK });
      this.y -= (o.spaceAfter || 0);
    }

    text(str, o = {}) {
      const font = o.font || this.f.body, size = o.size || 9.2;
      const width = o.width || BODY_W, x = o.x || M_LEFT;
      const lh = o.lineHeight || size * 1.55;
      const lines = this.wrap(str, font, size, width);
      this.ensure(lines.length * lh + (o.spaceAfter || 0));
      for (const ln of lines) {
        this.y -= lh;
        this.page.drawText(ln, { x, y: this.y, size, font, color: o.color || INK });
      }
      this.y -= (o.spaceAfter || 0);
    }

    rule(color = LINE, thickness = 0.6, o = {}) {
      this.ensure(10); this.y -= o.before ?? 6;
      this.page.drawLine({ start: { x: M_LEFT, y: this.y }, end: { x: o.x2 || PAGE_W - M_RIGHT, y: this.y }, thickness, color });
      this.y -= o.after ?? 4;
    }
    dualRule() {
      this.gap(5);
      this.page.drawLine({ start: { x: M_LEFT, y: this.y }, end: { x: PAGE_W - M_RIGHT, y: this.y }, thickness: 2.2, color: INK });
      this.y -= 3.2;
      this.page.drawLine({ start: { x: M_LEFT, y: this.y }, end: { x: PAGE_W - M_RIGHT, y: this.y }, thickness: 0.7, color: RUST });
      this.gap(10);
    }
    tick() { // short rust bar, the house signature
      this.ensure(18);
      this.page.drawLine({ start: { x: M_LEFT, y: this.y }, end: { x: M_LEFT + 40, y: this.y }, thickness: 3, color: RUST });
      this.gap(14);
    }

    title(str) { this.line(tracked(str), { font: this.f.display, size: 21, lineHeight: 26, spaceAfter: 4 }); }
    sub(str)   { this.text(str, { font: this.f.label, size: 8.6, color: MUTE, lineHeight: 12.5 }); }

    // Numbered section heading: rust index · tracked caps, thin rule.
    section(str) {
      this.ensure(50); this.gap(14);
      const m = /^(\d+)\.\s*(.*)$/.exec(str);
      const idx = m ? m[1] : null, rest = m ? m[2] : str;
      const disp = rest.length <= 34 ? tracked(rest) : rest.toUpperCase();
      const lh = 15;
      this.y -= lh;
      let x = M_LEFT;
      if (idx) {
        this.page.drawText(idx, { x, y: this.y, size: 11, font: this.f.display, color: RUST });
        x += this.f.display.widthOfTextAtSize(idx, 11) + 8;
      }
      this.page.drawText(safe(disp), { x, y: this.y, size: 10.2, font: this.f.label, color: INK2 });
      this.y -= 5;
      this.page.drawLine({ start: { x: M_LEFT, y: this.y }, end: { x: PAGE_W - M_RIGHT, y: this.y }, thickness: 0.5, color: LINE });
      this.y -= 6;
    }

    labeled(label, value, o = {}) {
      const size = o.size || 9.2, labelW = o.labelW || 158;
      const lh = size * 1.5;
      const vLines = this.wrap(value || '', this.f.body, size, BODY_W - labelW - 6);
      const h = Math.max(1, vLines.length) * lh + 3;
      this.ensure(h);
      const yStart = this.y - lh;
      this.page.drawText(safe(label).toUpperCase(), { x: M_LEFT, y: yStart, size: size * 0.82, font: this.f.label, color: INK });
      let yy = this.y;
      for (const ln of vLines) {
        yy -= lh;
        this.page.drawText(ln, { x: M_LEFT + labelW + 6, y: yy, size, font: this.f.body, color: INK });
      }
      this.y -= h;
    }

    // Signature line with invisible e-sign anchor tags for auto-placement.
    sigLine(label, o = {}) {
      const size = 9.2, lh = 22, labelW = o.labelW || 118;
      this.ensure(lh);
      this.y -= lh;
      this.page.drawText(safe(label).toUpperCase(), { x: M_LEFT, y: this.y, size: 7.8, font: this.f.label, color: INK });
      const x1 = M_LEFT + labelW, x2 = o.short ? M_LEFT + labelW + 160 : PAGE_W - M_RIGHT;
      this.page.drawLine({ start: { x: x1, y: this.y - 2 }, end: { x: x2, y: this.y - 2 }, thickness: 0.8, color: INK });
      if (o.anchor) {
        // White 4pt text: invisible on paper, findable by DocuSign/Adobe Sign
        // "auto-place by anchor" ( /sn1/, /ds1/, ... ).
        this.page.drawText(o.anchor, { x: x1 + 4, y: this.y + 1, size: 4, font: this.f.body, color: WHITE });
      }
    }

    tableRow(cells, cols, o = {}) {
      const size = o.size || 9.2, lh = size * 1.65;
      this.ensure(lh);
      this.y -= lh;
      cells.forEach((cell, i) => {
        const font = o.bold ? this.f.bold : this.f.body;
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
        pg.drawLine({ start: { x: M_LEFT, y: 44.6 }, end: { x: M_LEFT + 18, y: 44.6 }, thickness: 1.4, color: RUST });
        pg.drawText(safe(this.footerLeft).toUpperCase(), { x: M_LEFT, y: 36, size: 6.8, font: this.f.label, color: MUTE });
        const t = `${label ? label.toUpperCase() + ' - ' : ''}PAGE ${i + 1} OF ${n}`;
        pg.drawText(t, { x: PAGE_W - M_RIGHT - this.f.label.widthOfTextAtSize(t, 6.8), y: 36, size: 6.8, font: this.f.label, color: MUTE });
      });
    }
  }

  // ============================================================
  // Collect + validate
  // ============================================================
  const FIELD_IDS = [
    'f-tenant', 'f-tenant-addr', 'f-guarantor', 'f-guarantor-addr',
    'f-suite', 'f-unit-manual', 'f-sqft', 'f-share',
    'f-start', 'f-rent-start', 'f-term', 'f-end', 'f-renewal',
    'f-rent', 'f-cam', 'f-util', 'f-escalation', 'f-deposit', 'f-direct-util', 'f-first-month',
    'f-use', 'f-delivery', 'f-exclusive', 'f-stipulations',
    'f-notice-name', 'f-notice-addr', 'f-notice-email',
    'f-ti-allowance', 'f-ti-complete', 'f-ti-scope', 'f-ex-e',
  ];
  const CHECK_IDS = ['f-gfd', 'f-ex-a'];

  function unitValue() {
    const sel = val('f-suite');
    return sel === '__manual__' ? val('f-unit-manual').toUpperCase() : sel;
  }

  function collect() {
    const unit = unitValue();
    const suiteAddr = unit ? `19001 Vashon Hwy SW, Suite ${unit}, Vashon Island, WA 98070` : IDENT.buildingAddress;
    const d = {
      tenant: val('f-tenant'),
      tenantAddr: val('f-tenant-addr') || suiteAddr,
      guarantor: val('f-guarantor'),
      guarantorAddr: val('f-guarantor-addr'),
      unit, suiteAddr,
      sqft: num('f-sqft'),
      share: num('f-share'),
      calcShare: vacData.buildingSqft ? Math.round(num('f-sqft') / vacData.buildingSqft * 10000) / 100 : 0,
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
    d.shareOverridden = d.calcShare > 0 && Math.abs(d.share - d.calcShare) > 0.011;
    d.proration = prorationFor(d.rentStart, d.rent + d.cam + d.util);
    const pct = /(\d+(?:\.\d+)?)\s*%/.exec(d.escalation || '');
    d.escalationPct = pct ? parseFloat(pct[1]) : null;
    d.exhibits = [];
    const att = k => exhibitUploads[k] ? 'attached' : (exhibitAuto[k] ? 'attached' : 'attached separately');
    if (d.exA)      d.exhibits.push(`Exhibit A: Legal Description, ${att('a')}`);
    if (d.guarantor) d.exhibits.push(`Exhibit B: Unconditional Guaranty of Lease${exhibitUploads.b ? ', attached' : ''}`);
    if (d.hasTI)    d.exhibits.push('Exhibit C: Tenant Work Letter (terms below)');
    if (d.nnn)      d.exhibits.push(`Exhibit D: NNN Lease Amendment, ${exhibitUploads.d ? 'attached' : 'attached separately'}`);
    if (d.exE)      d.exhibits.push('Exhibit E: ' + d.exE);
    return d;
  }

  function validate(d) {
    const errs = [];
    if (!d.tenant) errs.push('Tenant legal name is required.');
    if (!d.unit)   errs.push('Choose a suite (or pick "Other / manual" and enter the unit).');
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
  async function exhibitCover(doc, fonts, letter, title) {
    const F = new Flow(doc, fonts, `${IDENT.entity}    ${IDENT.version}, ${IDENT.versionDate}`);
    F.gap(180);
    F.tick();
    F.line(tracked('Exhibit ' + letter), { font: fonts.display, size: 24, lineHeight: 30, spaceAfter: 8 });
    F.text(title, { font: fonts.italic, size: 11, color: INK2 });
    return F;
  }

  async function appendExhibit(doc, fonts, letter, title, bytes) {
    (await exhibitCover(doc, fonts, letter, title)).stampFooters('Exhibit ' + letter);
    const src = await PDFDocument.load(bytes, { ignoreEncryption: true });
    (await doc.copyPages(src, src.getPageIndices())).forEach(p => doc.addPage(p));
  }

  function firstMonthLabel(d) {
    return d.proration
      ? `First payment (prorated, ${d.proration.days}/${d.proration.dim} days of ${d.proration.monthName})`
      : 'First month (Rent, CAM & shared utilities)';
  }

  async function buildLeasePackage(d) {
    const { doc, fonts } = await makeDoc();
    const F = new Flow(doc, fonts, `${IDENT.entity}    ${IDENT.version}, ${IDENT.versionDate}`);

    F.tick();
    F.title('Lease Terms Sheet');
    F.sub(`${IDENT.entity} - ${IDENT.buildingAddress}`);
    F.sub(`${IDENT.version} - ${IDENT.versionDate}`);
    F.gap(6);
    F.text('The specific, negotiated terms of this lease. Where this Terms Sheet is silent, the ' +
           'Standard Lease Terms and the Definitions & Glossary (attached, and posted at ' +
           'courthousesquarevashon.com/lease/) control; in the event of a conflict, this Terms Sheet prevails.',
           { font: fonts.italic, size: 8, color: MUTE, lineHeight: 11.5 });
    F.dualRule();

    F.section('1. The Parties');
    F.labeled('Landlord:', IDENT.entityLong);
    F.labeled('Tenant (entity):', d.tenant);
    F.labeled('Tenant address:', d.tenantAddr);
    if (d.guarantor) F.labeled('Guarantor(s):', d.guarantor);

    F.section('2. The Premises');
    F.labeled('Property / Building:', IDENT.building);
    F.labeled('Address / Suite:', d.suiteAddr);
    if (d.sqft)  F.labeled('Approximate square footage:', fmtInt(d.sqft));
    F.labeled('Legal Description:', 'See Exhibit A, attached');
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
    if (d.firstMonth) F.labeled(firstMonthLabel(d) + ':', fmtMoney(d.firstMonth));
    if (d.gfd) F.text('The refundable $100 Good Faith Deposit submitted with the Letter of Intent is credited toward the amounts due upon signing.',
                      { font: fonts.italic, size: 8, color: MUTE, lineHeight: 11.5 });

    F.section('5. Operations & Special Conditions');
    F.labeled('Permitted Use:', d.use);
    F.labeled('Delivery condition:', d.delivery);
    if (d.exclusive)    F.labeled('Exclusive use:', d.exclusive);
    if (d.stipulations) F.labeled('Special stipulations:', d.stipulations);

    F.section('6. Notices');
    F.text(NOTICE_SERVICE, { size: 9.2 });
    F.gap(2);
    F.text('Notice to Landlord: ' + landlordNotice(), { size: 9.2 });
    F.gap(2);
    F.labeled('Tenant notice name:', d.noticeName);
    F.labeled('Tenant notice address:', d.noticeAddr);
    if (d.noticeEmail) F.labeled('Tenant courtesy email:', d.noticeEmail);

    F.section('7. Incorporation and Merger');
    F.text(`This Lease Terms Sheet, together with its Exhibits, the Standard Lease Terms, and the Definitions & ` +
           `Glossary (${IDENT.version}, ${IDENT.versionDate}, posted at courthousesquarevashon.com/lease/), constitutes ` +
           'the entire Commercial Lease Agreement and supersedes the Letter of Intent. In the event of any ' +
           'conflict between this Terms Sheet and the online Standard Lease Terms or Definitions, this Terms ' +
           'Sheet prevails.', { size: 9.2 });

    F.section('8. Index of Exhibits');
    if (d.exhibits.length) {
      for (const ex of d.exhibits) F.text('-  ' + ex, { size: 9.2, lineHeight: 15 });
    } else {
      F.text('No exhibits are attached to this Lease Terms Sheet.', { font: fonts.italic, size: 9.2 });
    }

    if (d.hasTI) {
      F.section('Exhibit C: Tenant Work Letter');
      if (d.tiAllowance) F.labeled('TI allowance:', d.tiAllowance.startsWith('$') ? d.tiAllowance : '$' + d.tiAllowance);
      if (d.tiComplete)  F.labeled('Substantial completion by:', fmtDate(d.tiComplete));
      if (d.tiScope)     F.labeled("Scope of Tenant's Work:", d.tiScope);
    }

    F.ensure(210);
    F.section('Signatures');
    F.gap(4);
    F.text('LANDLORD: ' + IDENT.entity, { font: fonts.bold, size: 9.2 });
    F.sigLine('Signature:', { anchor: '/sn1/' }); F.sigLine('Printed name / title:'); F.sigLine('Date:', { short: true, anchor: '/ds1/' });
    F.gap(10);
    F.text('TENANT: ' + d.tenant, { font: fonts.bold, size: 9.2 });
    F.sigLine('Signature:', { anchor: '/sn2/' }); F.sigLine('Printed name / title:'); F.sigLine('Date:', { short: true, anchor: '/ds2/' });
    if (d.guarantor) {
      F.gap(10);
      F.text('PERSONAL GUARANTOR: ' + d.guarantor, { font: fonts.bold, size: 9.2 });
      F.sigLine('Signature:', { anchor: '/sn3/' }); F.sigLine('Printed name / title:'); F.sigLine('Date:', { short: true, anchor: '/ds3/' });
      F.labeled('Guarantor home address:', d.guarantorAddr || '');
    }

    F.stampFooters('Lease Terms Sheet');

    // Exhibits with real attachments come right after the Terms Sheet.
    const exOrder = [
      ['a', 'A', 'Legal Description of the Premises'],
      ['b', 'B', 'Unconditional Guaranty of Lease'],
      ['d', 'D', 'NNN Lease Amendment'],
    ];
    for (const [key, letter, title] of exOrder) {
      const applies = (key === 'a' && d.exA) || (key === 'b' && d.guarantor) || (key === 'd' && d.nnn);
      if (!applies) continue;
      let bytes = exhibitUploads[key] && exhibitUploads[key].bytes;
      if (!bytes && exhibitAuto[key]) {
        try { bytes = await fetch(exhibitAuto[key]).then(r => r.ok ? r.arrayBuffer() : null); } catch (e) {}
      }
      if (bytes) await appendExhibit(doc, fonts, letter, title, bytes);
    }

    // Then the posted standard lease (Standard Lease Terms + Definitions).
    const stdBytes = await fetch('/lease/lease.pdf').then(r => {
      if (!r.ok) throw new Error('Could not load /lease/lease.pdf');
      return r.arrayBuffer();
    });
    const std = await PDFDocument.load(stdBytes);
    (await doc.copyPages(std, std.getPageIndices())).forEach(p => doc.addPage(p));

    doc.setTitle(`Commercial Lease - ${IDENT.entity} - ${d.tenant} - Suite ${d.unit}`);
    return doc.save();
  }

  // ============================================================
  // Document 2: two-page record (guaranteed two pages)
  // ============================================================
  const clip = (s, n) => (s && s.length > n) ? s.slice(0, n - 1).trimEnd() + '… (full text in lease)' : s;

  async function buildRecordAt(d, tier) {
    // tier 0 = roomy, 1 = compact, 2 = compact + clipped free text
    const size  = [9.0, 8.4, 8.0][tier];
    const labelW = [168, 158, 150][tier];
    const dd = tier >= 2 ? { ...d,
      renewal: clip(d.renewal, 110), escalation: clip(d.escalation, 110),
      stipulations: clip(d.stipulations, 150), exclusive: clip(d.exclusive, 110),
      directUtil: clip(d.directUtil, 110), exE: clip(d.exE, 80) } : d;

    const { doc, fonts } = await makeDoc();
    const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    const F = new Flow(doc, fonts, `${IDENT.entity}    Lease preparation record    Generated ${today}`);
    const NA = 'Not applicable - omitted from the lease';
    const o = { size, labelW };
    const head = t => { F.gap(4); F.line(tracked(t), { font: fonts.label, size: 8.8, color: INK2, lineHeight: 13, spaceAfter: 1 }); };

    // ---------- page 1: checklist ----------
    F.tick();
    F.title('Lease Checklist');
    F.sub(`${dd.tenant} - Suite ${dd.unit} - prepared ${today}`);
    F.gap(2);
    F.text('Record of the information used to prepare the lease. Items marked "not applicable" were omitted ' +
           'from the generated Lease Terms Sheet. This PDF carries the deal data (deal.json); drop it back ' +
           'onto the Lease Builder to reload and regenerate.', { font: fonts.italic, size: 7.8, color: MUTE, lineHeight: 11 });
    F.rule();

    head('Parties');
    F.labeled('Tenant legal name:', dd.tenant, o);
    F.labeled('Tenant address:', dd.tenantAddr, o);
    F.labeled('Guarantor:', dd.guarantor ? dd.guarantor + (dd.guarantorAddr ? ' - ' + dd.guarantorAddr : '') : NA, o);
    head('Premises & Term');
    F.labeled('Suite:', `${dd.unit} - ${dd.suiteAddr}`, o);
    F.labeled('Approximate sq ft:', fmtInt(dd.sqft), o);
    F.labeled('Proportionate Share:', dd.share.toFixed(2) + '%' + (dd.shareOverridden ? ` (negotiated; calculated ${dd.calcShare.toFixed(2)}%)` : ''), o);
    F.labeled('Start / Rent start:', fmtDate(dd.start) + '  /  ' + fmtDate(dd.rentStart), o);
    F.labeled('Expiration:', fmtDate(dd.end), o);
    F.labeled('Renewal options:', dd.renewal || NA, o);
    head('Financial');
    F.labeled('Lease type:', dd.nnn ? 'Triple Net (NNN)' : 'CAM Pass-Through (standard)', o);
    F.labeled('Base Rent / month:', fmtMoney(dd.rent), o);
    F.labeled('Escalation:', dd.escalation || NA, o);
    F.labeled('Estimated CAM / month:', fmtMoney(dd.cam), o);
    F.labeled('Shared utilities / month:', fmtMoney(dd.util), o);
    F.labeled('Direct utilities:', dd.directUtil || NA, o);
    F.labeled('Security Deposit:', fmtMoney(dd.deposit), o);
    F.labeled(firstMonthLabel(dd) + ':', fmtMoney(dd.firstMonth), o);
    F.labeled('Good Faith Deposit credit:', dd.gfd ? '$100.00 credited at signing' : NA, o);
    head('Operations & Notices');
    F.labeled('Permitted Use:', dd.use, o);
    F.labeled('Delivery condition:', dd.delivery, o);
    F.labeled('Exclusive use:', dd.exclusive || NA, o);
    F.labeled('Special stipulations:', dd.stipulations || NA, o);
    F.labeled('Tenant notices:', dd.noticeName + ', ' + dd.noticeAddr + (dd.noticeEmail ? ', ' + dd.noticeEmail : ''), o);
    head('Exhibits');
    if (dd.exhibits.length) dd.exhibits.forEach(ex => F.labeled('Included:', ex, o));
    else F.labeled('Exhibits:', 'None attached', o);

    const page1Count = F.pages.length;

    // ---------- page 2: CAM & cost calculations ----------
    F.newPage();
    F.tick();
    F.title('CAM & Cost Calculations');
    F.sub(`Suite ${d.unit} - ${IDENT.building}, ${IDENT.buildingAddress}`);
    F.gap(2);
    F.text(`Figures from the ${fmtDate(vacData.asOf) || 'current'} pricing data (data/vacancies.json). CAM and ` +
           'shared-utility amounts are estimates, collected monthly and subject to the annual review and ' +
           'reconciliation described in Article 1 of the Standard Lease Terms.',
           { font: fonts.italic, size: 7.8, color: MUTE, lineHeight: 11 });
    F.rule();

    F.section('Proportionate Share');
    F.labeled('Suite rentable area:', fmtInt(d.sqft) + ' sq ft', o);
    F.labeled('Building rentable area:', fmtInt(vacData.buildingSqft) + ' sq ft', o);
    F.labeled('Calculated share:', `${fmtInt(d.sqft)} / ${fmtInt(vacData.buildingSqft)} = ${d.calcShare.toFixed(2)}%`, o);
    if (d.shareOverridden)
      F.labeled('Share in this Lease:', `${d.share.toFixed(2)}% (negotiated; differs from calculated)`, o);

    F.section('Monthly Recurring Costs');
    const cols = [
      { x: M_LEFT,       w: 190, align: 'left'  },
      { x: M_LEFT + 200, w: 90,  align: 'right' },
      { x: M_LEFT + 300, w: 90,  align: 'right' },
      { x: M_LEFT + 400, w: 90,  align: 'right' },
    ];
    const perSq = v => d.sqft ? '$' + (v / d.sqft).toFixed(2) : '-';
    F.tableRow(['', 'MONTHLY', 'ANNUAL', 'PER SQ FT / MO'], cols, { size: 7.6, color: INK2, bold: false });
    F.rule(LINE, 0.5);
    F.tableRow(['Base Rent', fmtMoney(d.rent), fmtMoney(d.rent * 12), perSq(d.rent)], cols, { size });
    F.tableRow(['Estimated CAM Charges', fmtMoney(d.cam), fmtMoney(d.cam * 12), perSq(d.cam)], cols, { size });
    F.tableRow(['Shared utilities (est.)', fmtMoney(d.util), fmtMoney(d.util * 12), perSq(d.util)], cols, { size });
    F.rule(LINE, 0.5);
    const allIn = d.rent + d.cam + d.util;
    F.tableRow(['Total monthly (all-in)', fmtMoney(allIn), fmtMoney(allIn * 12), perSq(allIn)], cols, { bold: true, size });

    F.section('CAM Detail');
    F.labeled('Estimated CAM / month:', fmtMoney(d.cam), o);
    F.labeled('CAM rate:', d.sqft ? `${fmtMoney(d.cam)} / ${fmtInt(d.sqft)} sq ft = $${(d.cam / d.sqft).toFixed(3)} per sq ft per month` : '-', o);
    F.labeled('Estimated CAM / year:', fmtMoney(d.cam * 12), o);

    if (d.escalationPct && d.start && d.end) {
      const months = (new Date(d.end) - new Date(d.start)) / (30.44 * 24 * 3600 * 1000);
      const years = Math.min(Math.max(Math.ceil(months / 12), 1), 6);
      if (years >= 2) {
        F.section('Projected Base Rent Schedule');
        const cols2 = [{ x: M_LEFT, w: 200, align: 'left' }, { x: M_LEFT + 220, w: 120, align: 'right' }];
        for (let yn = 1; yn <= years; yn++) {
          const r = d.rent * Math.pow(1 + d.escalationPct / 100, yn - 1);
          F.tableRow([`Lease year ${yn}`, fmtMoney(r) + ' / mo'], cols2, { size });
        }
        F.text(`Escalation as stated in the Terms Sheet ("${clip(d.escalation, 60)}"); schedule is illustrative.`,
               { font: fonts.italic, size: 7.6, color: MUTE, lineHeight: 10.5 });
      }
    }

    F.section('Due at Signing');
    const cols3 = [{ x: M_LEFT, w: 290, align: 'left' }, { x: M_LEFT + 300, w: 120, align: 'right' }];
    if (d.proration) {
      F.tableRow([`First payment (prorated ${d.proration.days}/${d.proration.dim} days of ${d.proration.monthName})`, fmtMoney(d.firstMonth)], cols3, { size });
      F.tableRow([`(full monthly total thereafter: ${fmtMoney(allIn)})`, ''], cols3, { size: size - 0.8, color: MUTE });
    } else {
      F.tableRow(['First month (Rent, CAM & shared utilities)', fmtMoney(d.firstMonth)], cols3, { size });
    }
    F.tableRow(['Security Deposit', fmtMoney(d.deposit)], cols3, { size });
    if (d.gfd) F.tableRow(['Less: Good Faith Deposit credit', '-' + fmtMoney(100)], cols3, { size });
    F.rule(LINE, 0.5);
    F.tableRow(['Total due at signing', fmtMoney(d.firstMonth + d.deposit - (d.gfd ? 100 : 0))], cols3, { bold: true, size });

    F.stampFooters('Record');
    doc.setTitle(`Lease checklist & CAM record - ${d.tenant} - Suite ${d.unit}`);
    return { doc, ok: page1Count === 1 && F.pages.length === 2 };
  }

  async function buildRecord(d) {
    for (let tier = 0; tier < 3; tier++) {
      const { doc, ok } = await buildRecordAt(d, tier);
      if (ok) {
        await doc.attach(new TextEncoder().encode(JSON.stringify(snapshot())), 'deal.json',
                         { mimeType: 'application/json', description: 'Lease Builder deal state' });
        return doc.save();
      }
    }
    throw new Error('The checklist does not fit the two-page record even after compacting. Shorten the special stipulations.');
  }

  // ============================================================
  // Import: LOI PDFs, record PDFs (embedded deal.json), .json files
  // ============================================================
  function snapshot() {
    return {
      v: 2,
      generator: 'chs-lease-builder',
      fields: Object.fromEntries(FIELD_IDS.map(id => [id, val(id)])),
      checks: Object.fromEntries(CHECK_IDS.map(id => [id, $(id).checked])),
      leaseType: $('f-type-nnn').checked ? 'nnn' : 'cam',
    };
  }

  function applySnapshot(s) {
    if (!s || !s.fields) return false;
    for (const [id, v] of Object.entries(s.fields)) if ($(id)) $(id).value = v;
    for (const [id, v] of Object.entries(s.checks || {})) if ($(id)) $(id).checked = !!v;
    $('f-type-nnn').checked = s.leaseType === 'nnn';
    $('f-type-cam').checked = s.leaseType !== 'nnn';
    manualToggle();
    return true;
  }

  function extractDealJson(pdfDoc) {
    try {
      const { PDFName, PDFDict, PDFArray, PDFRawStream, decodePDFRawStream } = PDFLib;
      const names = pdfDoc.context.lookup(pdfDoc.catalog.get(PDFName.of('Names')), PDFDict);
      const ef = pdfDoc.context.lookup(names.get(PDFName.of('EmbeddedFiles')), PDFDict);
      const arr = pdfDoc.context.lookup(ef.get(PDFName.of('Names')), PDFArray);
      for (let i = 0; i + 1 < arr.size(); i += 2) {
        const fname = arr.lookup(i).decodeText ? arr.lookup(i).decodeText() : '';
        const spec = arr.lookup(i + 1, PDFDict);
        const efd = spec.lookup(PDFName.of('EF'), PDFDict);
        const stream = pdfDoc.context.lookup(efd.get(PDFName.of('F')), PDFRawStream);
        if (fname.indexOf('deal.json') !== -1) {
          const bytes = decodePDFRawStream(stream).decode();
          return JSON.parse(new TextDecoder().decode(bytes));
        }
      }
    } catch (e) { /* not a record PDF */ }
    return null;
  }

  function parseMoney(s) { const n = parseFloat(String(s || '').replace(/[^0-9.]/g, '')); return isFinite(n) ? n : null; }
  function parseDateish(s) {
    const t = Date.parse(s);
    if (isNaN(t)) return null;
    const dt = new Date(t);
    const pad = n => String(n).padStart(2, '0');
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
  }

  function applyLoiFields(fields) {
    const get = n => { const f = fields[n]; return f ? String(f).trim() : ''; };
    let applied = 0;
    const set = (id, v) => { if (v) { $(id).value = v; applied++; } };
    set('f-tenant', get('loi_legal_name'));
    set('f-tenant-addr', get('loi_current_addr'));
    set('f-use', get('loi_use'));
    const start = parseDateish(get('loi_start'));
    if (start) { $('f-start').value = start; applied++; }
    const term = /(\d+)\s*(year|yr)/i.exec(get('loi_term'));
    if (term) { const mo = String(+term[1] * 12); if ([...$('f-term').options].some(o => o.value === mo)) { $('f-term').value = mo; applied++; } }
    const rent = parseMoney(get('loi_base_rent')); if (rent) { $('f-rent').value = rent.toFixed(2); applied++; }
    const cam = parseMoney(get('loi_cam'));        if (cam)  { $('f-cam').value = cam.toFixed(2); applied++; }
    const dep = parseMoney(get('loi_deposit'));    if (dep != null) { $('f-deposit').value = dep.toFixed(2); applied++; }
    const email = /[\w.+-]+@[\w-]+\.[\w.]+/.exec(get('loi_contact_info'));
    if (email) { $('f-notice-email').value = email[0]; applied++; }
    const unit = /\b([A-Z]\d{2,3})\b/.exec((get('loi_premises') || '').toUpperCase());
    if (unit) {
      if ([...$('f-suite').options].some(o => o.value === unit[1])) {
        $('f-suite').value = unit[1]; onSuiteChange();
      } else {
        $('f-suite').value = '__manual__'; manualToggle(); $('f-unit-manual').value = unit[1];
      }
      applied++;
    }
    if (fields.loi_type_nnn === true) { $('f-type-nnn').checked = true; $('f-type-cam').checked = false; }
    recomputeEnd(); recomputeShare(); recomputeFirstMonth();
    return applied;
  }

  async function handleImportFile(file) {
    const status = $('import-status');
    const say = (m, bad) => { status.textContent = m; status.className = 'field-note' + (bad ? ' text-rust-600' : ''); };
    try {
      if (/\.json$/i.test(file.name)) {
        const s = JSON.parse(await file.text());
        if (applySnapshot(s)) { autosave(); say(`Deal file "${file.name}" loaded.`); }
        else say('That JSON file is not a Lease Builder deal file.', true);
        return;
      }
      const bytes = await file.arrayBuffer();
      const pdf = await PDFDocument.load(bytes, { ignoreEncryption: true });
      const deal = extractDealJson(pdf);
      if (deal) {
        applySnapshot(deal); autosave();
        say(`Record PDF "${file.name}" loaded — deal restored.`);
        return;
      }
      // Try the fillable Letter of Intent (AcroForm field names loi_*)
      let fields = {};
      try {
        pdf.getForm().getFields().forEach(f => {
          const name = f.getName();
          try {
            if (f.constructor.name.indexOf('CheckBox') !== -1) fields[name] = f.isChecked();
            else if (typeof f.getText === 'function') fields[name] = f.getText() || '';
          } catch (e) {}
        });
      } catch (e) {}
      if (Object.keys(fields).some(k => k.startsWith('loi_'))) {
        const n = applyLoiFields(fields);
        autosave();
        say(`Letter of Intent "${file.name}" imported — ${n} field(s) prefilled. Review before generating.`);
      } else {
        say('No Lease Builder data found in that PDF (expected a filled Letter of Intent or a generated record).', true);
      }
    } catch (err) {
      say('Import failed: ' + err.message, true);
    }
  }

  // ============================================================
  // Autosave
  // ============================================================
  const DRAFT_KEY = 'chsLeaseDraft.v2';
  let saveTimer = null;
  function autosave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(DRAFT_KEY, JSON.stringify(snapshot())); } catch (e) {}
    }, 300);
  }
  function restoreDraft() {
    try {
      const s = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
      if (s && s.fields && Object.values(s.fields).some(Boolean)) {
        applySnapshot(s);
        $('draft-note').classList.remove('hidden');
      }
    } catch (e) {}
  }
  function resetForm() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
    FIELD_IDS.forEach(id => { if ($(id)) $(id).value = ''; });
    $('f-delivery').value = 'As-Is';
    $('f-direct-util').value = "Electricity, natural gas, telephone, internet/data (accounts in Tenant's name)";
    $('f-deposit').value = '0';
    $('f-term').value = '24';
    $('f-gfd').checked = true; $('f-ex-a').checked = true;
    $('f-type-cam').checked = true; $('f-type-nnn').checked = false;
    Object.keys(exhibitUploads).forEach(k => delete exhibitUploads[k]);
    ['f-ex-a-file', 'f-ex-b-file', 'f-ex-d-file'].forEach(id => { if ($(id)) $(id).value = ''; });
    $('draft-note').classList.add('hidden');
    manualToggle();
  }

  // ============================================================
  // Generate + downloads
  // ============================================================
  function download(bytes, filename, linkId, mime) {
    const url = URL.createObjectURL(new Blob([bytes], { type: mime || 'application/pdf' }));
    const a = $(linkId);
    a.href = url; a.download = filename;
    return a;
  }

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
      const leaseBytes = await buildLeasePackage(d);
      const recordBytes = await buildRecord(d);
      const stamp = new Date().toISOString().slice(0, 10);
      const base = `${d.unit}_${slug(d.tenant)}_${stamp}`;
      const a1 = download(leaseBytes, `CourthouseSquare_Lease_${base}.pdf`, 'dl-lease');
      const a2 = download(recordBytes, `LeaseChecklist_CAM_${base}.pdf`, 'dl-record');
      download(new TextEncoder().encode(JSON.stringify(snapshot(), null, 2)),
               `LeaseDeal_${base}.json`, 'dl-deal', 'application/json');
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

  // ============================================================
  // Form behavior
  // ============================================================
  function recomputeShare() {
    const sqft = num('f-sqft');
    if (sqft && vacData.buildingSqft) $('f-share').value = (sqft / vacData.buildingSqft * 100).toFixed(2);
  }
  function recomputeFirstMonth() {
    const monthly = num('f-rent') + num('f-cam') + num('f-util');
    const pro = prorationFor(val('f-rent-start') || val('f-start'), monthly);
    $('f-first-month').value = (pro ? pro.amount : monthly).toFixed(2);
    $('first-month-note').textContent = pro
      ? `Prorated: ${pro.days} of ${pro.dim} days of ${pro.monthName} (full month is ${fmtMoney(monthly)}). Edit if negotiated.`
      : 'Base + CAM + shared utilities; edit if negotiated.';
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
  function manualToggle() {
    $('manual-unit-wrap').classList.toggle('hidden', val('f-suite') !== '__manual__');
  }

  function onSuiteChange() {
    manualToggle();
    const s = vacData.suites.find(x => x.unit === val('f-suite'));
    if (!s) return;
    $('f-sqft').value = s.sqft;
    $('f-rent').value = s.rent.toFixed(2);
    $('f-cam').value = s.cam.toFixed(2);
    $('f-util').value = s.utilities.toFixed(2);
    recomputeShare(); recomputeFirstMonth();
    probeExhibitA();
  }

  async function probeExhibitA() {
    // A site-hosted legal description auto-attaches when present.
    delete exhibitAuto.a;
    try {
      const r = await fetch('/lease/exhibits/exhibit-a-legal-description.pdf', { method: 'HEAD' });
      if (r.ok) {
        exhibitAuto.a = '/lease/exhibits/exhibit-a-legal-description.pdf';
        $('ex-a-note').textContent = 'Legal description found on the site — it will be attached automatically.';
        return;
      }
    } catch (e) {}
    $('ex-a-note').textContent = exhibitUploads.a
      ? `Will attach the uploaded file (${exhibitUploads.a.name}).`
      : 'No legal description on file — upload one below, or it is marked "attached separately."';
  }

  function wireExhibitUpload(inputId, key) {
    const input = $(inputId);
    if (!input) return;
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) { delete exhibitUploads[key]; return; }
      exhibitUploads[key] = { name: file.name, bytes: await file.arrayBuffer() };
      if (key === 'a') probeExhibitA();
    });
  }

  async function init() {
    try {
      const id = await fetch('/data/identity.json', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null);
      if (id) Object.assign(IDENT, id);
    } catch (e) { /* fallback literals above remain in effect */ }
    let dataOk = true;
    try {
      const raw = await fetch('/data/vacancies.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw 0; return r.json(); });
      vacData = Array.isArray(raw) ? { asOf: '', buildingSqft: 6630, suites: raw } : raw;
    } catch (e) { dataOk = false; }

    const sel = $('f-suite');
    for (const s of vacData.suites) {
      const o = document.createElement('option');
      o.value = s.unit;
      o.textContent = `${s.unit} - ${fmtInt(s.sqft)} sq ft`;
      sel.appendChild(o);
    }
    const manual = document.createElement('option');
    manual.value = '__manual__';
    manual.textContent = 'Other / manual entry…';
    sel.appendChild(manual);
    $('building-sqft-note').textContent = fmtInt(vacData.buildingSqft || 0);

    if (!dataOk) {
      const box = $('builder-errors');
      box.textContent = 'Suite pricing data (/data/vacancies.json) could not be loaded — choose "Other / manual entry" and fill the numbers by hand.';
      box.classList.remove('hidden');
    }

    sel.addEventListener('change', onSuiteChange);
    $('f-sqft').addEventListener('input', recomputeShare);
    ['f-rent', 'f-cam', 'f-util'].forEach(id => $(id).addEventListener('input', recomputeFirstMonth));
    ['f-start', 'f-term'].forEach(id => $(id).addEventListener('change', () => { recomputeEnd(); recomputeFirstMonth(); }));
    $('f-rent-start').addEventListener('change', recomputeFirstMonth);
    $('f-end').addEventListener('input', () => { $('f-term').value = 'custom'; });
    $('generate').addEventListener('click', generate);
    $('reset-form').addEventListener('click', resetForm);

    // Autosave every field.
    FIELD_IDS.concat(CHECK_IDS).forEach(id => { if ($(id)) $(id).addEventListener('input', autosave); });
    document.querySelectorAll('input[name="lease-type"]').forEach(r => r.addEventListener('change', autosave));

    // Import drop zone + file input.
    const zone = $('import-zone');
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('border-rust-400'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('border-rust-400'));
    zone.addEventListener('drop', e => {
      e.preventDefault(); zone.classList.remove('border-rust-400');
      if (e.dataTransfer.files.length) handleImportFile(e.dataTransfer.files[0]);
    });
    $('import-file').addEventListener('change', () => {
      if ($('import-file').files.length) handleImportFile($('import-file').files[0]);
    });

    wireExhibitUpload('f-ex-a-file', 'a');
    wireExhibitUpload('f-ex-b-file', 'b');
    wireExhibitUpload('f-ex-d-file', 'd');

    restoreDraft();
    probeExhibitA();
    // Preload fonts in the background so the first Generate is fast.
    loadFontBytes().catch(() => {});
  }

  init();
})();
