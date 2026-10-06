import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#070a12",
          900: "#0b1020",
          850: "#0f1526",
          800: "#141b2f",
          700: "#1d2540",
          600: "#2a3352",
          500: "#3b4667",
        },
        edge: "#1c2440",
        mute: "#8894b8",
        text: "#e8ecf8",
        brand: {
          DEFAULT: "#4f7cff",
          soft: "#8aa8ff",
          deep: "#2d55d4",
        },
        gain: "#22c98a",
        loss: "#ff5d6c",
        warn: "#ffb020",
        alert: "#ff8a3d",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 18px 40px -24px rgba(0,0,0,0.9)",
        glow: "0 0 0 1px rgba(79,124,255,0.35), 0 12px 40px -16px rgba(79,124,255,0.55)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 220ms ease-out both",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
