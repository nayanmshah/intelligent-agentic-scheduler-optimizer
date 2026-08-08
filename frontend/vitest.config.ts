import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

const here = import.meta.dirname;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(here, "src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
