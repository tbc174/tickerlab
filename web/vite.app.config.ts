// O app em React (série 3 da ADR 0048): uma página só, servida em app.tickerlab.com.br/novo/.
// `npm run app` escreve em ../novo (no repositório, como o site/): o VPS não precisa de Node. O CI
// refaz o build e falha se a pasta ficar velha.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { type Plugin, defineConfig } from "vite";
import { RAIZ_DO_REPOSITORIO, SOL_JS, lerTexto, versao } from "./src/arquivos";
import { marca } from "./src/conteudo";
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
// as cores das séries dos gráficos, uma paleta por tema (src/marca.py, as mesmas dos gráficos do
// Streamlit): --serie-1, --serie-2...
const series = (cores: string[]) => cores.map((cor, i) => `--serie-${i + 1}: ${cor};`).join(" ");
const CORES_DAS_SERIES =
  `:root { ${series(marca.paleta_clara.series)} }\n` +
  `:root[data-tema="escuro"] { ${series(marca.paleta_escura.series)} }\n`;
// o CSS do site, com as fontes dentro de /novo/ (o app fica em outro endereço que o site)
const ESTILO = css().replaceAll('url("/fontes/', `url("${BASE}fontes/`) + CORES_DAS_SERIES;

/** Põe no <head> o tema (antes de pintar) e o CSS da marca, e grava os arquivos fixos. */
function arquivosDaMarca(): Plugin {
  return {
    name: "tickerlab-arquivos-da-marca",
    transformIndexHtml(html) {
      // LF sempre: o Git no Windows pode tirar o app/index.html com CRLF, e o CI compara byte a byte
      const semCrlf = html.replace(/\r\n?/g, "\n");
      const cabeca =
        `<script src="${BASE}tema/sol.js?v=${versao(SOL_JS)}"></script>\n    ` +
        `${TEMA_SALVO}\n    ` +
        `<link rel="icon" href="${BASE}simbolo.svg" type="image/svg+xml">\n    ` +
        `<link rel="stylesheet" href="${BASE}estilo.css?v=${versao(ESTILO)}">`;
      return semCrlf.replace("<!--tema-e-estilo-->", cabeca);
    },
    generateBundle() {
      const emitir = (fileName: string, source: string | Uint8Array) =>
        this.emitFile({ type: "asset", fileName, source });
      emitir("estilo.css", ESTILO);
      emitir("tema/sol.js", SOL_JS);
      // texto com LF (a cópia do Windows pode ter CRLF); fonte é binária e vai como está
      const copiar = (destino: string, ...origem: string[]) => {
        const caminho = join(RAIZ_DO_REPOSITORIO, "site", ...origem);
        emitir(destino, /\.(svg|txt)$/.test(destino) ? lerTexto(caminho) : readFileSync(caminho));
      };
      copiar("simbolo.svg", "marca", "simbolo.svg");
      for (const nome of FONTES) copiar(`fontes/${nome}`, "fontes", nome);
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
