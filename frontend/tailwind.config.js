/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12211E",
        paper: "#F4F6F1",
        ledger: "#1F3B33",
        ledgerLight: "#2E5449",
        signal: "#C7622B",
        wheat: "#D9C79E",
        line: "#DDE3D6",
        critical: "#B3261E",
        major: "#C7622B",
        minor: "#B79A2E",
        matched: "#3D6B57",
      },
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        body: ["Inter", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
