// Tailwind CSS v4 uses @tailwindcss/postcss instead of the tailwindcss plugin.
// autoprefixer is no longer required — v4 handles vendor prefixes natively.
const config = {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};

export default config;
