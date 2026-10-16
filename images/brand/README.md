# images/brand

The brand marks the site shows. Two different kinds of file live here.

## E. Berry marks (`*.svg`)

`wordmark-*.svg`, `monogram-*.svg` and `lockup-friend-to-vashon.svg` are copied verbatim from the `ebberry/style-guide` repo (`reference/logos/`). If one needs to change, change it there and copy it over again. Never re-typeset the wordmark.

## Windermere Real Estate, Vashon Island (`windermere-vashon-island.png`)

The co-brand logo for E. Berry Property Management's affiliation with Windermere Vashon. It is **Windermere's trademark, supplied by the owner**, and it is shown **unmodified**:

- **Never recolor, restyle, redraw, stretch, outline or crop parts of it.** It is navy and black ink (plus a grey diamond) by design. Set its width and let the height follow.
- Because the ink is dark navy and black, it **only ever sits on Cream** (`#F1ECE9`): straight on a Cream field, or on a flat Cream panel (24px radius, no border) when the surrounding field is Berry, as in the footer. Never on Berry, never on a photo.
- Alt text, everywhere: `Windermere Real Estate, Vashon Island` (it says exactly what the logo says).
- It is always a link to the office's own website, `https://www.windermerevashon.com/`: a plain `<a>` (no `target`, no `rel`, no underline, no hover effect), named by the alt text alone. Its keyboard focus ring is Berry, even on the footer's Cream panel.
- It is a co-brand, not a replacement for the legal identification. The text lines ("A PART OF WINDERMERE VASHON" in the header, "E. Berry Property Management — A Part of Windermere Vashon" in the footer, the owners page block) stay as the firm-ID wording; the logo only makes the affiliation unmistakable. There is no logo in the header on purpose: at header height the "Vashon Island" lettering would be about 6px.

Where it appears, and how big: the footer of every page (on its own 128px Cream panel with 12px padding, so the logo is 104px), the lockup card in the owners page's "A part of Windermere Vashon" block (144px, beside the E. Berry wordmark, with a thin Berry divider), and the homepage's "part of Windermere Vashon" line (112px, on the Cream field). It stays modest: the E. Berry marks are the larger ones. `tools/check_site.py` and `tools/test_listings.py` hold those placements, sizes and links, and keep it out of the header.

### How the file was made

Source: a 900x600 JPEG on a white background, provided by the owner (`1.jpg`; the logo's content box is about 697x397 px). The PNG is the same pixels with only the white background removed, at the source's full resolution, cropped to the content box plus 2% padding (725x430):

1. The three solid inks were measured from eroded interior pixels: black `rgb(0, 0, 0)`, navy `rgb(1, 26, 68)` and grey `rgb(104, 105, 107)`.
2. Each pixel belongs to exactly one ink (the inks never overlap; they only anti-alias against the white page). The wordmark band is black, the lines under it are navy, and the diamond mark is navy or grey, decided by hue on solid pixels and carried outward to the edge pixels beside them.
3. `alpha = clamp((255 - L_pixel) / (255 - L_ink))` (L = Rec. 709 luminance) and the RGB is that ink's exact color. Nearly white pixels (alpha < 3%, JPEG ringing) become fully transparent, and pixels whose whole 3x3 neighbourhood is solid ink become fully opaque, so solid interiors are exactly alpha 255 in the exact ink color. Edges keep their real anti-aliased coverage, so there is no white halo on Cream.

A plain threshold leaves white halos, and a plain color-to-alpha turns the solid grey diamond translucent; this does neither. Checked: composited back on white, the PNG matches the JPEG to a mean absolute error of 0.43 per channel over the whole crop (2.6 / 1.6 / 2.5 on R / G / B over just the logo pixels; the rest is JPEG chroma noise that cannot be reproduced), and it is clean on Cream and on Berry.

If Windermere ever sends a vector (SVG) or a higher-resolution logo, replace this file with it, keeping the name and the alt text.
