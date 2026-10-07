#!/usr/bin/env python3
"""Write the PLACEHOLDER basemap archive, map/vashon.pmtiles.

The real archive is a cut of the Protomaps planet build (tools/extract_pmtiles.py). Until that has been run,
this script writes a tiny but fully VALID PMTiles v3 archive so the whole map pipeline (the style, the `pmtiles://`
protocol, HTTP Range requests, MapLibre drawing the brand palette) works end to end and every test gate can run
without network access:

  * nine z11 vector tiles that cover the whole island bbox (-122.62,47.28,-122.30,47.57), gzip-compressed MVT,
    the same tile type and compression the Protomaps builds use
  * header min/max zoom 11, so MapLibre overzooms them up to the map's maxZoom
  * the Protomaps layer and field names the style reads (see map/style.json):
      water      the sea: the whole tile minus the island
      earth      a rough hand-drawn outline of Vashon + Maury Island (NOT survey data)
      landuse    a park, a forest and a beach
      roads      one major road end to end, a few minor roads, two ferry routes
      buildings  two footprints where Courthouse Square stands
  * metadata: {"eberry": {"placeholder": true, ...}} so anything can tell this file from the real extract

Output is byte-for-byte reproducible (fixed gzip mtime, sorted tiles), so re-running it must not change the file.

Needs:  pip install pmtiles mapbox-vector-tile     (the latter brings shapely)
Run:    python3 tools/make_fixture_pmtiles.py [--out map/vashon.pmtiles]
"""

import argparse
import gzip
import math
import os
import sys

try:
    import mapbox_vector_tile
    from pmtiles.reader import MmapSource, Reader, all_tiles
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import write
    from shapely.geometry import LineString, Polygon, box
except ImportError as e:
    sys.exit(f'make_fixture_pmtiles: {e}. Install the tools with:  pip install pmtiles mapbox-vector-tile')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BBOX = (-122.62, 47.28, -122.30, 47.57)      # west, south, east, north: the same box js/eb-map.js locks panning to
ZOOM = 11
EXTENT = 4096
BUFFER = 128                                  # tile units of geometry kept past each edge, so lines and fills do not show seams
ATTRIBUTION = '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> | <a href="https://protomaps.com">Protomaps</a>'

# ---------------------------------------------------------------- the made-up island (lng, lat), clockwise from the north tip
ISLAND = [
    (-122.4660, 47.5120), (-122.4540, 47.5075), (-122.4465, 47.4975), (-122.4440, 47.4850), (-122.4410, 47.4700),
    (-122.4390, 47.4560), (-122.4350, 47.4440), (-122.4300, 47.4330), (-122.4290, 47.4235),
    # Maury Island: north shore east, round Point Robinson, south shore west
    (-122.4150, 47.4190), (-122.3950, 47.4130), (-122.3800, 47.4030), (-122.3735, 47.3935), (-122.3725, 47.3850),
    (-122.3800, 47.3720), (-122.3950, 47.3640), (-122.4150, 47.3580), (-122.4350, 47.3570), (-122.4500, 47.3640),
    # Quartermaster Harbor: up the Maury side to its head, down the Vashon side
    (-122.4570, 47.3700), (-122.4560, 47.3790), (-122.4590, 47.3900), (-122.4600, 47.4000),
    (-122.4680, 47.3990), (-122.4730, 47.3900), (-122.4770, 47.3790), (-122.4830, 47.3670),
    # the south tip and the west (Colvos Passage) coast
    (-122.4900, 47.3560), (-122.5000, 47.3430), (-122.5068, 47.3340), (-122.5100, 47.3300),
    (-122.5180, 47.3380), (-122.5250, 47.3560), (-122.5280, 47.3800), (-122.5300, 47.4050), (-122.5280, 47.4300),
    (-122.5240, 47.4550), (-122.5160, 47.4750), (-122.5050, 47.4900), (-122.4900, 47.5030), (-122.4750, 47.5100),
]

MAJOR_ROAD = [(-122.4660, 47.5090), (-122.4640, 47.4950), (-122.4600, 47.4700), (-122.4600, 47.4474), (-122.4630, 47.4250),
              (-122.4640, 47.4080), (-122.4720, 47.4010), (-122.4790, 47.3880), (-122.4880, 47.3650), (-122.4980, 47.3480),
              (-122.5060, 47.3340)]
MINOR_ROADS = [
    [(-122.5200, 47.4474), (-122.4900, 47.4480), (-122.4600, 47.4474), (-122.4380, 47.4500)],
    [(-122.4620, 47.4090), (-122.4400, 47.4120), (-122.4150, 47.4160), (-122.3900, 47.4110)],
    [(-122.4600, 47.4700), (-122.4800, 47.4720), (-122.5100, 47.4690)],
    [(-122.4790, 47.3880), (-122.5000, 47.3900), (-122.5230, 47.3880)],
    [(-122.4560, 47.3790), (-122.4400, 47.3720), (-122.3900, 47.3700)],
]
FERRIES = [[(-122.4639, 47.5102), (-122.4300, 47.5170), (-122.3935, 47.5231)],      # Vashon Heights toward Fauntleroy
           [(-122.5068, 47.3318), (-122.5130, 47.3180), (-122.5200, 47.3050)]]      # Tahlequah toward Point Defiance
PARK = [(-122.4870, 47.4100), (-122.4750, 47.4100), (-122.4750, 47.4220), (-122.4870, 47.4220)]
FOREST = [(-122.5200, 47.3950), (-122.4950, 47.3950), (-122.4900, 47.4100), (-122.5000, 47.4300), (-122.5230, 47.4250)]
BEACH = [(-122.4520, 47.3665), (-122.4440, 47.3640), (-122.4400, 47.3660), (-122.4480, 47.3690)]
# Two footprints with a courtyard between them (a stand-in for the north and south Courthouse Square buildings), so the
# pin sits in the gap and the footprints do not read as a drop shadow under it.
BUILDINGS = [[(-122.46075, 47.44722), (-122.45925, 47.44722), (-122.45925, 47.44752), (-122.46075, 47.44752)],
             [(-122.46075, 47.44668), (-122.45925, 47.44668), (-122.45925, 47.44698), (-122.46075, 47.44698)]]


# ---------------------------------------------------------------- tile math
def lonlat_to_xy(lng, lat):
    """Web Mercator metres."""
    x = lng * 20037508.342789244 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * 20037508.342789244 / math.pi
    return x, y


def lonlat_to_tile(lng, lat, z):
    n = 1 << z
    x = int((lng + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_bounds_xy(z, x, y):
    size = 2 * 20037508.342789244 / (1 << z)
    minx = -20037508.342789244 + x * size
    maxy = 20037508.342789244 - y * size
    return minx, maxy - size, minx + size, maxy


def tiles_covering(bbox, z):
    x0, y1 = lonlat_to_tile(bbox[0], bbox[1], z)       # south-west corner: smallest x, largest y
    x1, y0 = lonlat_to_tile(bbox[2], bbox[3], z)       # north-east corner
    return [(z, x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def project(points):
    return [lonlat_to_xy(lng, lat) for lng, lat in points]


# ---------------------------------------------------------------- features, in Web Mercator metres
def features():
    island = Polygon(project(ISLAND))
    assert island.is_valid and island.area > 0, 'the island outline must be a valid polygon'
    world = box(*[v for v in (-20037508.342789244, -20037508.342789244, 20037508.342789244, 20037508.342789244)])
    sea = world.difference(island)
    return {
        'water': [(sea, {'kind': 'ocean'})],
        'earth': [(island, {'kind': 'earth'})],
        'landuse': [(Polygon(project(PARK)), {'kind': 'park'}),
                    (Polygon(project(FOREST)), {'kind': 'forest'}),
                    (Polygon(project(BEACH)), {'kind': 'beach'})],
        'roads': [(LineString(project(MAJOR_ROAD)), {'kind': 'major_road', 'kind_detail': 'secondary'})]
                 + [(LineString(project(r)), {'kind': 'minor_road', 'kind_detail': 'residential'}) for r in MINOR_ROADS]
                 + [(LineString(project(r)), {'kind': 'ferry', 'kind_detail': 'ferry'}) for r in FERRIES],
        'buildings': [(Polygon(project(b)), {'kind': 'building'}) for b in BUILDINGS],
    }


def encode_tile(feats, z, x, y):
    minx, miny, maxx, maxy = tile_bounds_xy(z, x, y)
    pad = (maxx - minx) * BUFFER / EXTENT
    clip = box(minx - pad, miny - pad, maxx + pad, maxy + pad)
    layers = []
    for name in sorted(feats):                        # fixed order => reproducible bytes
        out = []
        for geom, props in feats[name]:
            g = geom.intersection(clip)
            if g.is_empty:
                continue
            out.append({'geometry': g, 'properties': props})
        if out:
            layers.append({'name': name, 'features': out})
    mvt = mapbox_vector_tile.encode(layers, default_options={'quantize_bounds': (minx, miny, maxx, maxy), 'extents': EXTENT})
    return gzip.compress(mvt, mtime=0)


def build(out_path):
    feats = features()
    tiles = sorted(tiles_covering(BBOX, ZOOM), key=lambda t: zxy_to_tileid(*t))
    west, south, east, north = BBOX
    header = {
        'tile_compression': Compression.GZIP,
        'tile_type': TileType.MVT,
        'min_lon_e7': round(west * 1e7), 'min_lat_e7': round(south * 1e7),
        'max_lon_e7': round(east * 1e7), 'max_lat_e7': round(north * 1e7),
        'center_zoom': 11,
        'center_lon_e7': round(-122.46 * 1e7), 'center_lat_e7': round(47.42 * 1e7),
    }
    metadata = {
        'name': 'Vashon-Maury Island (PLACEHOLDER)',
        'description': 'Hand-made stand-in for the Protomaps extract. A rough island outline, not survey data. '
                       'Replace with the output of tools/extract_pmtiles.py.',
        'attribution': ATTRIBUTION,
        'type': 'baselayer',
        'format': 'pbf',
        'version': '1',
        'vector_layers': [{'id': n, 'fields': {k: 'String' for k in sorted({k for _, p in feats[n] for k in p})},
                           'minzoom': ZOOM, 'maxzoom': ZOOM} for n in sorted(feats)],
        'eberry': {'placeholder': True, 'generator': 'tools/make_fixture_pmtiles.py', 'bbox': list(BBOX), 'zoom': ZOOM},
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with write(out_path) as w:
        for z, x, y in tiles:
            w.write_tile(zxy_to_tileid(z, x, y), encode_tile(feats, z, x, y))
        w.finalize(header, metadata)
    return tiles


def verify(out_path, tiles):
    """Open the file we just wrote, the way a client would, and make sure everything is there and decodes."""
    with open(out_path, 'rb') as f:
        reader = Reader(MmapSource(f))
        h = reader.header()
        assert (h['min_zoom'], h['max_zoom']) == (ZOOM, ZOOM), h
        assert h['tile_type'] == TileType.MVT and h['tile_compression'] == Compression.GZIP and h['clustered'], h
        assert reader.metadata()['eberry']['placeholder'] is True
        for z, x, y in tiles:
            data = reader.get(z, x, y)
            assert data, f'tile {z}/{x}/{y} is missing'
            decoded = mapbox_vector_tile.decode(gzip.decompress(data))
            assert 'water' in decoded or 'earth' in decoded, f'tile {z}/{x}/{y} has no basemap layers'
        assert sum(1 for _ in all_tiles(reader.get_bytes)) == len(tiles)
    with open(out_path, 'rb') as f:
        assert f.read(8) == b'PMTiles\x03', 'bad magic bytes'


def main():
    ap = argparse.ArgumentParser(description='Write the placeholder map/vashon.pmtiles.')
    ap.add_argument('--out', default=os.path.join(ROOT, 'map', 'vashon.pmtiles'))
    args = ap.parse_args()
    tiles = build(args.out)
    verify(args.out, tiles)
    print(f'wrote {os.path.relpath(args.out, ROOT) if args.out.startswith(ROOT) else args.out}: '
          f'{len(tiles)} z{ZOOM} tiles, {os.path.getsize(args.out):,} bytes (PLACEHOLDER, replace with tools/extract_pmtiles.py)')


if __name__ == '__main__':
    main()
