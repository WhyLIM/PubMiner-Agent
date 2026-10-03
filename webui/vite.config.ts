import path from "path";
import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const __dirname2 = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(() => {
  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname2, "src"),
      },
    },
    server: {
      port: 3001,
      proxy: {
        "/api": {
          target: process.env.VITE_API_TARGET || "http://localhost:8001",
          changeOrigin: true,
        },
      },
    },
  };
});
