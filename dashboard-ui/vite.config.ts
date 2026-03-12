import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: resolve(__dirname, "../src/flow_healer/dashboard_static"),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: "assets/dashboard.js",
        chunkFileNames: "assets/dashboard.js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith(".css")) {
            return "assets/dashboard.css";
          }
          return "assets/[name][extname]";
        },
      },
    },
  },
});
