# Tenant logos

Drop logo files here. The site references them from `data/tenants.json` via the optional `logo` field, e.g.:

```json
{ "name": "Smith Family Dental", "logo": "/images/tenants/smith-family-dental.png" }
```

## Tips

- **Format:** SVG is best (sharp at every size, tiny file). PNG with a transparent background is the next-best option. Avoid JPEGs — they have white edges around logos.
- **Aspect ratio:** Anything reasonable works. The site sizes logos to about **48 px tall** and lets the width be whatever the logo's natural ratio dictates.
- **Recommended dimensions:** roughly **200–400 px wide × 80–120 px tall**, exported at 2× for crisp display on retina screens.
- **File names:** lowercase, hyphenated, descriptive — `smith-family-dental.svg`, `vashon-tax-and-accounting.png`. Spaces in filenames work but tend to cause headaches.
- **Tenants without a logo:** just omit the `logo` field in `tenants.json`. The card falls back to a text-only layout. No broken-image icons.
- **Missing files:** if the file at the listed path doesn't exist, the card hides the image and renders the rest of the content normally — but it's worth fixing the path or removing the field when you notice.

## Permission

Logos belong to their respective tenants. Make sure each tenant has agreed to have their logo on the building's site — most are happy to (free marketing), but it's worth confirming once.
