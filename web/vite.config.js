import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend (src/serve.py) owns the API + data; this only builds/serves the SPA.
// In dev, requests to /api/* are proxied to the Python server so the same
// fetch("/api/...") calls work unchanged in both dev and the built bundle.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8787",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
