// Single source of truth for the Tailwind theme, shared by both pages.
// (Previously duplicated as inline Play-CDN config blocks in index.html and
// lease/index.html, which could drift.)
//
// The committed stylesheet css/tailwind.css is generated from this config —
// see "Rebuilding the stylesheet" in README.md. Rebuild whenever you add a
// Tailwind class that isn't already used somewhere in the two HTML files.
module.exports = {
  content: ['./index.html', './lease/index.html'],
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
        }
      },
      fontFamily: {
        sans:  ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['Fraunces', 'ui-serif', 'Georgia', 'serif']
      }
    }
  }
};
