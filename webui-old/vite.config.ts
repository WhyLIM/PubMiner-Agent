import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 3001,
    proxy: {
      // 开发态同源代理到后端，浏览器无跨域问题；SSE 亦可代理
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
});
