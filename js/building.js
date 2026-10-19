/* E. Berry building page: the neighbor wall and the inquiry form's suite options.
 *
 * Reusable across buildings; everything it needs comes from the page:
 *   document.body.dataset.building        building id, matched against listings[].buildingId
 *   #neighbor-wall[data-address-match]    fallback match: listing.address starts with this text
 *   #neighbor-wall[data-building-name]    display name, used when the copy adapts to having neighbors
 *   window.EB.LISTINGS_URL                the listings feed (js/site-config.js)
 *   /data/tenants.json                    occupied suites; [] today, and the wall is complete without them
 *
 * Adapted from the original Courthouse Square homepage script (buildNeighborWall and its helpers),
 * restyled for the E. Berry brand: flat Cream cards on a Berry field, the Tangerine highlighted-word
 * "OPEN" block, no ribbons or animation.
 */
(function () {
  'use strict';

  // ---- helpers (ported from the original homepage) ----

  // Format a number as USD without cents.
  const fmtMoney = n => Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

  // Minimal HTML escape so any data-supplied string can't break out of markup.
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // Only web, mailto and site-relative URLs from the data files become links or images.
  function safeUrl(u) {
    const s = String(u || '').trim();
    return /^(https?:\/\/|mailto:|\/(?!\/))/i.test(s) ? s : '';
  }

  const titleCase = s => String(s || '').replace(/\b\w/g, c => c.toUpperCase());

  // Join an array of names into "A", "A and B", or "A, B and C".
  function listText(arr) {
    if (!arr || !arr.length) return '';
    if (arr.length === 1) return arr[0];
    return arr.slice(0, -1).join(', ') + ' and ' + arr.slice(-1);
  }

  // ISO date -> "October 4, 2026". Parsed by parts (not new Date(string)) to avoid UTC off-by-one-day shifts.
  function parseISO(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }

  // Prefix the pricing note with the date the feed was last updated (listings.json "updated").
  function renderSnapshotDate(iso) {
    const el = document.getElementById('pricing-snapshot');
    const d = parseISO(iso);
    if (!el || !d) return;
    if (el.dataset.base === undefined) el.dataset.base = el.textContent;   // keeps repeat calls from stacking
    const nice = d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    el.textContent = `Pricing snapshot as of ${nice}. ` + el.dataset.base;
  }

  // Preselect a suite in the inquiry form. With { scroll: false } the caller (an in-page link) does the scrolling.
  function prefillInquiry(unit, opts) {
    const select = document.getElementById('suite-select');
    if (select && unit) {
      const value = `Suite ${unit}`;
      if (![...select.options].some(o => o.value === value)) {
        const opt = document.createElement('option');
        opt.value = value; opt.textContent = value;
        select.insertBefore(opt, select.querySelector('[data-after-suites]'));
      }
      select.value = value;
    }
    if (!opts || opts.scroll !== false) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const target = document.getElementById('inquire');
      if (target) target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    }
  }

  // One option per open suite, placed before "Something else".
  function populateSuiteDropdown(open) {
    const select = document.getElementById('suite-select');
    if (!select) return;
    select.querySelectorAll('[data-suite-option]').forEach(o => o.remove());
    const anchor = select.querySelector('[data-after-suites]');
    open.forEach(L => {
      const unit = suiteOf(L);
      if (!unit) return;
      const opt = document.createElement('option');
      opt.value = `Suite ${unit}`;
      opt.dataset.suiteOption = '';
      opt.textContent = L.sqft != null ? `Suite ${unit}, ${Number(L.sqft).toLocaleString('en-US')} sq ft` : `Suite ${unit}`;
      select.insertBefore(opt, anchor);
    });
  }

  // ---- tally count-up ----
  function countUp(id, target, reduce) {
    const el = document.getElementById(id);
    if (!el) return;
    if (reduce || target <= 0) { el.textContent = target; return; }
    let n = 0;
    const step = Math.max(1, Math.round(target / 20));
    const iv = setInterval(() => {
      n += step;
      if (n >= target) { n = target; clearInterval(iv); }
      el.textContent = n;
    }, 30);
  }

  function setupTally(suites, neighbors, open) {
    const box = document.getElementById('neighbors-tally');
    if (!box) return;
    box.classList.remove('hidden');
    box.classList.add('flex');
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    countUp('tally-suites', suites, reduce);
    countUp('tally-neighbors', neighbors, reduce);
    countUp('tally-open', open, reduce);
  }

  // ---- listing helpers ----

  // "19001 Vashon Hwy SW, Suite N101, Vashon, WA 98070" -> "N101" (title is the fallback).
  function suiteOf(L) {
    const re = /\bSuite\s+([A-Za-z]*\d+[A-Za-z]?)\b/i;
    const m = re.exec(String(L.address || '')) || re.exec(String(L.title || ''));
    return m ? m[1].toUpperCase() : '';
  }

  // Does this listing belong to the building this page is about?
  function matchesBuilding(L, buildingId, addressMatch) {
    if (!L || !L.id || typeof L.rent !== 'number') return false;
    if (buildingId && L.buildingId === buildingId) return true;
    return !!addressMatch && String(L.address || '').toLowerCase().startsWith(addressMatch.toLowerCase());
  }

  // The feed's summary is "<fit line> All-in $X/mo covers ...". Split it: the fit line, and a cost note
  // (the feature that starts "All-in", else the tail of the summary).
  function splitSummary(L) {
    const s = String(L.summary || '').trim();
    const i = s.search(/\bAll-in\b/i);
    const fit = (i >= 0 ? s.slice(0, i) : s).trim();
    const feat = (Array.isArray(L.features) ? L.features : []).find(f => /^all-in\b/i.test(String(f)));
    const cost = feat ? String(feat) : (i >= 0 ? s.slice(i).trim() : '');
    return { fit, cost };
  }

  // "2026-11-01" -> "Available Nov 1" when in the future; '' when available now.
  function availableLater(iso) {
    const d = parseISO(iso);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    if (!d || d <= today) return '';
    return 'Available ' + d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  // Pick up to two occupied neighbors nearest an open suite (same building letter prefix, closest suite number).
  function neighborsFor(openUnit, tenants) {
    const prefix = (String(openUnit).match(/^[A-Za-z]+/) || [''])[0];
    const num = parseInt(String(openUnit).replace(/\D/g, ''), 10);
    return tenants
      .filter(t => t.suite && (String(t.suite).match(/^[A-Za-z]+/) || [''])[0] === prefix)
      .map(t => ({ name: t.name, d: Math.abs(parseInt(String(t.suite).replace(/\D/g, ''), 10) - num) }))
      .sort((a, b) => a.d - b.d)
      .slice(0, 2)
      .map(t => t.name);
  }

  // ---- cards ----

  const CARD = 'neighbor-card flex flex-col rounded-card bg-eb-cream p-6 text-eb-berry sm:p-7';
  const LINK = 'text-lg font-semibold text-eb-berry underline decoration-eb-tangerine decoration-2 underline-offset-[6px] hover:decoration-eb-berry';

  function openCardHTML(L, tenants, isAlive) {
    const unit = suiteOf(L);
    const { fit, cost } = splitSummary(L);
    const later = availableLater(L.available);
    const next = (isAlive && unit) ? neighborsFor(unit, tenants) : [];
    const facts = [];
    if (L.sqft != null) facts.push(`<div><dt class="text-sm">Size</dt><dd class="font-serif text-2xl font-medium leading-tight">${Number(L.sqft).toLocaleString('en-US')} sq ft</dd></div>`);
    facts.push(`<div><dt class="text-sm">All-in, monthly</dt><dd class="font-serif text-2xl font-medium leading-tight">${fmtMoney(L.rent)}</dd></div>`);
    return `
      <article class="${CARD}" data-mode="open" data-cat="open">
        <div class="flex items-start justify-between gap-3">
          <span class="rounded-[4px] bg-eb-tangerine px-2.5 py-1 font-serif text-2xl font-medium uppercase leading-none tracking-[0.08em] text-eb-berry">Open</span>
          ${later ? `<span class="pt-1 text-base">${esc(later)}</span>` : ''}
        </div>
        <h3 class="mt-6 font-serif font-medium leading-none">${unit
          ? `<span class="block text-sm font-normal uppercase tracking-[0.08em]">Suite</span><span class="mt-1 block text-6xl tracking-[-0.01em]">${esc(unit)}</span>`
          : `<span class="block text-3xl leading-tight">${esc(L.title)}</span>`}</h3>
        <dl class="mt-6 flex flex-wrap gap-x-8 gap-y-3">${facts.join('')}</dl>
        ${fit ? `<p class="mt-5">${esc(fit)}</p>` : ''}
        ${cost ? `<p class="mt-3 text-base italic">${esc(cost)}</p>` : ''}
        ${next.length ? `<p class="mt-4 border-t border-dashed border-eb-berry pt-4 text-base italic">You'd be next to <span class="font-medium not-italic">${esc(listText(next))}</span>.</p>` : ''}
        <a href="#inquire" ${unit ? `data-inquire-suite="${esc(unit)}"` : ''} class="mt-auto self-start pt-6 ${LINK}">Curious? Let's talk &rarr;</a>
      </article>`;
  }

  function occupiedCardHTML(t) {
    const logo = safeUrl(t.logo);
    const site = safeUrl(t.website);
    const contact = [
      t.phone ? esc(t.phone) : '',
      t.email ? `<a href="mailto:${esc(t.email)}" class="underline decoration-eb-tangerine decoration-2 underline-offset-4 hover:decoration-eb-berry">${esc(t.email)}</a>` : ''
    ].filter(Boolean).join(' &middot; ');
    return `
      <article class="${CARD}" data-mode="occupied" data-cat="${esc(String(t.category || '').toLowerCase())}">
        ${logo ? `<img src="${esc(logo)}" alt="${esc(t.name)} logo" class="mb-4 h-10 w-auto object-contain" onerror="this.remove()" />` : ''}
        <div class="flex items-start justify-between gap-3">
          ${t.category ? `<span class="rounded-[4px] bg-eb-sand px-2 py-0.5 font-serif text-xs font-medium uppercase tracking-[0.08em]">${esc(titleCase(t.category))}</span>` : '<span></span>'}
          ${t.suite ? `<span class="text-sm">Suite ${esc(t.suite)}</span>` : ''}
        </div>
        <h3 class="mt-4 font-serif text-3xl font-medium leading-tight">${esc(t.name)}</h3>
        ${t.blurb ? `<p class="mt-3">${esc(t.blurb)}</p>` : ''}
        ${contact ? `<p class="mt-3 text-base">${contact}</p>` : ''}
        ${site ? `<p class="mt-auto pt-4"><a href="${esc(site)}" target="_blank" rel="noopener" class="${LINK}">Visit website &rarr;</a></p>` : ''}
      </article>`;
  }

  // ---- filter controls (hidden until there are occupied tenants) ----
  let activeCat = null;
  let openOnly = false;

  function setupControls(tenants) {
    const controls = document.getElementById('neighbors-controls');
    if (!controls) return;
    controls.classList.remove('hidden');
    controls.classList.add('flex');

    // One pill per distinct occupied category.
    const cats = [...new Set(tenants.map(t => String(t.category || '').toLowerCase()).filter(Boolean))].sort();
    const tagWrap = document.getElementById('neighbor-tags');
    tagWrap.innerHTML = cats.map(c =>
      `<button type="button" data-cat="${esc(c)}" aria-pressed="false"
               class="cursor-pointer rounded-full border-2 border-eb-cream px-4 py-1.5 text-base text-eb-cream hover:bg-eb-cream hover:text-eb-berry aria-pressed:bg-eb-cream aria-pressed:text-eb-berry">${esc(titleCase(c))}</button>`
    ).join('');

    tagWrap.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        activeCat = (activeCat === btn.dataset.cat) ? null : btn.dataset.cat;
        tagWrap.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cat === activeCat)));
        applyFilterStates();
      });
    });

    const toggle = document.getElementById('open-toggle');
    toggle.addEventListener('click', () => {
      openOnly = !openOnly;
      toggle.setAttribute('aria-pressed', String(openOnly));   // CSS reacts to this
      applyFilterStates();
    });
  }

  // Occupied cards dim (category filter) or recede (open-only toggle).
  // Open cards always stay fully visible, so "what's available" is never hidden.
  function applyFilterStates() {
    document.querySelectorAll('#neighbor-wall .neighbor-card').forEach(card => {
      card.classList.remove('opacity-50', 'opacity-40');
      if (card.dataset.mode === 'open') return;
      if (openOnly) { card.classList.add('opacity-40'); return; }
      if (activeCat && card.dataset.cat !== activeCat) card.classList.add('opacity-50');
    });
  }

  // ---- the wall ----

  function fetchJSON(url, fallback) {
    return fetch(url, { cache: 'no-cache' }).then(r => r.ok ? r.json() : fallback).catch(() => fallback);
  }

  async function buildNeighborWall() {
    const wall = document.getElementById('neighbor-wall');
    if (!wall) return;
    const buildingId = document.body.dataset.building || '';
    const addressMatch = wall.dataset.addressMatch || document.body.dataset.addressMatch || '';
    const buildingName = wall.dataset.buildingName || 'The building';
    const listingsUrl = (window.EB && window.EB.LISTINGS_URL) || '/data/listings.json';

    const [feed, tenantsRaw] = await Promise.all([
      fetchJSON(listingsUrl, null),
      fetchJSON('/data/tenants.json', [])
    ]);
    // The feed is {updated, listings}; tolerate a bare array too.
    const all = Array.isArray(feed) ? feed : ((feed && feed.listings) || []);
    renderSnapshotDate(Array.isArray(feed) ? '' : (feed && feed.updated));

    const open = all
      .filter(L => matchesBuilding(L, buildingId, addressMatch))
      .sort((a, b) => suiteOf(a).localeCompare(suiteOf(b), undefined, { numeric: true }));
    const tenants = (Array.isArray(tenantsRaw) ? tenantsRaw : [])
      .filter(t => t && t.name && (!t.buildingId || t.buildingId === buildingId));

    // Always keep the inquiry-form dropdown populated from real listings.
    populateSuiteDropdown(open);

    if (!open.length && !tenants.length) {
      wall.innerHTML = '<p class="col-span-full">Suite information is being updated. Please <a href="#inquire" class="underline decoration-2 underline-offset-[6px] hover:decoration-eb-tangerine">reach out</a> for the latest availability.</p>';
      return;
    }

    const isAlive = tenants.length > 0;   // do we have neighbors to show?

    // Adapt the header copy to whether the roster is populated yet.
    if (isAlive) {
      const heading = document.getElementById('neighbors-heading');
      const lede = document.getElementById('neighbors-lede');
      if (heading) heading.textContent = 'Meet the neighbors you’d be keeping.';
      if (lede) lede.textContent = `${buildingName} is a working building of professionals, practitioners, and small firms, with a few doors open for whoever comes next. Here is who you would share the block with.`;
    }

    // One suite-ordered list so open and occupied cards interleave.
    const items = [
      ...tenants.map(t => ({ mode: 'occupied', sortKey: String(t.suite || '~'), data: t })),
      ...open.map(L => ({ mode: 'open', sortKey: suiteOf(L) || '~', data: L }))
    ].sort((a, b) => a.sortKey.localeCompare(b.sortKey, undefined, { numeric: true }));

    wall.innerHTML = items.map(it =>
      it.mode === 'occupied' ? occupiedCardHTML(it.data) : openCardHTML(it.data, tenants, isAlive)
    ).join('');

    // "Curious? Let's talk": preselect the suite, then let the in-page link do the scrolling.
    wall.querySelectorAll('[data-inquire-suite]').forEach(a => {
      a.addEventListener('click', () => prefillInquiry(a.dataset.inquireSuite, { scroll: false }));
    });

    // Tally and controls only make sense once there are neighbors.
    if (isAlive) {
      setupTally(items.length, tenants.length, open.length);
      setupControls(tenants);
    }
  }

  window.EBBuilding = { buildNeighborWall, prefillInquiry, renderSnapshotDate, countUp, fmtMoney, esc };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', buildNeighborWall);
  else buildNeighborWall();
})();
