import path from "path";
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const __dirname2 = path.dirname(fileURLToPath(import.meta.url));
// 版本号单一来源：与后端 pyproject.toml 保持一致
const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf-8"));

export default defineConfig(() => {
  return {
    plugins: [vue(), tailwindcss()],
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
    },
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
