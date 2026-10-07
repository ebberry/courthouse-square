# Images

Everything the site shows lives under here. Most of it is already in place; the one thing only you can add is **photos**.

## What is where

| Path | What it is | Touch it? |
| --- | --- | --- |
| `brand/` | The E. Berry logos: wordmark (Berry, Cream, Tangerine), the monogram (bare and badge) and the "A Friend to Vashon" lockup. Copied verbatim from the `ebberry/style-guide` repo (`reference/logos/`). | **No.** If a logo needs to change, change it in the style-guide repo and copy it over again. |
| `buildings/<building-id>/` | Photos for a building page. Courthouse Square is `buildings/courthouse-square/` (the id in `data/buildings.json`). | Yes: add `gallery-1.jpg` … `gallery-6.jpg` (see below). |
| `listings/<slug>/` | Photos for one listing. `<slug>` is the listing's `id` in `data/listings.json` (e.g. `chs-n101`). | Yes: add `photo-1.jpg`, `photo-2.jpg`, … (see below). |
| `og-card-eberry.png` | The social-share card for the E. Berry site (1200×630, under 300 KB, checked by `tools/check_site.py`). It is the share image for the homepage, `/listings/`, and for any building or listing page that has no photo yet. | Only to redesign the card; keep the size. |
| `og-card.png`, `favicon.svg`, `logo.svg` | The old Courthouse Square art, still used by the lease pages (`/lease/`). | No. |
| `tenants/` | Tenant logos; see `tenants/README.md`. | When tenants send theirs. |

## Building photos: `buildings/courthouse-square/gallery-1.jpg` … `gallery-6.jpg`

The building page shows a six-tile gallery, "A look around". The tiles come from the `gallery` list in `data/buildings.json`; each one is **1200×900 (4:3)**. Suggested order, which is also the order they appear:

| File | Subject |
| --- | --- |
| `gallery-1.jpg` | The building from outside |
| `gallery-2.jpg` | The patio |
| `gallery-3.jpg` | A typical suite |
| `gallery-4.jpg` | A common area or reception |
| `gallery-5.jpg` | The parking lot |
| `gallery-6.jpg` | The entrance |

A building page's `og:image` (the picture that shows when someone shares the link) is the first gallery photo whose file exists **when you run the generator** (normally `gallery-1.jpg`). So after you drop photos in, run `python3 tools/build_pages.py` and commit the result. A second building follows the same pattern under `buildings/<its-id>/`; list its photos in its `gallery` in `data/buildings.json`.

## Listing photos: `listings/<slug>/photo-1.jpg`, `photo-2.jpg`, …

1. Put the files in `images/listings/<listing-id>/`, named `photo-1.jpg`, `photo-2.jpg` and so on, **1600×1200 (4:3)**.
2. List them, in order, in that listing's `photos` array in `data/listings.json`, e.g. `"photos": ["/images/listings/chs-n101/photo-1.jpg", "/images/listings/chs-n101/photo-2.jpg"]`. `tools/check_site.py` fails if a listed file isn't in the repo.
3. Bump `updated` in `data/listings.json`, run `python3 tools/build_pages.py`, and commit.

Photo 1 is the lead: it is the listing's `og:image` and the first thing on the page. With an odd number of photos it is shown wide (cropped to 16:9 on bigger screens), so keep the subject near the middle of the frame.

## When a photo is missing

On purpose, nothing breaks. A gallery tile with no file shows the flat Berry monogram placeholder ("photos soon"); a listing with an empty `photos` list shows one Berry band that says photos are coming; a card on `/listings/` or the homepage does the same. A page with no photo shares the E. Berry card instead. So you can launch with none and add them one at a time.

## Making good photos for the site

- **Format:** JPEG, 200 to 400 KB each. Resize before you commit (1200×900 for the gallery, 1600×1200 for a listing).
- **Light:** natural daylight, no heavy filters. Straight, true-to-life pictures of real places (the brand guide asks for exactly this); no stock photos.
- **People:** none, please, unless they've signed a release. Keep license plates out of the parking shots.
- **Alt text:** the generator writes it for you ("Courthouse Square, photo 3"; "Suite N101 — Courthouse Square, photo 1"). The monogram seal and the "photos soon" placeholders are decorative and hidden from screen readers.

## Your shot list

**Courthouse Square** (one visit on a bright morning covers it):

1. The building from outside, from across Vashon Hwy SW, whole building in frame.
2. The patio, with the chairs out.
3. One typical suite, empty and clean, shot from the doorway toward the window.
4. A common area or the reception spot.
5. The parking lot, to show there's plenty of room.
6. The entrance, close enough to see the door and the signage.

**Each residential unit, as they come** (6 to 8 photos, same light rules):

1. The outside, from the street or the driveway.
2. The main living space, from the corner that shows the most.
3. The kitchen.
4. Every bedroom (one photo each).
5. The bathroom(s).
6. Any yard, deck, garden or view, and the laundry or storage if there is some.

Name each photo `photo-1.jpg`, `photo-2.jpg` … in the order you'd walk through the place.
