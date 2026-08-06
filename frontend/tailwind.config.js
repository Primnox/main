/** @type {import('tailwindcss').Config} */

/* Every themed colour is a CSS custom property whose value is a full colour
   (often built with color-mix in themes.css), not an "R G B" channel triplet.
   Tailwind can only inject an alpha modifier into the triplet form, so a plain
   `var(--color-x)` string silently loses `/opacity`:

     text-on-surface/30  ->  rendered fully opaque
     bg-on-surface/5     ->  rendered fully transparent
     border-on-surface/10 -> fell back to Tailwind's default grey

   Declaring each colour as a function lets us mix the alpha in ourselves.
   `opacityValue` arrives either as a literal (`0.3`, from `/30`) or as a
   `var(--tw-*-opacity)` reference (when no modifier is present), and calc()
   handles both. */
const themed = (name) => ({ opacityValue }) =>
  opacityValue === undefined
    ? `var(${name})`
    : `color-mix(in srgb, var(${name}) calc(${opacityValue} * 100%), transparent)`;

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: themed('--color-surface'),
        'surface-dim': themed('--color-surface-dim'),
        'surface-bright': themed('--color-surface-bright'),
        'surface-container-lowest': themed('--color-surface-container-lowest'),
        'surface-container-low': themed('--color-surface-container-low'),
        'surface-container': themed('--color-surface-container'),
        'surface-container-high': themed('--color-surface-container-high'),
        'surface-container-highest': themed('--color-surface-container-highest'),
        'on-surface': themed('--color-on-surface'),
        'on-surface-variant': themed('--color-on-surface-variant'),
        'inverse-surface': themed('--color-inverse-surface'),
        'inverse-on-surface': themed('--color-inverse-on-surface'),
        outline: themed('--color-outline'),
        'outline-variant': themed('--color-outline-variant'),
        'surface-tint': themed('--color-surface-tint'),
        primary: themed('--color-primary'),
        'on-primary': themed('--color-on-primary'),
        'primary-container': themed('--color-primary-container'),
        'on-primary-container': themed('--color-on-primary-container'),
        'inverse-primary': themed('--color-inverse-primary'),
        secondary: themed('--color-secondary'),
        'on-secondary': themed('--color-on-secondary'),
        'secondary-container': themed('--color-secondary-container'),
        'on-secondary-container': themed('--color-on-secondary-container'),
        tertiary: themed('--color-tertiary'),
        'on-tertiary': themed('--color-on-tertiary'),
        'tertiary-container': themed('--color-tertiary-container'),
        'on-tertiary-container': themed('--color-on-tertiary-container'),
        /* Semantic accents, so views stop reaching for literal emerald/amber. */
        success: themed('--color-success'),
        warn: themed('--color-warn'),
        error: themed('--color-error'),
        'on-error': themed('--color-on-error'),
        'error-container': themed('--color-error-container'),
        'on-error-container': themed('--color-on-error-container'),
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
        display: 'var(--font-display)',
      },
    },
  },
  plugins: [],
}
