# PMTiles (JavaScript) 4.4.1

Vendored from the npm package `pmtiles@4.4.1` (https://github.com/protomaps/PMTiles, https://docs.protomaps.com/pmtiles/).
Author per its `package.json`: Brandon Liu (Protomaps). License: BSD-3-Clause.
Copied unmodified:

- `dist/pmtiles.js` -> `js/vendor/pmtiles.js` (the IIFE build; it exposes the `pmtiles` global with `PMTiles` and `Protocol`)

`js/eb-map.js` registers `new pmtiles.Protocol()` with MapLibre as the `pmtiles://` scheme, which is how
`map/style.json` reads `map/vashon.pmtiles` with HTTP Range requests.

The npm tarball ships no LICENSE file; its `package.json` names the license as BSD-3-Clause. The standard text of that
license follows.

## BSD 3-Clause License

Copyright (c) the PMTiles authors (Brandon Liu / Protomaps)

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
