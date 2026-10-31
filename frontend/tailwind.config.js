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
          bg: "#0b0f14",
          panel: "#12181f",
          border: "#1e2a36",
          accent: "#3b82f6",
          green: "#22c55e",
          red: "#ef4444",
          muted: "#94a3b8",
        },
      },
    },
  },
  plugins: [],
};
