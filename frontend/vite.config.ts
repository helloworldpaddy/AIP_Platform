import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      "/a2a": {
        target: process.env.VITE_A2A_TARGET ?? "http://localhost:8100",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/a2a/, ""),
      },
    },
  },
});
