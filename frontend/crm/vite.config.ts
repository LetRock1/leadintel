import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The CRM dashboard. In development the API is proxied to the backend, so the browser only talks to this server.
const api = process.env.API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: { "/api": { target: api } },
  },
  preview: { port: 5174, strictPort: true, proxy: { "/api": { target: api } } },
  build: { sourcemap: true, chunkSizeWarningLimit: 900 },
});
