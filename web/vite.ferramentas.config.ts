// O ferramentas.js do site: um arquivo só (React e as ferramentas), que só as páginas de
// ferramentas carregam. `npm run ferramentas` escreve em ../site/ferramentas.js (no repositório,
// como o resto do site: o VPS não tem Node); `npm run site` roda isto antes das páginas, que levam a
// versão do arquivo no endereço. O CI refaz o build e falha se o arquivo ficar velho.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "../site",
    emptyOutDir: false, // site/ tem o resto do site
    copyPublicDir: false,
    minify: true,
    sourcemap: false,
    lib: {
      entry: "src/ferramentas/cliente.tsx",
      formats: ["iife"],
      name: "ferramentasTickerLab",
      fileName: () => "ferramentas.js",
    },
  },
});
