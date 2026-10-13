// O site público em React (ADR 0048): o `vite build --ssr` monta o renderizador, e o
// scripts/prerender.mjs escreve o HTML pronto de cada página, com os mesmos nomes de hoje.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  publicDir: false, // o site.js vai junto pelo prerender (arquivosFixos)
  test: {
    include: ["testes/**/*.test.{ts,tsx}"],
  },
});
