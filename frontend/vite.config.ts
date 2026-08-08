import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

// ESM config: `__dirname` does not exist here. `import.meta.dirname` is the
// Node 20.11+ equivalent and avoids a fileURLToPath dance.
const here = import.meta.dirname;

// Test config lives in vitest.config.ts, not here. Keeping them separate avoids
// the dual-Vite type collision that arises when vitest bundles its own copy.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": resolve(here, "src") },
  },
  build: {
    // The build lands directly in the backend's static directory: one process
    // serves both in the demo (ADR-01). `npm run dev` proxies /api instead --
    // a development convenience, not the demo path.
    outDir: resolve(here, "../backend/app/static"),
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
