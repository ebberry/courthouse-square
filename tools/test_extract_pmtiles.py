#!/usr/bin/env python3
"""Hermetic test for tools/extract_pmtiles.py and tools/make_fixture_pmtiles.py (no network beyond 127.0.0.1).

The extractor runs exactly once against the real Protomaps archive, so this test builds a stand-in "planet": a valid
PMTiles v3 archive of ~8,500 tiles with leaf directories, run-length entries and de-duplicated ocean tiles, served from
a local HTTP server that supports Range. It then checks:

  * the extract holds EXACTLY the tiles that intersect the bbox for z0..maxzoom (computed independently of the script),
    each byte-identical to the source, including the low-zoom tiles that merely cover the bbox
  * the header (tile type, compression, bounds, zoom range, clustered, root directory in the first 16 KiB)
  * it asks for ranges, never the whole file, and uses far fewer requests than tiles
  * it refuses: a server that ignores Range, an archive that changes mid-run, a missing low-zoom tile, an oversized
    plan, a corrupt tile; it retries a flaky server; --dry-run writes nothing; --bbox with a leading minus works
  * tools/make_fixture_pmtiles.py reproduces the committed placeholder map/vashon.pmtiles (tile for tile)

Needs: pip install pmtiles mapbox-vector-tile
Run:   python3 tools/test_extract_pmtiles.py
"""

import gzip
import http.server
import io
import math
import os
import re
import socketserver
import subprocess
import sys
import tempfile
import threading
from contextlib import redirect_stderr, redirect_stdout

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.dont_write_bytecode = True
sys.path.insert(0, TOOLS)

try:
    import mapbox_vector_tile
    import extract_pmtiles as X
    from pmtiles.reader import MmapSource, Reader, all_tiles
    from pmtiles.tile import Compression, Entry, TileType, serialize_directory, serialize_header, tileid_to_zxy, zxy_to_tileid
    from pmtiles.writer import build_roots_leaves
except ImportError as e:
    sys.exit(f'test_extract_pmtiles: {e}. Install the tools with:  pip install pmtiles mapbox-vector-tile')

BBOX = (-122.62, 47.28, -122.30, 47.57)
REGION = (-123.6, 46.8, -121.3, 48.0)               # where the stand-in planet has tiles above z6
failures, passed = [], 0


def check(ok, msg):
    global passed
    if ok:
        passed += 1
    else:
        failures.append(msg)


# ---------------------------------------------------------------- a stand-in planet archive
def tile_bounds(z, x, y):
    n = 1 << z
    west, east = x / n * 360 - 180, (x + 1) / n * 360 - 180
    lat = lambda yy: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return west, lat(y + 1), east, lat(y)


def universe(missing=()):
    """Every (z, x, y) in the stand-in planet: all of z0..z6, and z7..z13 inside REGION."""
    out = []
    for z in range(0, 14):
        n = 1 << z
        if z <= 6:
            out += [(z, x, y) for x in range(n) for y in range(n)]
            continue
        x0, x1 = int((REGION[0] + 180) / 360 * n), int((REGION[2] + 180) / 360 * n)
        y0 = int((1 - math.asinh(math.tan(math.radians(REGION[3]))) / math.pi) / 2 * n)
        y1 = int((1 - math.asinh(math.tan(math.radians(REGION[1]))) / math.pi) / 2 * n)
        out += [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    return [t for t in out if t not in missing]


def payload(z, x, y):
    """Valid gzip'd MVT. Every tile with (x//4 + y//4) % 5 == 0 above z7 is the same 'ocean' blob (so there are runs)."""
    if z >= 8 and (x // 4 + y // 4) % 5 == 0:
        z, x, y = 99, 0, 0
    layer = {'name': 'roads', 'features': [{'geometry': 'POINT(10 10)', 'properties': {'kind': 'major_road', 'zxy': f'{z}/{x}/{y}'}}]}
    return gzip.compress(mapbox_vector_tile.encode([layer]), mtime=0)


def write_source(path, tiles, leaf_size=64, corrupt=None):
    """A spec-conforming PMTiles v3 file with leaf directories and run-length entries. `corrupt`: a (z,x,y) whose data is not gzip."""
    blobs = {zxy_to_tileid(*t): payload(*t) for t in tiles}
    if corrupt:
        blobs[zxy_to_tileid(*corrupt)] = b'this is not gzip'
    entries, data, seen = [], bytearray(), {}
    for tid in sorted(blobs):
        blob = blobs[tid]
        if blob in seen:
            last = entries[-1] if entries else None
            if last and last.offset == seen[blob] and last.length == len(blob) and tid == last.tile_id + last.run_length:
                last.run_length += 1
            else:
                entries.append(Entry(tid, seen[blob], len(blob), 1))
        else:
            seen[blob] = len(data)
            entries.append(Entry(tid, len(data), len(blob), 1))
            data += blob
    root, leaves, n_leaves = build_roots_leaves(entries, leaf_size)
    assert n_leaves > 1 and len(root) < 16384 - 127
    meta = gzip.compress(('{"name": "stand-in planet", "attribution": "test", "vector_layers": [{"id": "roads"}]}').encode(), mtime=0)
    h = {'root_offset': 127, 'root_length': len(root), 'metadata_offset': 127 + len(root), 'metadata_length': len(meta),
         'leaf_directory_offset': 127 + len(root) + len(meta), 'leaf_directory_length': len(leaves),
         'tile_data_offset': 127 + len(root) + len(meta) + len(leaves), 'tile_data_length': len(data),
         'addressed_tiles_count': len(blobs), 'tile_entries_count': len(entries), 'tile_contents_count': len(seen),
         'clustered': True, 'internal_compression': Compression.GZIP, 'tile_compression': Compression.GZIP,
         'tile_type': TileType.MVT, 'min_zoom': 0, 'max_zoom': 13}
    with open(path, 'wb') as f:
        f.write(serialize_header(h) + root + meta + leaves + bytes(data))
    return blobs, entries


# ---------------------------------------------------------------- a local server with Range, and ways to misbehave
class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def do_GET(self):
        srv = self.server
        srv.log.append(self.headers.get('Range'))
        path = srv.files.get(self.path)
        if path is None:
            self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
        size = os.path.getsize(path)
        n = len(srv.log)
        if n <= srv.fail_first_requests + 0 and n > srv.fail_skip:
            self.send_response(503); self.send_header('Content-Length', '0'); self.end_headers(); return
        etag = '"v2"' if (srv.flip_etag_after and n > srv.flip_etag_after) else '"v1"'
        m = re.match(r'bytes=(\d+)-(\d+)$', self.headers.get('Range') or '')
        with open(path, 'rb') as f:
            if not m or not srv.ranges:
                body = f.read()
                self.send_response(200)
                for k, v in (('Content-Length', len(body)), ('ETag', etag), ('Content-Type', 'application/octet-stream')):
                    self.send_header(k, v)
                self.end_headers(); self.wfile.write(body); return
            start, end = int(m.group(1)), min(int(m.group(2)), size - 1)
            f.seek(start)
            body = f.read(end - start + 1)
        self.send_response(206)
        for k, v in (('Content-Range', f'bytes {start}-{end}/{size}'), ('Content-Length', len(body)), ('ETag', etag),
                     ('Accept-Ranges', 'bytes'), ('Content-Type', 'application/octet-stream')):
            self.send_header(k, v)
        self.end_headers()
        if srv.truncate and len(body) > 5000:
            self.wfile.write(body[:len(body) // 2]); self.wfile.flush(); self.close_connection = True; return
        self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(files):
    srv = Server(('127.0.0.1', 0), Handler)
    srv.files, srv.log = files, []
    srv.ranges, srv.flip_etag_after, srv.fail_first_requests, srv.fail_skip, srv.truncate = True, 0, 0, 0, False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def extract(argv_extra, url, out, factory=None):
    """Run the extractor in-process. -> (exit code, stdout, stderr)"""
    argv = ['--url', url, '--out', out] + argv_extra
    args = X.build_parser().parse_args(X.normalize_argv(argv))
    buf, err = io.StringIO(), io.StringIO()
    code = 0
    with redirect_stdout(buf), redirect_stderr(err):
        try:
            code = X.run(args, log=lambda m: print(m), client_factory=factory or X.RangeClient)
        except X.ExtractError as e:
            print(f'FAILED: {e}', file=sys.stderr); code = 1
    return code, buf.getvalue(), err.getvalue()


def archive_tiles(path):
    with open(path, 'rb') as f:
        r = Reader(MmapSource(f))
        return {zxy: bytes(blob) for zxy, blob in all_tiles(r.get_bytes)}, r.header(), r.metadata()


def main():
    tmp = tempfile.mkdtemp(prefix='extract_test_')
    src = os.path.join(tmp, 'planet.pmtiles')
    tiles = universe()
    blobs, entries = write_source(src, tiles)
    check(len(tiles) > 8000 and any(e.run_length > 1 for e in entries), f'setup: {len(tiles)} tiles, with run-length entries')
    srv = serve({'/planet.pmtiles': src})
    url = f'http://127.0.0.1:{srv.server_address[1]}/planet.pmtiles'

    # ---- tile math, on its own
    check(X.tiles_for_bbox((-122.62, 47.28, -122.30, 47.57), 0) == [(0, 0, 0)], 'tiles_for_bbox: z0 is the one world tile')
    got = X.tiles_for_bbox(BBOX, 11)
    check(len(got) == 9 and (11, 327, 716) in got, f'tiles_for_bbox: the island is 9 z11 tiles around 327/716 (got {len(got)})')
    edge = set(X.tiles_for_bbox((-90, -1, 0, 1), 2))
    check({(2, 1, 1), (2, 1, 2), (2, 2, 1), (2, 2, 2)} <= edge, f'tiles_for_bbox: a bbox on tile edges keeps the touching tiles ({sorted(edge)})')
    check(X.coalesce({(0, 10), (20, 10), (100000, 10)}, 50, 1 << 20) == [[0, 30, [(0, 10), (20, 10)]], [100000, 100010, [(100000, 10)]]],
          'coalesce: near tiles share a request, far ones do not')
    check(len(X.coalesce({(i * 10, 10) for i in range(100)}, 0, 200)) == 5, 'coalesce: max request length is honoured')
    check(X.normalize_argv(['--bbox', '-1,2,3,4', '--x']) == ['--bbox=-1,2,3,4', '--x'], 'normalize_argv: --bbox -1,... becomes --bbox=-1,...')

    # ---- the real thing: z0..13 for the island
    out = os.path.join(tmp, 'out.pmtiles')
    srv.log.clear()
    code, so, se = extract(['--bbox', '-122.62,47.28,-122.30,47.57', '--maxzoom', '13'], url, out)
    check(code == 0 and os.path.exists(out), f'extract: exit {code}: {se or so[-300:]}')
    if code == 0:
        want = {t for t in tiles if t[0] <= 13 and (lambda b: b[0] < BBOX[2] and b[2] > BBOX[0] and b[1] < BBOX[3] and b[3] > BBOX[1])(tile_bounds(*t))}
        got_tiles, h, meta = archive_tiles(out)
        check(set(got_tiles) == want, f'extract: tile set differs (missing {sorted(want - set(got_tiles))[:3]}, extra {sorted(set(got_tiles) - want)[:3]})')
        check(all(got_tiles[t] == blobs[zxy_to_tileid(*t)] for t in want if t in got_tiles), 'extract: every tile is byte-identical to the source')
        zooms = sorted({t[0] for t in got_tiles})
        check(zooms == list(range(14)), f'extract: zooms {zooms}; the covering tiles z0..z10 and z11..z13 must all be there')
        check(all(sum(1 for t in got_tiles if t[0] == z) >= 1 for z in range(0, 11)), 'extract: a covering tile at every zoom 0..10')
        check(h['clustered'] and h['tile_type'] == TileType.MVT and h['tile_compression'] == Compression.GZIP, f'extract: header type/compression/clustered {h}')
        check((h['min_zoom'], h['max_zoom']) == (0, 13), f'extract: zoom range {h["min_zoom"]}..{h["max_zoom"]}')
        check((h['min_lon_e7'], h['min_lat_e7'], h['max_lon_e7'], h['max_lat_e7']) == (-1226200000, 472800000, -1223000000, 475700000), 'extract: header bounds are the bbox')
        check(h['root_offset'] + h['root_length'] <= 16384, 'extract: root directory sits in the first 16 KiB')
        check(h['tile_contents_count'] < h['addressed_tiles_count'], f'extract: identical tiles are stored once ({h["tile_contents_count"]} of {h["addressed_tiles_count"]})')
        check(meta.get('name') == 'stand-in planet' and meta['eberry']['placeholder'] is False and meta['eberry']['source'] == url
              and meta['eberry']['bbox'] == list(BBOX) and meta['eberry']['maxzoom'] == 13, f'extract: metadata {meta}')
        with open(out, 'rb') as f:
            check(f.read(8) == b'PMTiles\x03', 'extract: magic bytes')
        ranges = [r for r in srv.log if r]
        check(len(ranges) == len(srv.log) and all(re.match(r'bytes=\d+-\d+$', r) for r in ranges), 'extract: every request carried a Range header')
        check(len(srv.log) < len(want) / 3, f'extract: {len(srv.log)} requests for {len(want)} tiles (coalesced)')
        check(not os.path.exists(out + '.tmp'), 'extract: no .tmp left behind')
        code2, so2, _ = extract(['--inspect', out], url, out)
        check(code2 == 0 and 'roads kinds: major_road' in so2 and 'placeholder=False' in so2, f'--inspect describes the extract: {so2[-200:]}')

    # ---- the CLI form from the brief (--bbox with a leading minus), through main(), plus --dry-run
    out2 = os.path.join(tmp, 'cli.pmtiles')
    r = subprocess.run([sys.executable, '-B', os.path.join(TOOLS, 'extract_pmtiles.py'), '--url', url, '--bbox', '-122.62,47.28,-122.30,47.57',
                        '--maxzoom', '12', '--out', out2], capture_output=True, text=True)
    check(r.returncode == 0 and os.path.exists(out2), f'CLI: exit {r.returncode}: {r.stderr[-300:]}')
    out3 = os.path.join(tmp, 'dry.pmtiles')
    code, so, se = extract(['--dry-run', '--maxzoom', '12'], url, out3)
    check(code == 0 and not os.path.exists(out3) and 'dry run' in so and 'MB to download' in so, f'--dry-run plans and writes nothing: {so[-200:]}')

    # ---- --maxzoom above what the source has is clamped
    out4 = os.path.join(tmp, 'clamp.pmtiles')
    code, so, se = extract(['--maxzoom', '15'], url, out4)
    _, h4, _ = archive_tiles(out4) if code == 0 else (None, {'max_zoom': None}, None)
    check(code == 0 and h4['max_zoom'] == 13 and 'source stops at z13' in so, f'maxzoom is clamped to the source ({h4["max_zoom"]})')

    # ---- refusals
    srv.ranges = False
    code, so, se = extract(['--maxzoom', '12'], url, os.path.join(tmp, 'norange.pmtiles'))
    check(code == 1 and 'byte ranges' in se and not os.path.exists(os.path.join(tmp, 'norange.pmtiles')), f'a server without Range is refused: {se[-200:]}')
    srv.ranges = True

    srv.log.clear(); srv.flip_etag_after = 3
    code, so, se = extract(['--maxzoom', '13'], url, os.path.join(tmp, 'flip.pmtiles'))
    check(code == 1 and 'changed mid-run' in se and not os.path.exists(os.path.join(tmp, 'flip.pmtiles')), f'an archive that changes mid-run is refused: {se[-200:]}')
    srv.flip_etag_after = 0

    code, so, se = extract(['--maxzoom', '13', '--max-download-mb', '0'], url, os.path.join(tmp, 'big.pmtiles'))
    check(code == 1 and 'max-download-mb' in se, f'an oversized plan is refused: {se[-200:]}')

    code, so, se = extract(['--bbox', '10,20,5,30'], url, os.path.join(tmp, 'bad.pmtiles'))
    check(code == 1 and 'not a valid' in se, 'a bad bbox is refused')

    code, so, se = extract([], 'ftp://example.com/x.pmtiles', os.path.join(tmp, 'bad.pmtiles'))
    check(code == 1 and 'http(s)' in se, 'a non-http URL is refused')

    # flaky: the 4th and 5th requests fail with 503, then it works
    srv.log.clear(); srv.fail_skip, srv.fail_first_requests = 3, 5
    quick = lambda u, log: X.RangeClient(u, backoff=0.0, log=log)
    out5 = os.path.join(tmp, 'flaky.pmtiles')
    code, so, se = extract(['--maxzoom', '12'], url, out5, factory=quick)
    check(code == 0 and 'retry' in so and os.path.exists(out5), f'transient 503s are retried: {se or so[-200:]}')
    srv.fail_skip = srv.fail_first_requests = 0

    # a connection that dies halfway through a body, every time: give up loudly
    srv.truncate = True
    code, so, se = extract(['--maxzoom', '13'], url, os.path.join(tmp, 'trunc.pmtiles'), factory=lambda u, log: X.RangeClient(u, retries=2, backoff=0.0, log=log))
    check(code == 1 and 'giving up' in se and not os.path.exists(os.path.join(tmp, 'trunc.pmtiles')), f'truncated bodies are retried then refused: {se[-200:]}')
    srv.truncate = False

    # a covering tile missing from the source (z5 over the island)
    z5 = [t for t in X.tiles_for_bbox(BBOX, 5)][0]
    src2 = os.path.join(tmp, 'holey.pmtiles')
    write_source(src2, universe(missing={z5}))
    srv.files['/holey.pmtiles'] = src2
    holey = f'http://127.0.0.1:{srv.server_address[1]}/holey.pmtiles'
    code, so, se = extract(['--maxzoom', '12'], holey, os.path.join(tmp, 'holey-out.pmtiles'))
    check(code == 1 and 'low-zoom' in se and str(z5) in se, f'a missing covering tile is refused: {se[-200:]}')
    code, so, se = extract(['--maxzoom', '12', '--allow-missing'], holey, os.path.join(tmp, 'holey-out.pmtiles'))
    check(code == 0, f'--allow-missing lets it through: {se}')

    # a tile whose bytes are not gzip
    src3 = os.path.join(tmp, 'corrupt.pmtiles')
    write_source(src3, universe(), corrupt=X.tiles_for_bbox(BBOX, 12)[3])
    srv.files['/corrupt.pmtiles'] = src3
    code, so, se = extract(['--maxzoom', '12'], f'http://127.0.0.1:{srv.server_address[1]}/corrupt.pmtiles', os.path.join(tmp, 'corrupt-out.pmtiles'))
    check(code == 1 and 'not valid gzip' in se, f'a corrupt tile is refused: {se[-200:]}')

    # not a PMTiles file at all
    junk = os.path.join(tmp, 'junk.pmtiles')
    open(junk, 'wb').write(b'<html>hello</html>' * 20)
    srv.files['/junk.pmtiles'] = junk
    code, so, se = extract([], f'http://127.0.0.1:{srv.server_address[1]}/junk.pmtiles', os.path.join(tmp, 'junk-out.pmtiles'))
    check(code == 1 and 'not a PMTiles' in se, f'a non-archive is refused: {se[-200:]}')

    # a tiny archive (smaller than the 16 KiB first read) works
    small = os.path.join(tmp, 'small.pmtiles')
    small_tiles = [t for t in universe() if t[0] <= 3]
    blobs_small = {zxy_to_tileid(*t): payload(*t) for t in small_tiles}
    from pmtiles.writer import write
    with write(small) as w:
        for tid in sorted(blobs_small):
            w.write_tile(tid, blobs_small[tid])
        w.finalize({'tile_compression': Compression.GZIP, 'tile_type': TileType.MVT}, {'name': 'tiny'})
    srv.files['/small.pmtiles'] = small
    code, so, se = extract(['--maxzoom', '3'], f'http://127.0.0.1:{srv.server_address[1]}/small.pmtiles', os.path.join(tmp, 'small-out.pmtiles'))
    check(code == 0, f'an archive smaller than the first 16 KiB read works: {se}')

    # ---- the fixture generator reproduces what is committed (compared tile by tile after decoding, so a different zlib cannot fail it)
    fx = os.path.join(tmp, 'fixture.pmtiles')
    r = subprocess.run([sys.executable, '-B', os.path.join(TOOLS, 'make_fixture_pmtiles.py'), '--out', fx], capture_output=True, text=True)
    check(r.returncode == 0, f'make_fixture_pmtiles: exit {r.returncode}: {r.stderr[-300:]}')
    committed = os.path.join(ROOT, 'map', 'vashon.pmtiles')
    if r.returncode == 0 and os.path.exists(committed):
        fx_tiles, fx_h, fx_meta = archive_tiles(fx)
        cm_tiles, cm_h, cm_meta = archive_tiles(committed)
        if cm_meta.get('eberry', {}).get('placeholder') is True:
            dec = lambda tiles: {k: mapbox_vector_tile.decode(gzip.decompress(v)) for k, v in tiles.items()}
            keys = ('min_zoom', 'max_zoom', 'min_lon_e7', 'min_lat_e7', 'max_lon_e7', 'max_lat_e7', 'tile_type', 'tile_compression', 'clustered')
            check(set(fx_tiles) == set(cm_tiles) and dec(fx_tiles) == dec(cm_tiles) and fx_meta == cm_meta and all(fx_h[k] == cm_h[k] for k in keys),
                  'map/vashon.pmtiles is the placeholder, but it differs from what tools/make_fixture_pmtiles.py writes now; re-run the generator')
        else:
            with open(committed, 'rb') as f:
                check(f.read(8) == b'PMTiles\x03', 'map/vashon.pmtiles is a real extract with valid magic bytes')

    srv.shutdown()
    if failures:
        print(f'FAIL: {len(failures)} failure(s), {passed} checks passed')
        for f in failures:
            print('  -', f)
        sys.exit(1)
    print(f'OK: pmtiles tools: {passed} checks passed (extract: tile set, bytes, header, ranges, refusals, retries; fixture reproducibility)')


if __name__ == '__main__':
    main()
