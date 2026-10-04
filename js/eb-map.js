/* E. Berry brand map: a small wrapper around the vendored Leaflet (js/vendor/leaflet.js).
 *
 *   window.EBMap.create(el, points, opts)  ->  the Leaflet map instance
 *
 * points   [{ id, lat, lng, title, rent, address?, meta?, muted? }]
 *          Points with the same lat/lng are GROUPED into one marker (all eight Courthouse Square
 *          suites share one coordinate); its popup lists every listing in the group.
 *          Points without numeric lat/lng are skipped. `meta` is plain text ("259 sq ft · available now").
 * opts     label          aria-label for the map region
 *          isMuted(point) true -> the pin renders as the hollow Berry-outline variant (.eb-pin--muted);
 *                         a group is muted only when every point in it is
 *          linkBase       listing URL prefix, default '/listings/' (links are linkBase + id + '/')
 *
 * The map gets two extra methods:
 *   map.ebSetPoints(points, fit = true)   replace the markers (re-grouping), and refit the view unless fit === false
 *   map.ebFit()                           refit the view to the current markers
 *
 * Needs css/vendor/leaflet.css then css/eb-map.css, and the --eb-* tokens from css/tailwind.css.
 * Tiles are OpenStreetMap's; the attribution is required and always shown.
 */
(function () {
  'use strict';

  const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  const ISLAND = [47.4200, -122.4600];     // all of Vashon Island at zoom 11
  const ISLAND_ZOOM = 11;
  const PIN_W = 34, PIN_H = 44;

  // ---- helpers (duplicated from index.html / js/building.js / js/listings.js on purpose: those pages
  //      are generated or frozen, so there is no shared module to import from) ----
  const fmtMoney = n => Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  const hasCoords = p => p && typeof p.lat === 'number' && typeof p.lng === 'number' && isFinite(p.lat) && isFinite(p.lng);

  // "Suite N101 — Courthouse Square" -> { unit: 'Suite N101', place: 'Courthouse Square' }
  function splitTitle(title) {
    const m = /^(.*?)\s+[—–-]\s+(.+)$/.exec(String(title || ''));
    return m ? { unit: m[1], place: m[2] } : { unit: String(title || ''), place: '' };
  }

  // One group per distinct coordinate, in first-seen order.
  function groupPoints(points) {
    const groups = new Map();
    (points || []).filter(hasCoords).forEach(p => {
      const key = p.lat + ',' + p.lng;
      if (!groups.has(key)) groups.set(key, { lat: p.lat, lng: p.lng, items: [] });
      groups.get(key).items.push(p);
    });
    return [...groups.values()];
  }

  // Shared place name when every item in the group says "<unit> — <place>" with the same place.
  function groupPlace(items) {
    const places = items.map(p => splitTitle(p.title).place);
    return places.every(pl => pl && pl === places[0]) ? places[0] : '';
  }

  // ---- markup ----
  function pinHTML(count) {
    return '<svg class="eb-pin__svg" viewBox="0 0 ' + PIN_W + ' ' + PIN_H + '" width="' + PIN_W + '" height="' + PIN_H + '" aria-hidden="true" focusable="false">' +
             '<path class="eb-pin__body" d="M17 42C17 42 2.5 28 2.5 17a14.5 14.5 0 0 1 29 0C31.5 28 17 42 17 42Z"/>' +
             '<circle class="eb-pin__dot" cx="17" cy="17" r="5.5"/>' +
           '</svg>' +
           (count > 1 ? '<span class="eb-pin__count" aria-hidden="true">' + count + '</span>' : '');
  }

  function pinLabel(group) {
    const items = group.items;
    if (items.length === 1) return items[0].title + ', ' + fmtMoney(items[0].rent) + ' a month';
    const place = groupPlace(items);
    return items.length + ' places' + (place ? ' at ' + place : ' here');
  }

  function popupHTML(group, linkBase) {
    const href = p => esc(linkBase + encodeURIComponent(p.id) + '/');
    const items = group.items;
    if (items.length === 1) {
      const p = items[0];
      return '<div class="eb-pop">' +
        '<p class="eb-pop-title">' + esc(p.title) + '</p>' +
        '<p class="eb-pop-rent">' + fmtMoney(p.rent) + '<span>/mo</span></p>' +
        (p.meta ? '<p class="eb-pop-meta">' + esc(p.meta) + '</p>' : '') +
        (p.address ? '<p class="eb-pop-meta">' + esc(p.address) + '</p>' : '') +
        '<p class="eb-pop-cta"><a class="eb-pop-link" href="' + href(p) + '">Curious? Let\'s talk &rarr;</a></p>' +
      '</div>';
    }
    const place = groupPlace(items);
    return '<div class="eb-pop">' +
      '<p class="eb-pop-eyebrow">' + items.length + ' places open</p>' +
      '<p class="eb-pop-title">' + esc(place || 'Here') + '</p>' +
      '<ul class="eb-pop-list">' +
        items.map(p => '<li class="eb-pop-item"><a class="eb-pop-link" href="' + href(p) + '">' +
          esc(place ? splitTitle(p.title).unit : p.title) + '</a><span>' + fmtMoney(p.rent) + '/mo</span></li>').join('') +
      '</ul>' +
    '</div>';
  }

  // ---- the map ----
  function create(el, points, opts) {
    if (!window.L) throw new Error('EBMap: Leaflet (js/vendor/leaflet.js) is not loaded');
    const L = window.L;
    opts = opts || {};
    const linkBase = opts.linkBase || '/listings/';
    const isMuted = typeof opts.isMuted === 'function' ? opts.isMuted : p => !!p.muted;

    el.classList.add('eb-map');
    el.setAttribute('role', 'region');
    el.setAttribute('aria-label', opts.label || 'Map of the places that are open');

    const map = L.map(el, {
      center: ISLAND,
      zoom: ISLAND_ZOOM,
      minZoom: 9,
      maxZoom: 18,
      scrollWheelZoom: false           // the page scrolls; the wheel only zooms once the map is clicked or focused
    });

    L.tileLayer(TILE_URL, { maxZoom: 18, attribution: ATTRIBUTION, className: 'eb-map-tiles' }).addTo(map);
    // Leaflet's default prefix carries a flag graphic; keep the credit, drop the artwork.
    map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');

    // Wheel zoom: on after a click or keyboard focus, off again when the pointer leaves or focus moves on.
    map.on('click focus', () => map.scrollWheelZoom.enable());
    map.on('blur', () => map.scrollWheelZoom.disable());
    el.addEventListener('mouseleave', () => map.scrollWheelZoom.disable());

    const layer = L.layerGroup().addTo(map);
    let groups = [];

    function fit() {
      if (!groups.length) { map.setView(ISLAND, ISLAND_ZOOM, { animate: false }); return; }
      if (groups.length === 1) { map.setView([groups[0].lat, groups[0].lng], 15, { animate: false }); return; }
      map.fitBounds(groups.map(g => [g.lat, g.lng]), { padding: [56, 56], maxZoom: 16, animate: false });
    }

    function setPoints(pts, doFit) {
      layer.clearLayers();             // closes any popup that belonged to a removed marker
      groups = groupPoints(pts);
      groups.forEach(g => {
        const muted = g.items.every(isMuted);
        const label = pinLabel(g);
        const marker = L.marker([g.lat, g.lng], {
          icon: L.divIcon({
            className: 'eb-pin' + (muted ? ' eb-pin--muted' : ''),
            html: pinHTML(g.items.length),
            iconSize: [PIN_W, PIN_H],
            iconAnchor: [PIN_W / 2, PIN_H],
            popupAnchor: [0, -(PIN_H - 4)]
          }),
          title: label,
          keyboard: true,
          riseOnHover: true
        });
        marker.bindPopup(popupHTML(g, linkBase), {
          className: 'eb-popup', minWidth: 240, maxWidth: 320, autoPanPadding: [24, 24]
        });
        marker.addTo(layer);
        const icon = marker.getElement();
        if (icon) icon.setAttribute('aria-label', label);
      });
      if (doFit !== false) fit();
    }

    map.ebSetPoints = setPoints;
    map.ebFit = fit;
    setPoints(points, true);

    // The container can change size without a window resize (sticky pane, mobile List/Map swap).
    if (window.ResizeObserver) {
      new ResizeObserver(() => map.invalidateSize({ animate: false })).observe(el);
    }
    return map;
  }

  window.EBMap = { create, groupPoints };
})();
