import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    strictPort: false,
    host: "127.0.0.1"
  },
  preview: {
    port: 4173,
    host: "127.0.0.1"
  }
});
