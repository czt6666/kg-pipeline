import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend (src/serve.py) owns the API + data; this only builds/serves the SPA.
// In dev, requests to /api/* are proxied to the Python server so the same
// fetch("/api/...") calls work unchanged in both dev and the built bundle.
// Deployed behind nginx at czt666.cn/kg/ (see src/serve.py's module docstring),
// so built asset URLs need the /kg/ prefix. `base` affects the dev server's own
// URL too (not just `vite build`), so it's conditional on the command — `npm run
// dev` keeps serving from / (http://localhost:5173/), only `npm run build` gets
// the /kg/ prefix baked into dist/.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/kg/" : "/",
  plugins: [react()],
  server: {
    port: 53786,
    proxy: {
      "/api": "http://localhost:53785",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
}));
