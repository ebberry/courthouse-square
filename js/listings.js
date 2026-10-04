/* E. Berry listings index (/listings/): filter bar, card grid, brand map.
 *
 *   window.EB.LISTINGS_URL   the feed ({updated, listings}, or a bare array), from /js/site-config.js
 *   window.EBMap             js/eb-map.js (Leaflet wrapper); the page still works as a list if it is missing
 *
 * State lives in the URL: ?type=residential|commercial &beds=1|2|3 &price=750.. &sqft=150..
 * It is read on load and written back with history.replaceState, so every filtered view is a shareable
 * link and the homepage's /listings/?type=residential and ?type=commercial links just work.
 *
 * Filtering is in memory. The map always shows the FILTERED set, regrouped by coordinate.
 * Listings with null lat/lng get a card but never a marker.
 */
(function () {
  'use strict';

  // ---- helpers ----
  // fmtMoney / esc / safeUrl / availableText are copied from index.html's inline script and js/building.js
  // on purpose: both of those are generated or frozen, so there is no shared module to import from.

  // Format a number as USD without cents.
  const fmtMoney = n => Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

  // Minimal HTML escape so any data-supplied string can't break out of markup.
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // Only web and site-relative URLs from the feed become images.
  function safeUrl(u) {
    const s = String(u || '').trim();
    return /^(https?:\/\/|\/(?!\/))/i.test(s) ? s : '';
  }

  // ISO date parsed by parts (not new Date(string)) to avoid UTC off-by-one-day shifts.
  function parseISO(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }

  // "2026-11-01" -> "available Nov 1", or "available now" when null / today / past.
  function isFuture(iso) {
    const d = parseISO(iso);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    return !!d && d > today;
  }
  function availableText(iso) {
    if (!isFuture(iso)) return 'available now';
    return 'available ' + parseISO(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  // ["2 bed", "1 bath", "800 sq ft", "available now"] — plain text; callers escape and join.
  function factParts(L) {
    const bits = [];
    if (L.beds != null) bits.push(L.beds + ' bed');
    if (L.baths != null) bits.push(L.baths + ' bath');
    if (L.sqft != null) bits.push(Number(L.sqft).toLocaleString('en-US') + ' sq ft');
    bits.push(availableText(L.available));
    return bits;
  }

  const hasCoords = L => typeof L.lat === 'number' && typeof L.lng === 'number';

  // ---- card (the homepage's listing card; whole card is the link) ----
  function cardHTML(L) {
    const isCommercial = L.type === 'commercial';
    const badge = isCommercial
      ? '<span class="self-start rounded-[4px] bg-eb-mustard px-2 py-0.5 font-serif text-xs font-medium uppercase tracking-[0.08em]">Commercial</span>'
      : '<span class="self-start rounded-[4px] bg-eb-sand px-2 py-0.5 font-serif text-xs font-medium uppercase tracking-[0.08em]">Home</span>';
    const src = safeUrl(L.photos && L.photos[0]);
    const photo = src
      ? `<img src="${esc(src)}" alt="" loading="lazy" class="h-full w-full object-cover" />`
      : `<div class="flex h-full w-full flex-col items-center justify-center gap-2 text-eb-cream">
           <img src="/images/brand/monogram-tangerine-bare.svg" alt="" class="h-10 w-auto" />
           <span class="font-serif text-sm italic">photos soon</span>
         </div>`;
    return `
      <li class="flex">
        <article class="group relative flex w-full flex-col rounded-card border-[1.5px] border-eb-berry bg-eb-cream p-3 hover:border-eb-tangerine" data-id="${esc(L.id)}">
          <div class="aspect-[4/3] overflow-hidden rounded-[12px] bg-eb-berry">${photo}</div>
          <div class="flex flex-1 flex-col px-3 pb-3 pt-5 sm:px-4 sm:pb-4">
            ${badge}
            <p class="mt-4 font-serif text-3xl font-medium leading-none sm:text-4xl">${fmtMoney(L.rent)}<span class="text-lg font-normal">/mo</span></p>
            <p class="mt-2 text-base">${factParts(L).map(esc).join(' &middot; ')}</p>
            <h3 class="mt-3 font-serif text-lg font-medium leading-snug">
              <a href="/listings/${encodeURIComponent(L.id)}/" class="listing-card-link after:absolute after:inset-0 after:rounded-card">${esc(L.title)}</a>
            </h3>
            ${L.summary ? `<p class="mt-2 line-clamp-2 text-base">${esc(L.summary)}</p>` : ''}
            <span class="mt-auto pt-5 text-lg font-semibold text-eb-berry underline decoration-eb-tangerine decoration-2 underline-offset-[6px] group-hover:decoration-eb-berry">Curious? Let's talk &rarr;</span>
          </div>
        </article>
      </li>`;
  }

  // ---- DOM ----
  const $ = id => document.getElementById(id);
  const els = {
    header: document.querySelector('body > header'),
    bar: $('filter-bar'),
    types: [...document.querySelectorAll('#type-group [data-type]')],
    beds: $('f-beds'), price: $('f-price'), sqft: $('f-sqft'),
    clear: $('clear-filters'),
    count: $('result-count'),
    split: $('split'), grid: $('listing-grid'), empty: $('empty-state'),
    mapPane: $('map-pane'), map: $('map'),
    toggleWrap: $('mobile-toggle-wrap'), toggle: $('mobile-toggle')
  };

  // ---- filter state <-> URL ----
  const DEFAULTS = { type: 'all', beds: '', price: '', sqft: '' };
  const state = Object.assign({}, DEFAULTS);
  const allowed = k => [...els[k].options].map(o => o.value).filter(Boolean);   // the selects are the single list of choices

  function readParams() {
    const q = new URLSearchParams(location.search);
    const type = q.get('type');
    if (type === 'residential' || type === 'commercial') state.type = type;
    ['beds', 'price', 'sqft'].forEach(k => {
      const v = q.get(k);
      if (v && allowed(k).includes(v)) state[k] = v;
    });
    if (state.type === 'commercial') state.beds = '';          // bedrooms don't apply to commercial space
  }

  function writeParams() {
    const q = new URLSearchParams();
    if (state.type !== 'all') q.set('type', state.type);
    ['beds', 'price', 'sqft'].forEach(k => { if (state[k]) q.set(k, state[k]); });
    const qs = q.toString();
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash); } catch (e) { /* file:// etc. */ }
  }

  const isNarrowed = () => !!(state.beds || state.price || state.sqft);
  const isFiltered = () => state.type !== 'all' || isNarrowed();

  // Beds apply to homes only: a commercial space has no bedrooms, so "2+ beds" excludes it.
  function matches(L) {
    if (state.type !== 'all' && L.type !== state.type) return false;
    if (state.beds && !(typeof L.beds === 'number' && L.beds >= +state.beds)) return false;
    if (state.price && !(L.rent <= +state.price)) return false;
    if (state.sqft && !(typeof L.sqft === 'number' && L.sqft >= +state.sqft)) return false;
    return true;
  }

  // ---- data ----
  let all = [];
  let shown = [];

  // ---- controls ----
  function syncControls() {
    els.types.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.type === state.type)));
    els.beds.value = state.beds;
    els.price.value = state.price;
    els.sqft.value = state.sqft;
    const commercial = state.type === 'commercial';
    els.beds.disabled = commercial;
    els.beds.title = commercial ? 'Bedrooms only apply to homes' : '';
    els.clear.hidden = !isFiltered();
  }

  function setType(type) {
    state.type = type;
    if (type === 'commercial') state.beds = '';
    render();
  }

  function clearAll() {
    Object.assign(state, DEFAULTS);
    render();
  }

  // ---- count line + empty states ----
  function noun(type, n) {
    if (type === 'residential') return n === 1 ? 'home' : 'homes';
    if (type === 'commercial') return n === 1 ? 'commercial space' : 'commercial spaces';
    return n === 1 ? 'place' : 'places';
  }

  const LINK = 'font-semibold text-eb-berry underline decoration-eb-tangerine decoration-2 underline-offset-[6px] hover:decoration-eb-berry';

  function renderCount(ofType) {
    const n = shown.length;
    let text;
    if (!n) text = ofType.length ? 'No matches for that combination.' : `No ${noun(state.type, 2)} open right now.`;
    else if (isNarrowed()) text = `${n} of ${ofType.length} ${noun(state.type, ofType.length)} match.`;
    else text = `${n} ${noun(state.type, n)} open right now.`;
    // Below lg the bar's own Clear link can be scrolled out of sight, so repeat it here.
    els.count.innerHTML = esc(text) + (isFiltered()
      ? ` <a href="/listings/" data-clear class="text-base font-normal text-eb-berry underline decoration-eb-tangerine decoration-2 underline-offset-4 hover:decoration-eb-berry lg:hidden">Clear filters</a>`
      : '');
  }

  function renderEmpty(ofType) {
    if (shown.length) { els.empty.hidden = true; els.empty.innerHTML = ''; return; }
    let body;
    if (!ofType.length) {
      // Nothing of this kind is open at all (not an over-filtering problem).
      const lede = state.type === 'residential'
        ? "Nothing's open just now &mdash; but homes come and go."
        : state.type === 'commercial'
          ? 'No commercial space is open just now &mdash; but that changes.'
          : "Nothing's open just now &mdash; but places come and go.";
      const other = state.type === 'residential' ? 'commercial' : state.type === 'commercial' ? 'residential' : '';
      const otherOpen = other && all.some(L => L.type === other);
      body = `<p class="font-serif text-2xl leading-[1.25] sm:text-3xl">${lede} Tell me what you're looking for and I'll keep an eye out.</p>
        <p class="mt-6"><a href="/#inquire" class="text-xl ${LINK}">Tell me what you're looking for &rarr;</a></p>
        ${otherOpen ? `<p class="mt-4 text-base"><a href="/listings/?type=${other}" data-set-type="${other}" class="underline decoration-eb-tangerine decoration-2 underline-offset-4 hover:decoration-eb-berry">${other === 'commercial' ? 'See the commercial spaces that are open' : 'See the homes that are open'}</a></p>` : ''}`;
    } else {
      body = `<p class="font-serif text-2xl leading-[1.25] sm:text-3xl">Nothing matches that combination. Loosen a filter or two?</p>
        <p class="mt-6"><a href="/listings/" data-clear class="text-xl ${LINK}">Clear filters</a></p>`;
    }
    els.empty.innerHTML = body;
    els.empty.hidden = false;
  }

  // ---- map ----
  let map = null;

  function pointsFor(list) {
    return list.filter(hasCoords).map(L => ({
      id: L.id, lat: L.lat, lng: L.lng, title: L.title, rent: L.rent, address: L.address,
      meta: factParts(L).join(' · '), muted: isFuture(L.available)
    }));
  }

  function ensureMap() {
    if (map || !window.L || !window.EBMap || !els.map || !els.map.offsetWidth) return;
    map = window.EBMap.create(els.map, pointsFor(shown), { label: 'Map of the places that are open' });
  }

  function updateMap() {
    if (map) map.ebSetPoints(pointsFor(shown), true);
  }

  // ---- render ----
  function render() {
    const ofType = all.filter(L => state.type === 'all' || L.type === state.type);
    shown = all.filter(matches);
    els.grid.innerHTML = shown.map(cardHTML).join('');
    els.grid.hidden = !shown.length;
    renderCount(ofType);
    renderEmpty(ofType);
    syncControls();
    writeParams();
    updateMap();
    measure();
  }

  // ---- sticky offsets ----
  // The filter bar sticks under the header and the map pane under both; their heights vary with wrapping,
  // so measure them and publish as CSS variables (page <style> has sane fallbacks).
  function measure() {
    const root = document.documentElement.style;
    if (els.header) root.setProperty('--eb-header-h', els.header.offsetHeight + 'px');
    if (els.bar) root.setProperty('--eb-filter-h', els.bar.offsetHeight + 'px');
  }

  // ---- mobile List / Map swap ----
  function setView(view) {
    els.split.dataset.view = view;
    els.toggle.textContent = view === 'map' ? 'List' : 'Map';
    measure();
    if (view === 'map') {
      ensureMap();
      if (map) { map.invalidateSize({ animate: false }); map.ebFit(); }
    }
    // Keep the filter bar pinned under the header after the swap, so the new view starts at its top.
    const top = els.split.getBoundingClientRect().top + window.scrollY - els.header.offsetHeight - els.bar.offsetHeight;
    window.scrollTo(0, Math.max(0, top));
  }

  // ---- boot ----
  function wire() {
    els.types.forEach(b => b.addEventListener('click', () => setType(b.dataset.type)));
    ['beds', 'price', 'sqft'].forEach(k => els[k].addEventListener('change', () => { state[k] = els[k].value; render(); }));
    els.clear.addEventListener('click', e => { e.preventDefault(); clearAll(); });
    // Links the empty states render.
    document.addEventListener('click', e => {
      const clear = e.target.closest('[data-clear]');
      if (clear) { e.preventDefault(); clearAll(); return; }
      const t = e.target.closest('[data-set-type]');
      if (t) { e.preventDefault(); setType(t.dataset.setType); }
    });
    els.toggle.addEventListener('click', () => setView(els.split.dataset.view === 'map' ? 'list' : 'map'));

    // The pill would sit on top of the footer links; step aside when the footer is on screen.
    const footer = document.querySelector('body > footer');
    if (footer && 'IntersectionObserver' in window) {
      new IntersectionObserver(es => { els.toggleWrap.hidden = es.some(e => e.isIntersecting); }).observe(footer);
    }

    measure();
    window.addEventListener('resize', measure);
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(measure);
      if (els.header) ro.observe(els.header);
      ro.observe(els.bar);
    }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);
  }

  function watchMap() {
    if (!window.L || !window.EBMap) { els.split.dataset.nomap = '1'; return; }   // list-only fallback
    // Build the map only once its pane is actually on screen (it is display:none on phones in List view).
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(es => {
        if (es.some(e => e.isIntersecting)) { io.disconnect(); ensureMap(); updateMap(); }
      }, { rootMargin: '200px' });
      io.observe(els.mapPane);
    } else {
      ensureMap();
    }
  }

  async function load() {
    try {
      const url = (window.EB && window.EB.LISTINGS_URL) || '/data/listings.json';
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      // Feed is {updated, listings}; tolerate a bare array too.
      const list = Array.isArray(data) ? data : (data.listings || []);
      all = list.filter(L => L && L.id && typeof L.rent === 'number');
      render();
      ensureMap();                       // no-op unless the pane is already visible
    } catch (err) {
      els.count.textContent = '';
      els.grid.hidden = true;
      els.empty.innerHTML = `<p class="font-serif text-2xl leading-[1.25] sm:text-3xl">I couldn't load the list just now.</p>
        <p class="mt-6">Please try again in a moment, or <a href="mailto:me@ebberry.com" class="${LINK}">email me</a> and I'll tell you what's open.</p>`;
      els.empty.hidden = false;
    }
  }

  function init() {
    if (!els.grid || !els.bar || !els.split) return;
    readParams();
    syncControls();
    wire();
    watchMap();
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
