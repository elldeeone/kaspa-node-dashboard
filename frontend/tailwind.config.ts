import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "kaspa-teal": "#0d9488",
        "kaspa-zinc": {
          800: "#27272a",
          900: "#18181b",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
