import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#1B2A4A",
        blue: "#2E5EAA",
        teal: "#1F8A70",
        red: "#8B1E3F",
        gold: "#C99A2E",
      },
    },
  },
  plugins: [],
} satisfies Config;
