import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Vendor-чанки: react/anim-бібліотеки міняються рідше за наш код, тож
// окремий чанк лишається в кеші юзера між деплоями (наш index.js — ні).
// lucide-react НЕ чіпаємо: sideEffects:false + іменовані імпорти — Rollup
// вже tree-shake'ить невикористані іконки, окремий чанк тут не потрібен.
function manualChunks(id: string): string | undefined {
  if (!id.includes("node_modules")) return undefined;
  if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
    return "react-vendor";
  }
  if (/[\\/]node_modules[\\/](motion|gsap|@gsap[\\/]react|@number-flow[\\/]react)[\\/]/.test(id)) {
    return "anim-vendor";
  }
  return undefined;
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    css: false,
    globals: true,
  },
});
