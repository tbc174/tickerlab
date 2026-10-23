// O ferramentas.js do site: um arquivo só (as ferramentas e o Preact), que só as páginas de
// ferramentas carregam. `npm run ferramentas` escreve em ../site/ferramentas.js (no repositório,
// como o resto do site: o VPS não tem Node); `npm run site` roda isto antes das páginas, que levam a
// versão do arquivo no endereço. O CI refaz o build e falha se o arquivo ficar velho.
//
// O código das ferramentas é React (as páginas prontas saem do renderToStaticMarkup), mas no
// navegador roda sobre o preact/compat, a mesma interface em ~10 KB: sem o react-dom, o script caiu
// de 98 KB para 38 KB comprimidos. O testes/ferramentas/no_preact.test.ts roda o arquivo gerado.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  resolve: {
    // do mais específico para o mais geral: o primeiro que casa ganha
    alias: [
      { find: /^react\/jsx-(dev-)?runtime$/, replacement: "preact/jsx-runtime" },
      { find: /^react-dom\/client$/, replacement: "preact/compat/client" },
      { find: /^react(-dom)?$/, replacement: "preact/compat" },
    ],
  },
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
