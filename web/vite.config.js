import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend is independent from the Python services.
// /api/*     -> backend server (pipeline / assets metadata)
// /api/kg/*  -> KG server (graph / retrieval / agent)
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/kg/" : "/",
  plugins: [react()],
  server: {
    port: 53787,
    proxy: {
      "/api/kg": "http://localhost:53786",
      "/api": "http://localhost:53785",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
}));
