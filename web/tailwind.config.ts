import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0B1620",
          soft:    "#0E1E2A",
        },
        panel: {
          DEFAULT: "#122431",
          border:  "#1E3A44",
        },
        ink: {
          DEFAULT: "#E6EEF0",
          muted:   "#8FA6AE",
          faint:   "#5F7A83",
        },
        brand: {
          teal:    "#14B8A6",
          deep:    "#0E7C6B",
          glow:    "#22D3B7",
        },
        state: {
          answer:  "#22C55E",
          warn:    "#F59E0B",
          clarify: "#38BDF8",
          abstain: "#F43F5E",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: {
        "2xl": "1rem",
      },
      boxShadow: {
        panel: "0 4px 30px -12px rgba(0,0,0,0.5)",
        glow:  "0 0 40px -8px rgba(20,184,166,0.35)",
      },
      keyframes: {
        pulseDot: {
          "0%,100%": { boxShadow: "0 0 0 0 rgba(34,197,94,0.65)" },
          "50%":     { boxShadow: "0 0 0 8px rgba(34,197,94,0)" },
        },
        fadeUp: {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        pulseDot: "pulseDot 2s ease-in-out infinite",
        fadeUp:   "fadeUp .35s ease-out both",
      },
    },
  },
  plugins: [],
};
export default config;
