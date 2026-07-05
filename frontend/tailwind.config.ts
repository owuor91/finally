import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d1117",
        panel: "#161b22",
        "panel-alt": "#1a1a2e",
        border: "#30363d",
        accent: "#ecad0a",
        blue: "#209dd7",
        purple: "#753991",
        up: "#26a69a",
        down: "#ef5350",
      },
    },
  },
  plugins: [],
};

export default config;
