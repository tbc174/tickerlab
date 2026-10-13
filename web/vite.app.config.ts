// O app em React (série 3 da ADR 0048): uma página só, servida em app.tickerlab.com.br/novo/.
// `npm run app` escreve em ../novo (no repositório, como o site/): o VPS não precisa de Node. O CI
// refaz o build e falha se a pasta ficar velha.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { type Plugin, defineConfig } from "vite";
import { RAIZ_DO_REPOSITORIO, SOL_JS, versao } from "./src/arquivos";
import { css } from "./src/estilo";
import { TEMA_SALVO } from "./src/site/tema";

const BASE = "/novo/";
// as fontes do site (vêm do Python: scripts/gerar_site.py), com as licenças junto
const FONTES = [
  "Manrope-VariableFont_wght.ttf",
  "JetBrainsMono-VariableFont_wght.ttf",
  "OFL-Manrope.txt",
  "OFL-JetBrainsMono.txt",
];
// o CSS do site, com as fontes dentro de /novo/ (o app fica em outro endereço que o site)
const ESTILO = css().replaceAll('url("/fontes/', `url("${BASE}fontes/`);

/** Põe no <head> o tema (antes de pintar) e o CSS da marca, e grava os arquivos fixos. */
function arquivosDaMarca(): Plugin {
  return {
    name: "tickerlab-arquivos-da-marca",
    transformIndexHtml(html) {
      const cabeca =
        `<script src="${BASE}tema/sol.js?v=${versao(SOL_JS)}"></script>\n    ` +
        `${TEMA_SALVO}\n    ` +
        `<link rel="icon" href="${BASE}simbolo.svg" type="image/svg+xml">\n    ` +
        `<link rel="stylesheet" href="${BASE}estilo.css?v=${versao(ESTILO)}">`;
      return html.replace("<!--tema-e-estilo-->", cabeca);
    },
    generateBundle() {
      const emitir = (fileName: string, source: string | Uint8Array) =>
        this.emitFile({ type: "asset", fileName, source });
      emitir("estilo.css", ESTILO);
      emitir("tema/sol.js", SOL_JS);
      emitir("simbolo.svg", readFileSync(join(RAIZ_DO_REPOSITORIO, "site", "marca", "simbolo.svg")));
      for (const nome of FONTES) {
        emitir(`fontes/${nome}`, readFileSync(join(RAIZ_DO_REPOSITORIO, "site", "fontes", nome)));
      }
    },
  };
}

export default defineConfig({
  root: fileURLToPath(new URL("./app", import.meta.url)),
  base: BASE,
  publicDir: false,
  plugins: [react(), arquivosDaMarca()],
  build: {
    outDir: join(RAIZ_DO_REPOSITORIO, "novo"),
    emptyOutDir: true,
  },
  // `npm run app:dev`: a tela em http://localhost:5173/novo/ falando com a API local (uvicorn na 8000)
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
