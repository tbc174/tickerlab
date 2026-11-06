// O app em React (série 3 da ADR 0048): uma página só, servida na raiz de app.tickerlab.com.br
// (o Streamlit é a versão clássica, em /classico). `npm run app` escreve em ../novo (no repositório,
// como o site/; a pasta guarda o nome antigo): o VPS não precisa de Node. O CI refaz o build e falha
// se a pasta ficar velha.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { type Plugin, defineConfig } from "vite";
import { ICONES, manifesto, servicoDaCasca } from "./src/app/pwa";
import { RAIZ_DO_REPOSITORIO, SOL_JS, lerTexto, versao } from "./src/arquivos";
import { marca } from "./src/conteudo";
import { css } from "./src/estilo";
import { TEMA_SALVO } from "./src/site/tema";

const BASE = "/";
// as fontes do site (vêm do Python: scripts/gerar_site.py), com as licenças junto
const FONTES = [
  "Manrope-VariableFont_wght.woff2",
  "JetBrainsMono-VariableFont_wght.woff2",
  "OFL-Manrope.txt",
  "OFL-JetBrainsMono.txt",
];
// as cores das séries dos gráficos, uma paleta por tema (src/marca.py, as mesmas dos gráficos do
// Streamlit): --serie-1, --serie-2...
const series = (cores: string[]) => cores.map((cor, i) => `--serie-${i + 1}: ${cor};`).join(" ");
// alta e queda (verde e vermelho só com esse significado), para o mapa do retorno mensal
const sinal = (p: { alta: string; queda: string }) => `--alta: ${p.alta}; --queda: ${p.queda};`;
const CORES_DAS_SERIES =
  `:root { ${series(marca.paleta_clara.series)} ${sinal(marca.paleta_clara)} }\n` +
  `:root[data-tema="escuro"] { ${series(marca.paleta_escura.series)} ${sinal(marca.paleta_escura)} }\n`;
// o CSS do site, com as fontes no endereço do app (o build grava uma cópia delas em BASE/fontes/)
const ESTILO = css().replaceAll('url("/fontes/', `url("${BASE}fontes/`) + CORES_DAS_SERIES;

/** O <head> da página: o tema (antes de pintar) e o CSS da marca. LF sempre: o Git no Windows pode
 * tirar o app/index.html com CRLF, e o CI compara o build byte a byte. */
function transformarPagina(html: string): string {
  const semCrlf = html.replace(/\r\n?/g, "\n");
  const cabeca =
    `<script src="${BASE}tema/sol.js?v=${versao(SOL_JS)}"></script>\n    ` +
    `${TEMA_SALVO}\n    ` +
    `<link rel="icon" href="${BASE}simbolo.svg" type="image/svg+xml">\n    ` +
    // o app instalável (PWA): manifesto, ícone do iPhone e a cor da barra do sistema
    `<link rel="manifest" href="${BASE}manifest.json">\n    ` +
    `<link rel="apple-touch-icon" href="${BASE}icones/apple-touch-icon.png">\n    ` +
    `<meta name="theme-color" content="${marca.marinho}">\n    ` +
    `<link rel="stylesheet" href="${BASE}estilo.css?v=${versao(ESTILO)}">`;
  return semCrlf.replace("<!--tema-e-estilo-->", cabeca);
}

/** Põe no <head> o tema e o CSS da marca, e grava os arquivos fixos. */
function arquivosDaMarca(): Plugin {
  return {
    name: "tickerlab-arquivos-da-marca",
    // "pre": antes de o Vite mexer no HTML. Ele tira a tag <script> da página e, com CRLF, sobrava
    // uma linha em branco que o build do CI (LF) não tem
    transformIndexHtml: { order: "pre", handler: transformarPagina },
    generateBundle(_opcoes, pacote) {
      // o que este plugin grava ainda não aparece em `pacote`: a lista vai para a casca do PWA
      const gravados: string[] = [];
      const emitir = (fileName: string, source: string | Uint8Array) => {
        gravados.push(fileName);
        this.emitFile({ type: "asset", fileName, source });
      };
      emitir("estilo.css", ESTILO);
      emitir("tema/sol.js", SOL_JS);
      // texto com LF (a cópia do Windows pode ter CRLF); fonte é binária e vai como está
      const copiar = (destino: string, ...origem: string[]) => {
        const caminho = join(RAIZ_DO_REPOSITORIO, "site", ...origem);
        emitir(destino, /\.(svg|txt)$/.test(destino) ? lerTexto(caminho) : readFileSync(caminho));
      };
      copiar("simbolo.svg", "marca", "simbolo.svg");
      for (const nome of FONTES) copiar(`fontes/${nome}`, "fontes", nome);
      for (const nome of Object.keys(ICONES))
        emitir(`icones/${nome}`, readFileSync(join(RAIZ_DO_REPOSITORIO, "static", "marca", nome)));
      emitir("manifest.json", `${JSON.stringify(manifesto(), null, 2)}\n`);
      // a casca: tudo o que o build grava (menos a página, que entra como a raiz), com o ?v= de quem
      // é pedido assim no HTML; a versão do cache muda quando qualquer arquivo muda de nome
      const comVersao: Record<string, string> = {
        "estilo.css": `estilo.css?v=${versao(ESTILO)}`,
        "tema/sol.js": `tema/sol.js?v=${versao(SOL_JS)}`,
      };
      const casca = [
        BASE,
        ...[...Object.keys(pacote), ...gravados]
          .filter((nome) => !nome.endsWith(".html") && !nome.endsWith(".txt"))
          .sort()
          .map((nome) => BASE + (comVersao[nome] ?? nome)),
      ];
      emitir("sw.js", servicoDaCasca(casca, versao(casca.join("\n"))));
    },
  };
}

export default defineConfig(({ command }) => ({
  root: fileURLToPath(new URL("./app", import.meta.url)),
  base: BASE,
  publicDir: false,
  plugins: [react(), arquivosDaMarca()],
  build: {
    outDir: join(RAIZ_DO_REPOSITORIO, "novo"),
    emptyOutDir: true,
  },
  // `npm run app:dev`: a tela em http://localhost:5173/ falando com a API local (uvicorn na 8000)
  // o X-Forwarded-Host faz o papel do nginx: a API só aceita pedido que muda algo (POST) se a origem
  // for o endereço que o navegador usou, e o proxy troca o Host
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        configure: (proxy) =>
          proxy.on("proxyReq", (pedido, original) => {
            pedido.setHeader("x-forwarded-host", original.headers.host ?? "");
          }),
      },
    },
  },
  // no `app:dev`, a página (em web/app) pede "/src/app/main.tsx" na raiz do servidor, que não existe
  // dentro de web/app; no build o caminho relativo da página já resolve e nada muda
  resolve:
    command === "serve"
      ? { alias: [{ find: /^\/src\//, replacement: fileURLToPath(new URL("./src/", import.meta.url)) }] }
      : {},
}));
