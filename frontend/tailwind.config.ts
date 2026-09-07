import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f7f7f8", 100: "#eeeef0", 200: "#d9d9de", 300: "#b8b8c1",
          400: "#90909e", 500: "#727283", 600: "#5c5c6b", 700: "#4b4b57",
          800: "#40404a", 900: "#38383f", 950: "#18181b",
        },
        accent: {
          50: "#ecfdf5", 100: "#d1fae5", 400: "#34d399", 500: "#10b981",
          600: "#059669", 700: "#047857",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 4px 16px -4px rgba(16,24,40,.08)",
      },
    },
  },
  plugins: [],
};
export default config;
