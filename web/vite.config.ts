// O site público em React (ADR 0048): o Vite monta o JavaScript do navegador, e o
// scripts/prerender.mjs escreve o HTML pronto de cada página, com os mesmos nomes de hoje.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    manifest: true, // o prerender acha o nome final do JavaScript por aqui
    rollupOptions: { input: "src/entry-client.tsx" },
  },
  test: {
    include: ["testes/**/*.test.{ts,tsx}"],
  },
});
