// Single source of truth for the Tailwind theme, shared by both pages.
// (Previously duplicated as inline Play-CDN config blocks in index.html and
// lease/index.html, which could drift.)
//
// The committed stylesheet css/tailwind.css is generated from this config —
// see "Rebuilding the stylesheet" in README.md. Rebuild whenever you add a
// Tailwind class that isn't already used somewhere in the two HTML files.
module.exports = {
  content: [
    './index.html', './lease/index.html', './lease/builder.html', './js/lease-builder.js',
    './listings/**/*.html',
    './buildings/**/*.html',
    './listing.html',
    './404.html',
    './js/listings.js',
    './js/listing-detail.js',
    './js/building.js',
    './js/eb-map.js',
    './tools/templates/*.html'
  ],
  theme: {
    extend: {
      colors: {
        evergreen: {
          50:  '#f2f6f3',
          100: '#dde8e0',
          200: '#bcd0c2',
          300: '#92b29c',
          400: '#699177',
          500: '#4b755c',
          600: '#385c47',
          700: '#2c4a39',
          800: '#243b2f',
          900: '#1e3128',
          950: '#0f1d16'
        },
        sand: {
          50:  '#faf7f2',
          100: '#f3ece0',
          200: '#e6d7bf',
          300: '#d4bb95',
          400: '#c19c6b',
          500: '#b08550'
        },
        // Warm rust accent, used for the "OPEN" ribbon and available-suite
        // highlights on the Your Neighbors card wall.
        rust: {
          400: '#d98a52',
          500: '#b4521f',
          600: '#9a4419'
        },
        // E. Berry brand palette (style guide section 4.1). Namespaced under
        // `eb` so it never collides with the lease pages' evergreen/sand/rust.
        eb: {
          berry:     '#670A2F',
          cream:     '#F1ECE9',
          tangerine: '#F36E30',
          sky:       '#8DC8E8',
          mustard:   '#E8C450',
          sage:      '#98B286',
          sand:      '#F1DDB7'
        }
      },
      borderRadius: {
        card: '24px'
      },
      fontFamily: {
        sans:  ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['Fraunces', 'ui-serif', 'Georgia', 'serif']
      }
    }
  }
};
