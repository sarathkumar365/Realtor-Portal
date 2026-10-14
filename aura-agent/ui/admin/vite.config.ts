import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    // The API on the page's own origin: jsdom's XMLHttpRequest enforces CORS, and
    // CORS is the api's to test, not this app's.
    environmentOptions: { jsdom: { url: "http://aura.test/" } },
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    env: { VITE_AURA_BASE: "http://aura.test" },
  },
});
