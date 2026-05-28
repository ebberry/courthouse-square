# Photos

Drop your real building photos in this folder. The site references them by these exact filenames:

| File              | Where it appears                              | Recommended size           |
| ----------------- | --------------------------------------------- | -------------------------- |
| `hero.jpg`        | Large background photo on the landing page hero | 2400×1400 (landscape)      |
| `exterior.jpg`    | Reserved for future use                       | 1600×1200                  |
| `patio.jpg`       | Reserved for future use                       | 1600×1200                  |
| `suite-typical.jpg` | Reserved for future use                     | 1600×1200                  |
| `gallery-1.jpg`   | Gallery tile #1 — building exterior           | 1200×900                   |
| `gallery-2.jpg`   | Gallery tile #2 — patio                       | 1200×900                   |
| `gallery-3.jpg`   | Gallery tile #3 — typical suite interior      | 1200×900                   |
| `gallery-4.jpg`   | Gallery tile #4 — common area or reception    | 1200×900                   |
| `gallery-5.jpg`   | Gallery tile #5 — parking lot                 | 1200×900                   |
| `gallery-6.jpg`   | Gallery tile #6 — entrance                    | 1200×900                   |

## Tips

- **Format:** JPEG is fine. Compress to ~200–400 KB each; the hero can go up to ~600 KB.
- **Tone:** Natural light, no heavy filters. The site's palette is muted evergreen + warm neutral, so photos with greens, woods, and soft sunlight feel right at home.
- **People:** Optional. If you do shoot people, make sure they've signed a release.
- **Fallback:** If a file is missing, the site quietly substitutes a muted green placeholder block. Nothing breaks, but the page does look better with real photos in place.

## Adding a new gallery photo

If you want a 7th gallery tile (or more), drop the file as `gallery-7.jpg`, then open `index.html` and add a copy of one of the `<figure>` blocks in the Gallery section, bumping the filename.
