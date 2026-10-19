# The basemap

The maps on `/listings/` and the listing pages are drawn by [MapLibre GL JS](https://maplibre.org) from a **self-hosted vector basemap**: no tile service, no API key, nothing fetched from a third party.

| File | What it is |
|---|---|
| `map/style.json` | The brand style: Cream land, Sky-tint water, Sage-tint parks, Sand beaches, Berry roads, dashed Berry ferry routes. Flat: no raster, no hillshade, no text layers. |
| `map/vashon.pmtiles` | The tiles: Vashon-Maury Island cut out of a Protomaps build, z0..z15, one file read with HTTP Range requests. |

The wiring is `js/eb-map.js`: it registers the PMTiles protocol (`js/vendor/pmtiles.js`) with MapLibre (`js/vendor/maplibre-gl.js`), so the style's `pmtiles:///map/vashon.pmtiles` source reads the archive straight off the site. Netlify answers Range requests natively; `netlify.toml` only adds a cache header for `/map/*` and must never get a redirect for it.

## `map/vashon.pmtiles` is a PLACEHOLDER until the real extract has been run

The committed file is a 2.4 KB stand-in written by `tools/make_fixture_pmtiles.py`: nine z11 tiles with a rough, hand-drawn outline of the island, a few roads, a park, a beach and two ferry routes, **not survey data and not OpenStreetMap**. It exists so the whole pipeline (style, protocol, Range requests, brand colors) works and every test can run offline. Its metadata says `{"eberry": {"placeholder": true}}`, and `python3 tools/check_site.py` prints a note while it is still there.

### Replace it with the real map

Protomaps publishes a planet build as `https://build.protomaps.com/YYYYMMDD.pmtiles` (daily; pick a recent date). The extract script reads it with Range requests, so nothing near its full size is ever downloaded:

```
pip install pmtiles mapbox-vector-tile
python3 tools/extract_pmtiles.py --url https://build.protomaps.com/YYYYMMDD.pmtiles \
    --bbox -122.62,47.28,-122.30,47.57 --maxzoom 15 --out map/vashon.pmtiles
```

Add `--dry-run` first to see what it would fetch (tiles, requests, megabytes) without writing anything. It keeps every tile that touches the bbox from z0 to z15, including the few low-zoom tiles that merely cover it, writes a clustered PMTiles v3 file with identical tiles stored once, and proves the result before moving it into place: magic bytes, header, a gunzip of every tile, and every tile byte-identical to what was downloaded. It stops with a message, writing nothing, on a server that ignores Range, an archive that changes mid-run, a missing low-zoom tile, or a plan over `--max-download-mb`.

Then:

1. `python3 tools/extract_pmtiles.py --inspect map/vashon.pmtiles` lists the zoom levels, the bounds and, for a sample tile in Vashon town, the layers and `kind` values. Check that `roads` has `major_road` and `minor_road`, that `landuse` has parks or forests, and whether ferry routes arrive as `kind=ferry` (see below).
2. `python3 tools/check_site.py` (the placeholder note should be gone) and `python3 tools/test_listings.py`.
3. Look at `/listings/` and a listing page in a browser at zoom 11 and zoom 15. The first load of the new archive is a cold cache; the PMTiles client revalidates on its ETag.
4. Commit `map/vashon.pmtiles`. A real Vashon extract at z15 is a few tens of megabytes; that is fine for git and for Netlify, which serves it in ranges.

### What the style expects of the tiles

`map/style.json` follows the Protomaps basemap tile schema (layer and field names taken from `@protomaps/basemaps` 5.7.2, the successor to `protomaps-themes-base`): source layers `earth`, `landuse` (`kind`: park, forest, wood, beach, sand, pier, ...), `water`, `roads` (`kind`: major_road, minor_road, highway, ...; `kind_detail`: service, pier, ...) and `buildings`. Two guesses to confirm against the real archive with `--inspect`:

- **Ferry routes.** The style draws any `roads` feature with `kind` or `kind_detail` equal to `ferry` as dashed Berry at 40% opacity. The schema documentation was not reachable when this was written. If ferries live in another layer or under another `kind`, change the `roads_ferry` layer in `style.json`; nothing else depends on it.
- **No text layers.** There are no `symbol` layers because there are no font files to fetch. Place names (Vashon, Burton, Dockton, Maury Island and the two ferry terminals) are HTML labels from `PLACE_LABELS` in `js/eb-map.js`.

`tools/check_site.py` enforces the style: version 8, one `vashon` source at `pmtiles:///map/vashon.pmtiles`, only background/fill/line layers, no glyphs, sprite or `text-field`, every color from the brand palette plus three tints (water `#A7C8D8`, greenspace `#CBD5BE`, minor roads `#DCCFC8`).

## Rules the data comes with

The tiles derive from OpenStreetMap (ODbL). The credit "(c) OpenStreetMap" linking to `https://www.openstreetmap.org/copyright`, plus "Protomaps", is drawn on every map by `js/eb-map.js` and the tests fail if it is not visible. Do not remove it.

## Tools

| Tool | Purpose |
|---|---|
| `tools/extract_pmtiles.py` | The one-shot cut from a Protomaps build (also `--dry-run` and `--inspect`). |
| `tools/make_fixture_pmtiles.py` | Writes the placeholder. Reproducible: running it again changes nothing. |
| `tools/test_extract_pmtiles.py` | Hermetic test of both, against a stand-in "planet" on a local Range server (CI: `.github/workflows/map-tools.yml`). Needs `pip install pmtiles==3.8.1 mapbox-vector-tile==2.2.0 shapely==2.2.0`. |
