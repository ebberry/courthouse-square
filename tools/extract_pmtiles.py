#!/usr/bin/env python3
"""Cut Vashon-Maury Island out of a remote Protomaps basemap archive into map/vashon.pmtiles.

  python3 tools/extract_pmtiles.py --url https://build.protomaps.com/20261001.pmtiles \\
      --bbox -122.62,47.28,-122.30,47.57 --maxzoom 15 --out map/vashon.pmtiles

What it does (HTTP Range requests only; the planet file is ~100+ GB and is never downloaded):

  1. reads the remote header + root directory (the first 16 KiB), then only the leaf directories that can hold a
     wanted tile
  2. wants every tile at z<minzoom>..z<maxzoom> that intersects the bbox. That includes the few low-zoom tiles
     (z0..z10) that merely COVER the bbox, so the map renders when zoomed out, and everything z11..z15 inside it
  3. downloads the tile bytes with coalesced range requests (nearby tiles share one request), checking status,
     Content-Range, length and that the archive does not change under it (ETag / Last-Modified); transient errors
     are retried
  4. writes a clustered PMTiles v3 archive (tiles in Hilbert order, identical tiles stored once) through the
     `pmtiles` Python writer, with the source's tile type and compression, the bbox as its bounds, and the source
     metadata plus {"eberry": {"placeholder": false, ...}}
  5. re-opens the output and proves it: magic bytes, header, a gunzip of every tile, and every tile byte-identical to
     what was downloaded. Nothing is moved into place until that passes.

It refuses to run on a mistake: a missing low-zoom parent tile, an absurd download size (--max-download-mb), a server
that ignores Range, or an archive that changes mid-run all stop it with a message instead of a quiet bad file.

Other modes:
  --dry-run             plan only: read the directories, print how many tiles and bytes it WOULD fetch, write nothing
  --inspect FILE        describe a local archive: header, tiles per zoom, and (if mapbox-vector-tile is installed) the
                        layers and `kind` values in a sample tile. Use it on the real extract to check that
                        map/style.json filters match the data.

Needs:  pip install pmtiles                  (stdlib otherwise)
        pip install mapbox-vector-tile       (optional, for --inspect)
"""

import argparse
import bisect
import gzip
import hashlib
import http.client
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request

try:
    from pmtiles.reader import MmapSource, Reader
    from pmtiles.tile import (Compression, Entry, MagicNumberNotFound, SpecVersionUnsupported, TileType,
                              deserialize_header, read_varint, tileid_to_zxy, zxy_to_tileid)
    from pmtiles.writer import write
except ImportError as e:               # pragma: no cover
    sys.exit(f'extract_pmtiles: {e}. Install the library with:  pip install pmtiles')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BBOX = '-122.62,47.28,-122.30,47.57'          # west,south,east,north: Vashon + Maury Island, the map's pan limit
DEFAULT_OUT = os.path.join(ROOT, 'map', 'vashon.pmtiles')
FIRST_READ = 16384                                     # header (127 B) + root directory always sit in the first 16 KiB
PARENT_ZOOM = 10                                       # tiles up to this zoom must exist: they are the ones that cover the bbox
MAX_LAT = 85.0511287798066
USER_AGENT = 'eberry-extract-pmtiles/1.0 (+https://eberryvashon.com)'


class ExtractError(Exception):
    """Anything that means 'do not trust this run'."""


# ---------------------------------------------------------------- tile math
def lat_to_tile_y(lat, z):
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    return (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * (1 << z)


def lng_to_tile_x(lng, z):
    return (lng + 180.0) / 360.0 * (1 << z)


def tiles_for_bbox(bbox, z):
    """Every (z, x, y) whose tile touches the bbox. A tile that only shares an edge is included: wanting one tile too
    many is harmless, wanting one too few leaves a hole in the map."""
    west, south, east, north = bbox
    n = 1 << z
    x0 = max(0, min(n - 1, math.floor(lng_to_tile_x(west, z))))
    x1 = max(0, min(n - 1, math.floor(lng_to_tile_x(east, z))))
    y0 = max(0, min(n - 1, math.floor(lat_to_tile_y(north, z))))       # tile y grows southward
    y1 = max(0, min(n - 1, math.floor(lat_to_tile_y(south, z))))
    return [(z, x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def parse_bbox(text):
    try:
        west, south, east, north = [float(v) for v in text.split(',')]
    except ValueError:
        raise ExtractError(f'--bbox must be west,south,east,north in degrees (got {text!r})')
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ExtractError(f'--bbox {text!r} is not a valid west,south,east,north box')
    return west, south, east, north


# ---------------------------------------------------------------- HTTP Range client
class RangeClient:
    """Reads byte ranges of one URL, and refuses anything that looks wrong."""

    def __init__(self, url, retries=5, timeout=60, backoff=1.0, log=print):
        if not re.match(r'^https?://', url):
            raise ExtractError(f'--url must be http(s) (got {url!r})')
        self.url, self.retries, self.timeout, self.backoff, self.log = url, retries, timeout, backoff, log
        self.total = None            # archive size, from the first Content-Range
        self.identity = None         # (ETag, Last-Modified) of the first response
        self.requests = 0
        self.bytes_read = 0

    def _once(self, offset, length):
        end = offset + length - 1
        req = urllib.request.Request(self.url, headers={'Range': f'bytes={offset}-{end}', 'User-Agent': USER_AGENT,
                                                        'Accept-Encoding': 'identity'})
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code == 416 and offset == 0:
                # the whole archive is smaller than the first read: ask for exactly what exists
                m = re.match(r'bytes \*/(\d+)$', e.headers.get('Content-Range', ''))
                e.close()
                if not m or int(m.group(1)) < 1:
                    raise ExtractError('server answered 416 without a usable Content-Range')
                return self._once(0, int(m.group(1)))
            raise
        with resp:
            status = resp.status
            headers = resp.headers
            if status == 200:
                # The server ignored Range and is about to send the whole file. Only acceptable if that IS the range.
                clen = headers.get('Content-Length')
                if offset != 0 or clen is None or int(clen) > length:
                    raise ExtractError(f'{self.url}: the server answered 200 to a Range request, so it does not support '
                                       'byte ranges (pmtiles needs them); refusing to download the whole archive')
                body = resp.read()
                start, total = 0, len(body)
            elif status == 206:
                m = re.match(r'bytes (\d+)-(\d+)/(\d+|\*)$', headers.get('Content-Range', ''))
                if not m:
                    raise ExtractError(f'{self.url}: 206 response with a missing or odd Content-Range '
                                       f'{headers.get("Content-Range")!r}')
                start, last = int(m.group(1)), int(m.group(2))
                total = int(m.group(3)) if m.group(3) != '*' else None
                if start != offset:
                    raise ExtractError(f'asked for bytes from {offset}, the server sent bytes from {start}')
                body = resp.read()
                if len(body) != last - start + 1:
                    raise urllib.error.ContentTooShortError(f'short read: {len(body)} of {last - start + 1} bytes', None)
            else:
                raise ExtractError(f'{self.url}: unexpected HTTP status {status}')
            ident = (headers.get('ETag'), headers.get('Last-Modified'))
        if total is not None:
            if self.total is None:
                self.total = total
            elif total != self.total:
                raise ExtractError(f'the archive changed size mid-run ({self.total} -> {total} bytes); start again')
        if self.identity is None:
            self.identity = ident
        else:
            for old, new, what in zip(self.identity, ident, ('ETag', 'Last-Modified')):
                if old and new and old != new:
                    raise ExtractError(f'the archive changed mid-run ({what} {old!r} -> {new!r}); start again')
        if len(body) != length and not (self.total is not None and offset + len(body) == self.total):
            raise ExtractError(f'asked for {length} bytes at {offset}, got {len(body)} (not at the end of the file)')
        return body

    def get(self, offset, length):
        if length <= 0:
            return b''
        delay = self.backoff
        for attempt in range(1, self.retries + 1):
            try:
                body = self._once(offset, length)
                self.requests += 1
                self.bytes_read += len(body)
                return body
            except ExtractError:
                raise
            except urllib.error.HTTPError as e:
                if e.code < 500 and e.code != 429:
                    raise ExtractError(f'{self.url}: HTTP {e.code} {e.reason} for bytes {offset}-{offset + length - 1}')
                err = f'HTTP {e.code}'
            except (urllib.error.URLError, http.client.HTTPException, OSError) as e:      # OSError covers resets and timeouts
                err = repr(e)
            if attempt == self.retries:
                raise ExtractError(f'{self.url}: giving up on bytes {offset}-{offset + length - 1} after {attempt} tries ({err})')
            self.log(f'  retry {attempt}/{self.retries - 1} after {err}')
            time.sleep(delay)
            delay *= 2


# ---------------------------------------------------------------- archive structure
def decompress(data, compression, what):
    if compression == Compression.NONE:
        return data
    if compression == Compression.GZIP:
        try:
            return gzip.decompress(data)
        except (OSError, EOFError) as e:
            raise ExtractError(f'{what}: not valid gzip ({e})')
    raise ExtractError(f'{what}: {compression.name} compression is not supported by this script (the Protomaps builds use gzip)')


def parse_directory(raw):
    """A decompressed PMTiles v3 directory -> [Entry] (the same algorithm as pmtiles.tile.deserialize_directory)."""
    b = io.BytesIO(raw)
    n = read_varint(b)
    entries, last = [], 0
    for _ in range(n):
        last += read_varint(b)
        entries.append(Entry(last, 0, 0, 0))
    for e in entries:
        e.run_length = read_varint(b)
    for e in entries:
        e.length = read_varint(b)
    for i, e in enumerate(entries):
        v = read_varint(b)
        e.offset = entries[i - 1].offset + entries[i - 1].length if (i > 0 and v == 0) else v - 1
    return entries


def read_directory(client, header, offset, length, what):
    raw = decompress(client.get(offset, length), header['internal_compression'], what)
    return parse_directory(raw)


def locate(client, header, entries, wanted, found, depth=0, max_len=1 << 26):
    """Resolve the sorted tile ids in `wanted` against one directory, descending into leaf directories only where a
    wanted id falls inside their range. Fills found[tile_id] = (offset, length) for every wanted id that exists
    (offset is absolute: the tile-data section start is already added)."""
    if depth > 3:
        raise ExtractError('directory nesting deeper than the spec allows')
    ids = [e.tile_id for e in entries]
    by_leaf = {}
    for w in wanted:
        i = bisect.bisect_right(ids, w) - 1
        if i < 0:
            continue
        e = entries[i]
        if e.run_length == 0:                                   # a pointer to a leaf directory covering [e.tile_id, next.tile_id)
            by_leaf.setdefault(i, []).append(w)
        elif w < e.tile_id + e.run_length:
            if e.length <= 0 or e.length > max_len:
                raise ExtractError(f'tile {tileid_to_zxy(w)} has an implausible length {e.length}')
            found[w] = (header['tile_data_offset'] + e.offset, e.length)       # absolute position in the file
    for i, sub in sorted(by_leaf.items()):
        e = entries[i]
        leaf = read_directory(client, header, header['leaf_directory_offset'] + e.offset, e.length, f'leaf directory at {e.offset}')
        locate(client, header, leaf, sub, found, depth + 1, max_len)


def open_remote(client, log):
    """Header, root directory and metadata of the remote archive."""
    first = client.get(0, FIRST_READ)
    if len(first) < 127:
        raise ExtractError('not a PMTiles archive (shorter than the 127-byte header)')
    try:
        header = deserialize_header(first[:127])
    except MagicNumberNotFound:
        raise ExtractError('not a PMTiles archive (no "PMTiles" magic bytes at the start)')
    except SpecVersionUnsupported:
        raise ExtractError('not a PMTiles v3 archive')
    except ValueError as e:
        raise ExtractError(f'unreadable PMTiles header ({e})')
    if header['tile_type'] != TileType.MVT:
        raise ExtractError(f'the archive holds {header["tile_type"].name} tiles; this script extracts vector (MVT) archives')
    if header['root_offset'] + header['root_length'] > len(first):
        root_raw = client.get(header['root_offset'], header['root_length'])
    else:
        root_raw = first[header['root_offset']:header['root_offset'] + header['root_length']]
    root = parse_directory(decompress(root_raw, header['internal_compression'], 'root directory'))
    meta_raw = b''
    if header['metadata_length']:
        meta_raw = decompress(client.get(header['metadata_offset'], header['metadata_length']), header['internal_compression'], 'metadata')
    try:
        metadata = json.loads(meta_raw) if meta_raw else {}
    except ValueError as e:
        raise ExtractError(f'metadata is not JSON ({e})')
    log(f'  source: {client.total:,} bytes, z{header["min_zoom"]}..z{header["max_zoom"]}, tiles {header["tile_type"].name}, '
        f'{header["tile_compression"].name}, {len(root)} root entries')
    return header, root, metadata


# ---------------------------------------------------------------- planning and fetching
def plan(client, header, root, bbox, minzoom, maxzoom, allow_missing, log):
    """-> ({tile_id: (z, x, y)} wanted, {tile_id: (offset, length)} found)"""
    wanted = {}
    for z in range(minzoom, maxzoom + 1):
        for t in tiles_for_bbox(bbox, z):
            wanted[zxy_to_tileid(*t)] = t
    found = {}
    locate(client, header, root, sorted(wanted), found)
    per_zoom = {}
    for tid, (z, x, y) in wanted.items():
        s = per_zoom.setdefault(z, [0, 0])
        s[0] += 1
        s[1] += tid in found
    log(f'  directories: {client.requests} requests, {client.bytes_read / 1e6:.1f} MB read')
    log('  zoom: wanted/found  ' + '  '.join(f'z{z}:{w}/{f}' for z, (w, f) in sorted(per_zoom.items())))
    missing_parents = sorted(wanted[t] for t in wanted if t not in found and wanted[t][0] <= PARENT_ZOOM)
    if missing_parents and not allow_missing:
        raise ExtractError(f'{len(missing_parents)} low-zoom tile(s) that cover the bbox are not in the source archive, e.g. '
                           f'{missing_parents[:3]}; the map would not render zoomed out. (--allow-missing overrides)')
    if not found:
        raise ExtractError('none of the wanted tiles exist in the source archive (wrong archive or bbox?)')
    return wanted, found


def coalesce(blobs, max_gap, max_request):
    """Sorted unique (offset, length) blobs -> [(start, end, [blobs])] requests. Blobs closer than max_gap share a request,
    and no request is longer than max_request (unless a single blob is)."""
    out = []
    for off, ln in sorted(blobs):
        if out and off - out[-1][1] <= max_gap and (off + ln) - out[-1][0] <= max_request:
            out[-1][1] = max(out[-1][1], off + ln)
            out[-1][2].append((off, ln))
        else:
            out.append([off, off + ln, [(off, ln)]])
    return out


def fetch_tiles(client, header, found, max_gap, max_request, log):
    """-> {(offset, length): bytes}, each checked to be valid gzip when the archive's tiles are gzip."""
    blobs = set(found.values())
    reqs = coalesce(blobs, max_gap, max_request)
    log(f'  fetching {len(blobs)} distinct tiles in {len(reqs)} range requests')
    data = {}
    for n, (start, end, group) in enumerate(reqs, 1):
        body = client.get(start, end - start)
        if len(body) != end - start:
            raise ExtractError(f'short read at {start}: wanted {end - start} bytes, got {len(body)}')
        for off, ln in group:
            blob = body[off - start:off - start + ln]
            if header['tile_compression'] == Compression.GZIP:
                try:
                    gzip.decompress(blob)
                except (OSError, EOFError) as e:
                    raise ExtractError(f'the tile at offset {off} is not valid gzip ({e}); the directory and the data disagree')
            data[(off, ln)] = blob
        if n % 25 == 0 or n == len(reqs):
            log(f'  ... {n}/{len(reqs)} requests, {client.bytes_read / 1e6:.1f} MB')
    return data


def planned_bytes(found, max_gap, max_request):
    reqs = coalesce(set(found.values()), max_gap, max_request)
    return len(reqs), sum(end - start for start, end, _ in reqs)


# ---------------------------------------------------------------- writing and proving the output
def write_archive(path, wanted, found, data, src_header, src_meta, bbox, args_info):
    west, south, east, north = bbox
    header = {
        'tile_compression': src_header['tile_compression'],
        'tile_type': src_header['tile_type'],
        'min_lon_e7': round(west * 1e7), 'min_lat_e7': round(south * 1e7),
        'max_lon_e7': round(east * 1e7), 'max_lat_e7': round(north * 1e7),
        'center_zoom': 12,
        'center_lon_e7': round((west + east) / 2 * 1e7), 'center_lat_e7': round((south + north) / 2 * 1e7),
    }
    meta = dict(src_meta)
    meta['eberry'] = {'placeholder': False, **args_info}
    with write(path) as w:
        for tid in sorted(found):                            # ascending tile id => clustered
            w.write_tile(tid, data[found[tid]])
        w.finalize(header, meta)


def verify_archive(path, wanted, found, data, bbox, minzoom, maxzoom, src_header):
    """Read the file back and compare it with what was downloaded. Raises ExtractError on the first doubt."""
    with open(path, 'rb') as f:
        if f.read(8) != b'PMTiles\x03':
            raise ExtractError('output does not start with the PMTiles v3 magic bytes')
    with open(path, 'rb') as f:
        reader = Reader(MmapSource(f))
        h = reader.header()
        if not h['clustered']:
            raise ExtractError('output is not clustered')
        if h['tile_type'] != src_header['tile_type'] or h['tile_compression'] != src_header['tile_compression']:
            raise ExtractError('output tile type/compression differs from the source')
        if h['root_offset'] + h['root_length'] > FIRST_READ:
            raise ExtractError('output root directory does not fit in the first 16 KiB (clients need that)')
        zs = sorted({wanted[t][0] for t in found})
        if (h['min_zoom'], h['max_zoom']) != (zs[0], zs[-1]):
            raise ExtractError(f'output zoom range {h["min_zoom"]}..{h["max_zoom"]} != {zs[0]}..{zs[-1]}')
        if h['addressed_tiles_count'] != len(found):
            raise ExtractError(f'output addresses {h["addressed_tiles_count"]} tiles, expected {len(found)}')
        sha = lambda b: hashlib.sha256(b).digest()
        for tid in sorted(found):
            z, x, y = tileid_to_zxy(tid)
            got = reader.get(z, x, y)
            want = data[found[tid]]
            if got is None or sha(got) != sha(want):
                raise ExtractError(f'tile {z}/{x}/{y} in the output differs from the downloaded bytes')
        # and nothing extra: walk every tile id in the output
        from pmtiles.reader import all_tiles
        n = 0
        for (z, x, y), blob in all_tiles(reader.get_bytes):
            n += 1
            if zxy_to_tileid(z, x, y) not in found:
                raise ExtractError(f'output contains an unrequested tile {z}/{x}/{y}')
        if n != len(found):
            raise ExtractError(f'output holds {n} tiles, expected {len(found)}')
    return h


# ---------------------------------------------------------------- --inspect
def inspect(path, log=print):
    with open(path, 'rb') as f:
        try:
            src = Reader(MmapSource(f))
            h = src.header()
        except (MagicNumberNotFound, SpecVersionUnsupported, ValueError) as e:
            raise ExtractError(f'{path}: not a PMTiles v3 archive ({e!r})')
        meta = src.metadata()
        from pmtiles.reader import all_tiles
        per_zoom, sample = {}, {}
        for (z, x, y), blob in all_tiles(src.get_bytes):
            per_zoom[z] = per_zoom.get(z, 0) + 1
            if z > sample.get('z', -1):
                sample = {'z': z, 'xyz': (z, x, y), 'blob': blob}
        if sample:                                           # prefer the tile under Vashon town at the highest zoom
            z = sample['z']
            x, y = math.floor(lng_to_tile_x(-122.46, z)), math.floor(lat_to_tile_y(47.4471, z))
            blob = src.get(z, x, y)
            if blob:
                sample = {'z': z, 'xyz': (z, x, y), 'blob': blob}
        log(f'{path}: {os.path.getsize(path):,} bytes')
        log(f'  header: z{h["min_zoom"]}..z{h["max_zoom"]}, {h["tile_type"].name}, tiles {h["tile_compression"].name}, '
            f'clustered={h["clustered"]}, addressed={h["addressed_tiles_count"]}, distinct={h["tile_contents_count"]}')
        log(f'  bounds: {h["min_lon_e7"] / 1e7},{h["min_lat_e7"] / 1e7},{h["max_lon_e7"] / 1e7},{h["max_lat_e7"] / 1e7}')
        log('  tiles per zoom: ' + ', '.join(f'z{z}={n}' for z, n in sorted(per_zoom.items())))
        log(f'  metadata: {meta.get("name")!r}, placeholder={meta.get("eberry", {}).get("placeholder")}')
        if not sample:
            return
        try:
            import mapbox_vector_tile
        except ImportError:
            log('  (pip install mapbox-vector-tile to see the layers and kinds inside a tile)')
            return
        blob = sample['blob']
        raw = gzip.decompress(blob) if h['tile_compression'] == Compression.GZIP else blob
        layers = mapbox_vector_tile.decode(raw)
        log(f'  sample tile {sample["xyz"]}: layers ' + ', '.join(f'{k}({len(v["features"])})' for k, v in sorted(layers.items())))
        for name in ('roads', 'landuse', 'water', 'earth', 'buildings'):
            kinds = {}
            for ft in layers.get(name, {}).get('features', []):
                k = ft['properties'].get('kind')
                kinds[k] = kinds.get(k, 0) + 1
            if kinds:
                log(f'    {name} kinds: ' + ', '.join(f'{k}={n}' for k, n in sorted(kinds.items(), key=lambda kv: str(kv[0]))))


# ---------------------------------------------------------------- driver
def build_parser():
    ap = argparse.ArgumentParser(description='Extract a bounding box from a remote Protomaps PMTiles archive using HTTP Range requests.')
    ap.add_argument('--url', help='remote archive, e.g. https://build.protomaps.com/20261001.pmtiles (daily builds are YYYYMMDD.pmtiles)')
    ap.add_argument('--bbox', default=DEFAULT_BBOX, help='west,south,east,north in degrees (use --bbox=-122.62,... if your shell objects) [%(default)s]')
    ap.add_argument('--maxzoom', type=int, default=15, help='highest zoom to keep [%(default)s]')
    ap.add_argument('--minzoom', type=int, default=0, help='lowest zoom to keep [%(default)s]')
    ap.add_argument('--out', default=DEFAULT_OUT, help='output archive [map/vashon.pmtiles]')
    ap.add_argument('--max-gap-kb', type=int, default=64, help='tiles closer together than this share one request [%(default)s]')
    ap.add_argument('--max-request-mb', type=int, default=8, help='longest single range request [%(default)s]')
    ap.add_argument('--max-download-mb', type=int, default=400, help='abort if the plan needs more than this [%(default)s]')
    ap.add_argument('--allow-missing', action='store_true', help='do not fail when a low-zoom covering tile is absent from the source')
    ap.add_argument('--dry-run', action='store_true', help='plan only: report what would be fetched, write nothing')
    ap.add_argument('--inspect', metavar='FILE', help='describe a local archive instead of extracting')
    return ap


def normalize_argv(argv):
    """argparse reads `--bbox -122.62,...` as a missing value (it starts with a minus); make it `--bbox=-122.62,...`."""
    out, i = [], 0
    while i < len(argv):
        if argv[i] == '--bbox' and i + 1 < len(argv):
            out.append('--bbox=' + argv[i + 1])
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def run(args, log=print, client_factory=RangeClient):
    if args.inspect:
        inspect(args.inspect, log)
        return 0
    if not args.url:
        raise ExtractError('--url is required (or use --inspect FILE)')
    bbox = parse_bbox(args.bbox)
    if not (0 <= args.minzoom <= args.maxzoom <= 22):
        raise ExtractError('need 0 <= --minzoom <= --maxzoom <= 22')
    client = client_factory(args.url, log=log)
    log(f'reading {args.url}')
    header, root, src_meta = open_remote(client, log)
    maxzoom = args.maxzoom
    if maxzoom > header['max_zoom']:
        log(f'  note: the source stops at z{header["max_zoom"]}; using --maxzoom {header["max_zoom"]}')
        maxzoom = header['max_zoom']
    minzoom = max(args.minzoom, header['min_zoom'])
    wanted, found = plan(client, header, root, bbox, minzoom, maxzoom, args.allow_missing, log)
    gap, req = args.max_gap_kb * 1024, args.max_request_mb * 1024 * 1024
    n_req, n_bytes = planned_bytes(found, gap, req)
    log(f'  plan: {len(found)} tiles ({len(set(found.values()))} distinct), {n_req} requests, {n_bytes / 1e6:.1f} MB to download')
    if n_bytes > args.max_download_mb * 1024 * 1024:
        raise ExtractError(f'the plan needs {n_bytes / 1e6:.0f} MB, over --max-download-mb {args.max_download_mb}; '
                           'check --bbox and --maxzoom (or raise the limit)')
    if args.dry_run:
        log('dry run: nothing written')
        return 0
    data = fetch_tiles(client, header, found, gap, req, log)
    info = {'source': args.url, 'bbox': list(bbox), 'minzoom': minzoom, 'maxzoom': maxzoom,
            'generator': 'tools/extract_pmtiles.py',
            'extracted': time.strftime('%Y-%m-%d', time.gmtime())}
    tmp = args.out + '.tmp'
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    try:
        write_archive(tmp, wanted, found, data, header, src_meta, bbox, info)
        h = verify_archive(tmp, wanted, found, data, bbox, minzoom, maxzoom, header)
        os.replace(tmp, args.out)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    log(f'wrote {args.out}: {os.path.getsize(args.out):,} bytes, {len(found)} tiles, z{h["min_zoom"]}..z{h["max_zoom"]}, '
        f'{client.requests} requests; verified byte-for-byte against the download')
    return 0


def main(argv=None):
    args = build_parser().parse_args(normalize_argv(sys.argv[1:] if argv is None else list(argv)))
    try:
        return run(args)
    except ExtractError as e:
        print(f'extract_pmtiles: FAILED: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
