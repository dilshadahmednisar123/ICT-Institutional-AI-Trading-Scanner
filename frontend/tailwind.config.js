/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        institutional: {
          bg: "#07111f",
          panel: "#0c1726",
          border: "#1c3348",
          accent: "#22d3ee",
          green: "#10b981",
          red: "#ef4444",
          muted: "#8da5b9",
        },
      },
    },
  },
  plugins: [],
};
