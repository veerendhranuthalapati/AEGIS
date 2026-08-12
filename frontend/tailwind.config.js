/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        soc: {
          bg: "#0b0f14",
          panel: "#111820",
          border: "#1e2936",
          accent: "#3b82f6",
          critical: "#ef4444",
          high: "#f97316",
          medium: "#eab308",
          low: "#22c55e",
          muted: "#64748b",
        },
      },
    },
  },
  plugins: [],
};
