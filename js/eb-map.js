/* E. Berry brand map: a small wrapper around the vendored MapLibre GL JS (js/vendor/maplibre-gl.js), drawing the
 * self-hosted Vashon-Maury basemap (map/vashon.pmtiles, read through js/vendor/pmtiles.js, styled by map/style.json).
 *
 *   window.EBMap.create(el, points, opts)  ->  the MapLibre map instance
 *   window.EBMap.supported()               ->  true when MapLibre is loaded and the browser has WebGL
 *
 * points   [{ id, lat, lng, title, rent, address?, meta?, muted? }]
 *          Points with the same lat/lng are GROUPED into one pin (all eight Courthouse Square suites share one
 *          coordinate); its popup lists every listing in the group.
 *          Points without numeric lat/lng are skipped. `meta` is plain text ("259 sq ft · available now").
 * opts     label          aria-label for the map region
 *          isMuted(point) true -> the pin renders as the hollow Berry-outline variant (.eb-pin--muted);
 *                         a group is muted only when every point in it is
 *          linkBase       listing URL prefix, default '/listings/' (links are linkBase + id + '/')
 *          zoom           zoom to use when the view is centred on a single pin (default 15)
 *          popups         false -> pins are plain markers with no popup (a page does not link to itself)
 *
 * The map gets three extra members:
 *   map.ebSetPoints(points, fit = true)   replace the pins (re-grouping), and refit the view unless fit === false
 *   map.ebFit()                           refit the view to the current pins
 *   map.ebCalm                            true when prefers-reduced-motion asked for no animation
 * and every map is also pushed onto window.EBMap.maps (the tests read the view from there).
 *
 * Needs css/vendor/maplibre-gl.css then css/eb-map.css, the --eb-* tokens from css/tailwind.css, and js/vendor/pmtiles.js
 * (without it the map still shows Cream, pins and place names, just no basemap).
 * Attribution is required by the OpenStreetMap licence (ODbL) and is always shown.
 *
 * There are no text layers in the style, so the place names are HTML labels (non-interactive markers).
 */
(function () {
  'use strict';

  const STYLE_URL = '/map/style.json';
  // Used when js/vendor/pmtiles.js is missing: the style's source could not be read, so do not even ask for it.
  const BARE_STYLE = { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#F1ECE9' } }] };
  const PMTILES_PROTOCOL = 'pmtiles';
  const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &middot; <a href="https://protomaps.com">Protomaps</a>';
  const ISLAND = [-122.4600, 47.4200];     // [lng, lat]: all of Vashon at zoom 11
  const ISLAND_ZOOM = 11;
  // Hard pan limit: Vashon + Maury with a little water around them. The map is about the island;
  // nobody needs to scroll to Tacoma. MapLibre wants [[west, south], [east, north]].
  const ISLAND_BOUNDS = [[-122.62, 47.28], [-122.30, 47.57]];
  const MIN_ZOOM = 11, MAX_ZOOM = 15.5;
  const PIN_W = 34, PIN_H = 44;
  const POPUP_PAD = 24;

  // Curated place names: sparse and editorial, not a gazetteer. Drawn as HTML so the style needs no font files.
  // `anchor`/`offset` keep a name clear of a pin that sits on the same spot (Courthouse Square is in Vashon town).
  const PLACE_LABELS = [
    { name: 'Vashon',               lat: 47.4474, lng: -122.4600, kind: 'town',  anchor: 'left', offset: [26, -16], minzoom: 11, maxzoom: 14.5 },
    { name: 'Burton',               lat: 47.3978, lng: -122.4633, kind: 'town',  minzoom: 11, maxzoom: 15.5 },
    { name: 'Dockton',              lat: 47.3727, lng: -122.4557, kind: 'town',  minzoom: 11, maxzoom: 15.5 },
    { name: 'Maury Island',         lat: 47.3770, lng: -122.4190, kind: 'area',  minzoom: 11, maxzoom: 14.5 },
    { name: 'Vashon Heights ferry', lat: 47.5102, lng: -122.4639, kind: 'ferry', minzoom: 11, maxzoom: 15.5 },
    { name: 'Tahlequah ferry',      lat: 47.3318, lng: -122.5068, kind: 'ferry', minzoom: 11, maxzoom: 15.5 }
  ];

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

  // Where a popup sits relative to the pin's tip, whichever side MapLibre anchors it on: clear of the 44px pin.
  const POPUP_OFFSET = {
    'top': [0, 10], 'top-left': [0, 10], 'top-right': [0, 10],
    'bottom': [0, -(PIN_H - 2)], 'bottom-left': [0, -(PIN_H - 2)], 'bottom-right': [0, -(PIN_H - 2)],
    'left': [PIN_W / 2 + 2, -PIN_H / 2], 'right': [-(PIN_W / 2 + 2), -PIN_H / 2]
  };

  // ---- capability ----
  let webgl = null;
  function hasWebGL() {
    if (webgl === null) {
      try {
        const c = document.createElement('canvas');
        const ctx = c.getContext('webgl2') || c.getContext('webgl');
        webgl = !!ctx;
        const lose = ctx && ctx.getExtension && ctx.getExtension('WEBGL_lose_context');
        if (lose) lose.loseContext();                // the probe context is not needed again; do not spend one of the page's few
      } catch (e) { webgl = false; }
    }
    return webgl;
  }
  const supported = () => !!(window.maplibregl && hasWebGL());

  // `pmtiles://` -> js/vendor/pmtiles.js. Registered once; without the library the style's source simply fails to load
  // and the map degrades to its Cream background.
  let protocolReady = false;
  function ensureProtocol() {
    if (protocolReady) return true;
    if (!window.pmtiles || !window.maplibregl) return false;
    window.maplibregl.addProtocol(PMTILES_PROTOCOL, new window.pmtiles.Protocol().tile);
    protocolReady = true;
    return true;
  }

  // ---- the map ----
  function create(el, points, opts) {
    if (!window.maplibregl) throw new Error('EBMap: MapLibre GL (js/vendor/maplibre-gl.js) is not loaded');
    const gl = window.maplibregl;
    opts = opts || {};
    const linkBase = opts.linkBase || '/listings/';
    const isMuted = typeof opts.isMuted === 'function' ? opts.isMuted : p => !!p.muted;
    const singleZoom = typeof opts.zoom === 'number' ? opts.zoom : 15;
    const withPopups = opts.popups !== false;

    el.classList.add('eb-map');
    el.setAttribute('role', 'region');
    el.setAttribute('aria-label', opts.label || 'Map of the places that are open');

    // Reduced motion: no tile or label fade, no animated zoom/pan, and no animated nudge when a popup opens near an edge.
    // (MapLibre drops its own easing under prefers-reduced-motion too; this covers the tile fade.)
    const calm = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

    const map = new gl.Map({
      container: el,
      style: ensureProtocol() ? STYLE_URL : BARE_STYLE,
      center: ISLAND,
      zoom: ISLAND_ZOOM,
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
      maxBounds: ISLAND_BOUNDS,
      renderWorldCopies: false,
      // A flat, north-up map: no rotating, no tilting.
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      maxPitch: 0,
      fadeDuration: calm ? 0 : 200,
      attributionControl: false,
      canvasContextAttributes: { antialias: true }
    });
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();
    map.ebCalm = calm;

    map.addControl(new gl.NavigationControl({ showCompass: false, showZoom: true, visualizePitch: false }), 'top-left');
    map.addControl(new gl.AttributionControl({ compact: false, customAttribution: ATTRIBUTION }), 'bottom-right');

    // Anything that goes wrong with the basemap (no pmtiles library, a missing archive, a bad tile) must leave the
    // Cream map, the pins and the names working. MapLibre logs unhandled errors to the console, so handle them here.
    let warned = false;
    map.on('error', e => {
      if (warned) return;
      warned = true;
      if (window.console && console.warn) console.warn('EBMap: the basemap could not be drawn (' + ((e && e.error && e.error.message) || 'unknown') + '); showing the plain map');
    });

    // Wheel zoom: on after a click or keyboard focus, off again when the pointer leaves or focus moves on. The page
    // scrolls otherwise.
    map.scrollZoom.disable();
    map.on('click', () => map.scrollZoom.enable());
    const canvas = map.getCanvas();
    canvas.addEventListener('focus', () => map.scrollZoom.enable());
    canvas.addEventListener('blur', () => map.scrollZoom.disable());
    el.addEventListener('mouseleave', () => map.scrollZoom.disable());

    // ---- place names ----
    const labelEls = PLACE_LABELS.map(def => {
      const node = document.createElement('div');
      node.className = 'eb-map-label eb-map-label--' + def.kind;
      node.textContent = def.name;
      node.setAttribute('aria-hidden', 'true');
      node.setAttribute('role', 'presentation');
      node.setAttribute('aria-label', '');          // MapLibre would otherwise name every marker "Map marker"
      new gl.Marker({ element: node, anchor: def.anchor || 'center', offset: def.offset || [0, 0] })
        .setLngLat([def.lng, def.lat]).addTo(map);
      return { def, node };
    });
    function showLabels() {
      const z = map.getZoom();
      labelEls.forEach(l => l.node.classList.toggle('eb-map-label--off', z < l.def.minzoom || z > l.def.maxzoom));
    }
    map.on('zoom', showLabels);
    showLabels();

    // ---- pins ----
    let pins = [];
    let groups = [];

    function fit() {
      if (!groups.length) { map.jumpTo({ center: ISLAND, zoom: ISLAND_ZOOM }); return; }
      if (groups.length === 1) { map.jumpTo({ center: [groups[0].lng, groups[0].lat], zoom: singleZoom }); return; }
      const b = new gl.LngLatBounds();
      groups.forEach(g => b.extend([g.lng, g.lat]));
      map.fitBounds(b, { padding: 56, maxZoom: MAX_ZOOM, animate: false });
    }

    // Nudge the map so a freshly opened popup is not cut off by the edge of the frame.
    function nudgeIntoView(popup) {
      const box = popup.getElement();
      if (!box) return;
      const c = el.getBoundingClientRect(), r = box.getBoundingClientRect();
      let dx = 0, dy = 0;
      if (r.left < c.left + POPUP_PAD) dx = r.left - (c.left + POPUP_PAD);
      else if (r.right > c.right - POPUP_PAD) dx = r.right - (c.right - POPUP_PAD);
      if (r.top < c.top + POPUP_PAD) dy = r.top - (c.top + POPUP_PAD);
      else if (r.bottom > c.bottom - POPUP_PAD) dy = r.bottom - (c.bottom - POPUP_PAD);
      if (dx || dy) map.panBy([dx, dy], { animate: !calm, duration: 220 });
    }

    function clearPins() {
      pins.forEach(m => m.remove());       // removing a marker closes its popup
      pins = [];
    }

    function setPoints(pts, doFit) {
      clearPins();
      groups = groupPoints(pts);
      groups.forEach(g => {
        const muted = g.items.every(isMuted);
        const label = pinLabel(g);
        const node = document.createElement('div');
        node.className = 'eb-pin' + (muted ? ' eb-pin--muted' : '');
        node.innerHTML = pinHTML(g.items.length);
        node.title = label;
        node.setAttribute('aria-label', label);
        const marker = new gl.Marker({ element: node, anchor: 'bottom' }).setLngLat([g.lng, g.lat]);
        if (withPopups) {
          const popup = new gl.Popup({
            className: 'eb-popup', closeButton: true, closeOnClick: true, closeOnMove: false,
            maxWidth: '320px', offset: POPUP_OFFSET, focusAfterOpen: false
          }).setHTML(popupHTML(g, linkBase));
          // Focus moves into the popup only when it was opened from the keyboard (Enter or Space on the pin), so a
          // mouse click does not leave a focus ring on the first link.
          let byKey = false, closeHooked = false;
          node.addEventListener('keydown', e => { byKey = e.key === 'Enter' || e.key === ' '; });
          popup.on('open', () => {
            requestAnimationFrame(() => nudgeIntoView(popup));
            const box = popup.getElement();
            const first = box && box.querySelector('a[href], button');
            if (byKey && first) first.focus({ preventScroll: true });
            byKey = false;
            // The keyboard's way out: Enter or Space on the close button hands the focus back to the pin. (MapLibre keeps
            // one close button for the life of the popup, so hook it once.)
            const x = box && box.querySelector('.maplibregl-popup-close-button');
            if (x && !closeHooked) {
              closeHooked = true;
              x.addEventListener('click', e => { if (e.detail === 0) node.focus({ preventScroll: true }); });
            }
          });
          marker.setPopup(popup);
          node.setAttribute('role', 'button');
          node.setAttribute('aria-haspopup', 'dialog');
        } else {
          node.setAttribute('role', 'img');   // nothing to press: a picture of where it is
        }
        marker.addTo(map);
        pins.push(marker);
      });
      if (doFit !== false) fit();
    }

    // Escape closes the open popup (a mouse click leaves focus on the page, so listen on the document, but only for keys
    // pressed on the page itself or inside this map) and, if the keyboard was inside the popup, hands the focus back to its pin.
    document.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      if (e.target !== document.body && e.target !== document.documentElement && !el.contains(e.target)) return;
      pins.forEach(m => {
        const p = m.getPopup();
        if (!p || !p.isOpen()) return;
        const box = p.getElement();
        const inside = !!box && box.contains(document.activeElement);
        p.remove();
        if (inside) m.getElement().focus({ preventScroll: true });
      });
    });

    map.ebSetPoints = setPoints;
    map.ebFit = fit;
    setPoints(points, true);

    // The container can change size without a window resize (sticky pane, mobile List/Map swap).
    if (window.ResizeObserver) {
      new ResizeObserver(() => map.resize()).observe(el);
    }
    (window.EBMap.maps = window.EBMap.maps || []).push(map);
    return map;
  }

  window.EBMap = { create, supported, groupPoints, maps: [] };
})();
