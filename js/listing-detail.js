/* E. Berry listing detail, client-side fallback (/listing.html).
 *
 *   window.EB.LISTINGS_URL   the feed ({updated, listings}, or a bare array), from /js/site-config.js
 *   window.EBMap             js/eb-map.js (MapLibre wrapper); the page still works without it
 *
 * Used ONLY by listing.html. The real detail pages (/listings/<id>/) are generated, fully static HTML from
 * tools/build_pages.py and never load this file. This is the safety net behind the netlify.toml rewrite
 * /listings/* -> /listing.html: a listing that is in the live feed but has no generated page yet lands here.
 *
 * It finds the listing from the URL (/listings/<id>/ when served through the rewrite, else ?id=<id>), fetches
 * the feed, and draws the SAME layout as the generated pages. The markup below mirrors
 * tools/templates/listing.tmpl.html + listing.parts.tmpl.html and the helpers in tools/build_pages.py
 * (money, num, date_fmt, split_address, ...); tools/test_listings.py compares the two DOMs, so change them together.
 * An id the feed does not know gets a warm "not on my list" page with a link back to /listings/.
 */
(function () {
  'use strict';

  // ---- helpers (the same few small ones as js/listings.js; this page has no shared module to import from) ----

  const fmtMoney = n => Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  const fmtNum = n => Number(n).toLocaleString('en-US');

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

  // "2026-11-01" -> "Nov 1, 2026"
  function fmtDate(iso) {
    return parseISO(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  // Null, today or a past date reads as available now.
  function isNow(iso) {
    const d = parseISO(iso);
    if (!d) return true;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    return d <= today;
  }

  const hasCoords = L => typeof L.lat === 'number' && typeof L.lng === 'number' && isFinite(L.lat) && isFinite(L.lng);

  // "19001 Vashon Hwy SW, Suite N101, Vashon, WA 98070" -> street "19001 Vashon Hwy SW, Suite N101", Vashon, WA, 98070
  function splitAddress(address) {
    const m = /^(.+),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?$/.exec(address);
    return m ? { street: m[1], city: m[2], region: m[3], zip: m[4] } : { street: address, city: 'Vashon', region: 'WA', zip: '98070' };
  }

  const allInFeature = L => (L.features || []).find(f => String(f).toLowerCase().startsWith('all-in pricing')) || null;

  // ---- markup (mirrors tools/templates/listing.parts.tmpl.html; the page-level pieces mirror listing.tmpl.html) ----

  const LINK = 'text-xl font-semibold text-eb-berry underline decoration-eb-tangerine decoration-2 underline-offset-[6px] hover:decoration-eb-berry';
  const CRUMB = 'underline decoration-eb-tangerine decoration-2 underline-offset-4 hover:decoration-eb-berry';
  const SEAL = '<img src="/images/brand/monogram-tangerine-bare.svg" alt="" aria-hidden="true" class="h-14 w-auto shrink-0 sm:h-16" />';

  function factTile(value, note) {
    return `<li class="rounded-[12px] border-[1.5px] border-eb-berry bg-eb-cream px-5 py-3">
        <span class="block font-serif text-xl font-medium leading-tight">${esc(value)}</span>${note
          ? `\n        <span class="mt-1 block text-base leading-tight">${esc(note)}</span>` : ''}
      </li>`;
  }

  function factTiles(L) {
    const tiles = [];
    if (L.sqft != null) tiles.push(factTile(fmtNum(L.sqft) + ' sq ft'));
    if (L.beds != null) tiles.push(factTile(fmtNum(L.beds) + ' bed'));
    if (L.baths != null) tiles.push(factTile(fmtNum(L.baths) + ' bath'));
    tiles.push(factTile(isNow(L.available) ? 'Available now' : 'Available ' + fmtDate(L.available)));
    const feat = allInFeature(L);
    if (feat) {
      const i = feat.indexOf(' — ');
      let note = i >= 0 ? feat.slice(i + 3).trim() : '';
      note = note.charAt(0).toUpperCase() + note.slice(1);
      tiles.push(factTile('All-in pricing', note));
    }
    return tiles.join('\n      ');
  }

  function photoTiles(L, title) {
    const photos = (Array.isArray(L.photos) ? L.photos : []).map(safeUrl).filter(Boolean);
    if (!photos.length) {
      return `<div id="listing-photos-placeholder" class="relative flex min-h-[15rem] flex-col justify-end rounded-card bg-eb-berry p-6 text-eb-cream sm:p-10 md:min-h-[20rem]">
      <img src="/images/brand/monogram-tangerine-bare.svg" alt="" aria-hidden="true" class="absolute right-6 top-6 h-14 w-auto sm:right-10 sm:top-10 sm:h-16" />
      <p class="max-w-[30rem] font-serif text-2xl italic leading-[1.3] md:text-3xl">Photos are coming — ask me and I'll walk you through in person.</p>
    </div>`;
    }
    const tiles = photos.map((src, i) => {
      const wide = i === 0 && photos.length % 2 === 1;
      return `<li class="relative aspect-[4/3] overflow-hidden rounded-card bg-eb-berry${wide ? ' sm:col-span-2 sm:aspect-[16/9]' : ''}">
        <img src="${esc(src)}" alt="${esc(title + ', photo ' + (i + 1))}" loading="${i === 0 ? 'eager' : 'lazy'}" decoding="async" class="absolute inset-0 h-full w-full object-cover" onerror="this.remove()" />
      </li>`;
    });
    return `<ul id="listing-photos" role="list" class="grid gap-4 sm:grid-cols-2">
      ${tiles.join('\n      ')}
    </ul>`;
  }

  function featureTags(L, commercial) {
    const cls = commercial ? 'bg-eb-mustard' : 'bg-eb-sand';
    const feats = (Array.isArray(L.features) ? L.features : []).filter(f => String(f ?? '').trim());
    if (!feats.length) return '';
    return `<ul id="listing-features" role="list" class="mt-10 flex flex-wrap gap-3">
      ${feats.map(f => `<li class="rounded-[4px] ${cls} px-3 py-1.5 text-lg leading-snug">${esc(f)}</li>`).join('\n      ')}
    </ul>`;
  }

  function detailHTML(L, building) {
    const commercial = L.type === 'commercial';
    const title = String(L.title || L.id);
    const address = String(L.address || '');
    const addr = splitAddress(address);
    const mapped = hasCoords(L);
    const summary = String(L.summary || '').split(/\s+/).filter(Boolean).join(' ');

    const crumb = building
      ? `\n        <a href="/buildings/${encodeURIComponent(building.id)}/" class="${CRUMB}">Part of ${esc(building.name)} &rarr;</a>` : '';
    const badge = commercial
      ? '<span class="inline-block rounded-[4px] bg-eb-mustard px-2 py-0.5 font-serif text-xs font-medium uppercase tracking-[0.08em]">Commercial</span>'
      : '<span class="inline-block rounded-[4px] bg-eb-sand px-2 py-0.5 font-serif text-xs font-medium uppercase tracking-[0.08em]">Home</span>';

    const cityLine = `${addr.city}, ${addr.region} ${addr.zip}`;
    const addressLines = addr.street !== address ? `${esc(addr.street)}<br />${esc(cityLine)}` : esc(address);
    const osmUrl = mapped
      ? `https://www.openstreetmap.org/?mlat=${L.lat}&mlon=${L.lng}#map=17/${L.lat}/${L.lng}`
      : `https://www.openstreetmap.org/search?query=${encodeURIComponent(address)}`;
    const mapBlock = mapped
      ? `<div id="listing-map-wrap" class="hidden">
        <div id="listing-map" class="h-[20rem] w-full sm:h-[24rem] lg:h-full lg:min-h-[26rem]"
             data-lat="${esc(L.lat)}" data-lng="${esc(L.lng)}" data-id="${esc(L.id)}" data-title="${esc(title)}" data-rent="${esc(L.rent)}"></div>
      </div>` : '';

    return `
<section class="bg-eb-cream" aria-labelledby="listing-title">
  <div class="mx-auto max-w-[1440px] px-[var(--eb-space-margin)] pb-12 pt-[max(1.75rem,calc(var(--eb-space-margin)*0.45))] md:pb-16">
    <div class="flex items-start justify-between gap-6">
      <nav aria-label="Breadcrumb" class="flex flex-wrap items-baseline gap-x-8 gap-y-2 text-base">
        <a href="/listings/" class="${CRUMB}">&larr; Everything that's open</a>${crumb}
      </nav>
      ${SEAL}
    </div>

    <div class="mt-8 md:mt-12">
      ${badge}
      <h1 id="listing-title" class="mt-4 max-w-[26ch] text-balance font-serif text-[length:clamp(1.875rem,4.5vw,3.25rem)] font-medium leading-[1.08] tracking-[-0.01em]">${esc(title)}</h1>
      <address class="mt-3 text-xl not-italic">${esc(address)}</address>
    </div>

    <p id="listing-rent" class="mt-10 flex flex-wrap items-baseline gap-x-4 md:mt-14">
      <span class="font-serif text-[length:clamp(4.5rem,17vw,11rem)] font-medium leading-[0.9] tracking-[-0.03em]">${esc(fmtMoney(L.rent))}</span>
      <span class="font-serif text-2xl md:text-3xl">/month</span>
    </p>

    <ul id="listing-facts" role="list" class="mt-10 flex flex-wrap gap-3">
      ${factTiles(L)}
    </ul>

    <p class="mt-10"><a href="#inquire" class="${LINK}">Curious? Let's talk &rarr;</a></p>
  </div>
</section>

<section class="bg-eb-cream" aria-labelledby="photos-heading">
  <div class="mx-auto max-w-[1440px] px-[var(--eb-space-margin)]">
    <h2 id="photos-heading" class="sr-only">Photos</h2>
    ${photoTiles(L, title)}
  </div>
</section>

<section class="bg-eb-cream" aria-labelledby="about-heading">
  <div class="mx-auto max-w-[1440px] px-[var(--eb-space-margin)] py-[max(3.5rem,calc(var(--eb-space-margin)*1))]">
    <h2 id="about-heading" class="font-serif text-sm font-medium uppercase tracking-[0.08em]">${commercial ? 'About this space' : 'About this home'}</h2>
    ${summary ? `<p id="listing-summary" class="mt-6 max-w-[46rem] font-serif text-2xl leading-[1.35] sm:text-[1.75rem] md:text-[2rem]">${esc(summary)}</p>` : ''}
    ${featureTags(L, commercial)}
  </div>
</section>

<section id="location" class="${commercial ? 'eb-field-mustard' : 'eb-field-sand'} p-[clamp(1.5rem,4vw,3.5rem)]" aria-labelledby="location-heading">
  <div class="mx-auto max-w-[1440px]">
    <div class="eb-card ${mapped ? 'grid gap-10 lg:grid-cols-[6fr_7fr] lg:gap-16' : 'max-w-[44rem]'}">
      <div>
        <h2 id="location-heading" class="font-serif text-[length:var(--eb-h2-size)] font-medium leading-[1.1]">Where it is</h2>
        <address class="mt-6 font-serif text-2xl not-italic leading-[1.3] md:text-3xl">${addressLines}</address>
        <p class="mt-8"><a href="${esc(osmUrl)}" class="${LINK}">${mapped ? 'Open in OpenStreetMap' : 'Find it on OpenStreetMap'} &rarr;</a></p>
      </div>
      ${mapBlock}
    </div>
  </div>
</section>

<section id="inquire" class="bg-eb-berry text-eb-cream" aria-labelledby="inquire-heading">
  <div class="mx-auto max-w-[1440px] px-[var(--eb-space-margin)] py-[max(4.5rem,calc(var(--eb-space-margin)*1.25))]">
    <div class="grid gap-10 lg:grid-cols-[5fr_7fr] lg:gap-16">
      <div>
        <h2 id="inquire-heading" class="max-w-[14ch] text-balance font-serif text-[length:var(--eb-h2-size)] font-medium leading-[1.1]">Curious? Let's talk.</h2>
        <p class="mt-4 max-w-[26rem]">Tell me a little about yourself and what you have in mind. A line or two is plenty. I read every note myself and will write back within a few business days.</p>
      </div>

      <div class="eb-card">
        <!-- Declared (data-netlify) on every generated /listings/<id>/ page, which is how Netlify knows this form. -->
        <form id="listing-inquiry-form" name="listing-inquiry" method="POST" data-netlify="true" netlify-honeypot="bot-field" class="grid gap-5 sm:grid-cols-2">
          <input type="hidden" name="form-name" value="listing-inquiry" />
          <input type="hidden" name="listing" value="${esc(L.id)}" />
          <input type="hidden" name="building" value="${building ? esc(building.id) : ''}" />
          <p class="hidden">
            <label>Don't fill this out: <input name="bot-field" class="bg-eb-cream" /></label>
          </p>

          <label>
            <span class="mb-1.5 block text-base font-medium">Name <span aria-hidden="true">*</span></span>
            <input name="name" required autocomplete="name"
                   class="block w-full rounded-[12px] border-[1.5px] border-eb-berry bg-eb-cream px-4 py-3 font-serif text-lg text-eb-berry" />
          </label>

          <label>
            <span class="mb-1.5 block text-base font-medium">Email <span aria-hidden="true">*</span></span>
            <input type="email" name="email" required autocomplete="email"
                   class="block w-full rounded-[12px] border-[1.5px] border-eb-berry bg-eb-cream px-4 py-3 font-serif text-lg text-eb-berry" />
          </label>

          <label>
            <span class="mb-1.5 block text-base font-medium">Phone <span class="font-normal">(optional)</span></span>
            <input type="tel" name="phone" autocomplete="tel"
                   class="block w-full rounded-[12px] border-[1.5px] border-eb-berry bg-eb-cream px-4 py-3 font-serif text-lg text-eb-berry" />
          </label>

          <label>
            <span class="mb-1.5 block text-base font-medium">Move-in timeframe</span>
            <select name="timeframe"
                    class="eb-select block w-full rounded-[12px] border-[1.5px] border-eb-berry bg-eb-cream px-4 py-3 font-serif text-lg text-eb-berry">
              <option value="">Choose one</option>
              <option value="As soon as possible">As soon as possible</option>
              <option value="1–3 months">1–3 months</option>
              <option value="Later">Later</option>
              <option value="Just curious">Just curious</option>
            </select>
          </label>

          <label class="sm:col-span-2">
            <span class="mb-1.5 block text-base font-medium">Anything I should know?</span>
            <textarea name="message" rows="5"
                      class="block w-full rounded-[12px] border-[1.5px] border-eb-berry bg-eb-cream px-4 py-3 font-serif text-lg text-eb-berry placeholder:text-eb-berry/70"></textarea>
          </label>

          <div class="sm:col-span-2 flex flex-wrap items-center gap-x-6 gap-y-3">
            <button type="submit" class="eb-btn cursor-pointer px-9 py-2.5 text-2xl">Ask about this space</button>
            <p class="text-base">I don't share your contact information. Ever.</p>
          </div>
        </form>

        <p class="mt-8 text-base">Or just email me &mdash; <a href="mailto:me@ebberry.com" class="underline decoration-eb-tangerine decoration-2 underline-offset-4 hover:decoration-eb-berry">me@ebberry.com</a>.</p>
      </div>
    </div>
  </div>
</section>`;
  }

  // The warm "not on my list" page (unknown id, or no id at all), and the can't-load page.
  function messageHTML(heading, body, extra) {
    return `
<section class="bg-eb-cream" aria-labelledby="listing-title">
  <div class="mx-auto max-w-[1440px] px-[var(--eb-space-margin)] py-[max(4.5rem,calc(var(--eb-space-margin)*1.25))]">
    <div class="flex items-start justify-between gap-6">
      <div>
        <h1 id="listing-title" class="max-w-[16ch] text-balance font-serif text-[length:var(--eb-h1-size)] font-medium leading-[1.08] tracking-[-0.01em]">${heading}</h1>
        <p class="mt-4 max-w-[34rem] text-xl leading-[1.4]">${body}</p>
        <p class="mt-8 flex flex-wrap gap-x-10 gap-y-4">
          <a href="/listings/" class="${LINK}">&larr; Everything that's open</a>
          ${extra}
        </p>
      </div>
      ${SEAL}
    </div>
  </div>
</section>`;
  }

  const notFoundHTML = () => messageHTML(
    "That one isn't on my list just now.",
    "It may have been rented, or the link may have a typo. Take a look at everything that's open, or tell me what you're looking for and I'll keep an eye out.",
    `<a href="/#inquire" class="${LINK}">Tell me what you're looking for &rarr;</a>`);

  const failedHTML = () => messageHTML(
    "I couldn't load this just now.",
    'Please try again in a moment, or email me and I\'ll tell you what\'s open.',
    `<a href="mailto:me@ebberry.com" class="${LINK}">me@ebberry.com</a>`);

  // ---- the single-marker map: built only once it is near the screen ----
  function watchMap() {
    const el = document.getElementById('listing-map');
    const wrap = document.getElementById('listing-map-wrap');
    if (!el || !wrap || !window.EBMap || !window.EBMap.supported()) return;     // the address and the OpenStreetMap link stand on their own
    wrap.classList.remove('hidden');
    let built = false;
    function build() {
      if (built) return;
      built = true;
      const d = el.dataset;
      const lat = parseFloat(d.lat), lng = parseFloat(d.lng);
      try {
        // A popup that links back to this very page would only be noise: plain pin, no popup.
        window.EBMap.create(el, [{
          id: d.id, lat: lat, lng: lng, title: d.title, rent: Number(d.rent)
        }], { label: 'Map showing ' + d.title, zoom: 15.5, popups: false });
      } catch (err) {
        wrap.classList.add('hidden');
      }
    }
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(function (es) {
        if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); build(); }
      }, { rootMargin: '200px' });
      io.observe(el);
    } else {
      build();
    }
  }

  // ---- which listing? /listings/<id>/ (through the rewrite) wins, then ?id= ----
  function slugFromLocation() {
    const m = /^\/listings\/([^/]+)\/?$/.exec(location.pathname);
    let slug = '';
    if (m && m[1] !== 'index.html') {
      try { slug = decodeURIComponent(m[1]); } catch (e) { slug = m[1]; }
    }
    if (!slug) slug = new URLSearchParams(location.search).get('id') || '';
    return slug.trim();
  }

  async function fetchJSON(url) {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  function show(main, html, title) {
    main.innerHTML = html;
    if (title) document.title = title;
    if (location.hash) {                       // the content arrived after the browser's own jump to #inquire
      let id = location.hash.slice(1);
      try { id = decodeURIComponent(id); } catch (e) { /* use it as typed */ }
      const t = document.getElementById(id);
      if (t) t.scrollIntoView();
    }
  }

  async function init() {
    const main = document.getElementById('main');
    if (!main) return;
    const slug = slugFromLocation();
    let feed;
    try {
      const url = (window.EB && window.EB.LISTINGS_URL) || '/data/listings.json';
      feed = await fetchJSON(url);
    } catch (err) {
      show(main, failedHTML(), "Couldn't load — E. Berry Property Management");
      return;
    }
    const list = (Array.isArray(feed) ? feed : (feed.listings || [])).filter(L => L && L.id && typeof L.rent === 'number');
    const L = slug ? list.find(x => x.id === slug) : null;
    if (!L) {
      show(main, notFoundHTML(), "Not on my list — E. Berry Property Management");
      return;
    }
    // The building name for the breadcrumb is optional: no buildings file, no "Part of" link.
    let building = null;
    if (L.buildingId) {
      try {
        const doc = await fetchJSON('/data/buildings.json');
        building = (doc.buildings || []).find(b => b && b.id === L.buildingId) || null;
      } catch (err) { /* leave it out */ }
    }
    document.body.dataset.listing = L.id;
    show(main, detailHTML(L, building),
      `${L.title || L.id} — ${fmtMoney(L.rent)}/mo on Vashon — E. Berry Property Management`);
    watchMap();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
