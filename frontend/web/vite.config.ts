import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The learner website. host: true lets a phone on the same Wi-Fi open it (emails link to PUBLIC_SITE_URL).
const api = process.env.API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    host: true,
    proxy: { "/api": { target: api } },
  },
  preview: { port: 5173, strictPort: true, host: true, proxy: { "/api": { target: api } } },
  build: { sourcemap: true },
});
