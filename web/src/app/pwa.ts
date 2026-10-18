// O app instalável no celular (PWA, ADR 0066): o manifesto e o service worker. O build do app
// (vite.app.config.ts) grava os dois em novo/ (a pasta guarda o nome; o app é servido na raiz de
// app.tickerlab.com.br). O manifesto se chama manifest.json (e não .webmanifest) porque o nginx do
// VPS já entrega .json com o tipo certo.
import { marca } from "../conteudo";
import { CAMINHO_DO_CLASSICO } from "./classico";
import { PREFIXO_DA_API } from "./configuracao";

const BASE = "/";
// o que mora embaixo da raiz mas não é do app: a versão clássica (o Streamlit, com o /_stcore dela)
// e a API (toda em /api/; a v1 é PREFIXO_DA_API). O service worker não toca em nada disso.
const PREFIXO_DA_API_INTEIRA = `/${PREFIXO_DA_API.split("/")[1]}/`;
export const CAMINHOS_DE_FORA = [`${CAMINHO_DO_CLASSICO}/`, PREFIXO_DA_API_INTEIRA];

/** Os ícones do app instalado (gerados por `python -m scripts.gerar_marca` em static/marca/). */
export const ICONES: Record<string, { tamanho: number; mascaravel?: boolean }> = {
  "icone-192.png": { tamanho: 192 },
  "icone-512.png": { tamanho: 512 },
  "icone-mascaravel-512.png": { tamanho: 512, mascaravel: true },
  "apple-touch-icon.png": { tamanho: 180 }, // o iPhone usa este, ligado no HTML (não no manifesto)
};

interface IconeDoManifesto {
  src: string;
  sizes: string;
  type: "image/png";
  purpose?: "maskable";
}

export function manifesto() {
  const icons: IconeDoManifesto[] = Object.entries(ICONES)
    .filter(([nome]) => nome !== "apple-touch-icon.png")
    .map(([nome, { tamanho, mascaravel }]) => ({
      src: `${BASE}icones/${nome}`,
      sizes: `${tamanho}x${tamanho}`,
      type: "image/png",
      ...(mascaravel ? { purpose: "maskable" as const } : {}),
    }));
  return {
    name: "TickerLab",
    short_name: "TickerLab",
    description: "Plataforma de inteligência financeira: análise de ações e teste de estratégias.",
    lang: "pt-BR",
    start_url: BASE,
    scope: BASE,
    display: "standalone",
    theme_color: marca.marinho,
    background_color: marca.marinho,
    icons,
  };
}

/**
 * O service worker: guarda só a casca do app (HTML, CSS, JS, fontes e ícones do build) num cache
 * com a versão do build e nunca guarda mais nada. A API, a versão clássica e todo pedido com token
 * vão direto à rede, sem passar por ele. Abrir uma tela vai à rede primeiro; sem internet, mostra
 * a casca.
 */
export function servicoDaCasca(casca: string[], versao: string): string {
  return `// Service worker do app TickerLab (gerado por web/src/app/pwa.ts; não editar à mão).
"use strict";
var VERSAO = "tl-casca-${versao}";
var CASCA = ${JSON.stringify(casca)};
var CAMINHOS_DE_FORA = ${JSON.stringify(CAMINHOS_DE_FORA)};

self.addEventListener("install", function (evento) {
  evento.waitUntil(
    caches.open(VERSAO).then(function (cache) { return cache.addAll(CASCA); }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (evento) {
  evento.waitUntil(
    caches.keys().then(function (nomes) {
      return Promise.all(nomes.filter(function (nome) {
        return nome.indexOf("tl-casca-") === 0 && nome !== VERSAO;
      }).map(function (nome) { return caches.delete(nome); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (evento) {
  var pedido = evento.request;
  var endereco = new URL(pedido.url);
  // API, versão clássica, token, escrita e outros domínios: direto à rede, nunca pelo cache
  if (pedido.method !== "GET" || pedido.headers.has("Authorization")) return;
  if (endereco.origin !== self.location.origin) return;
  if (endereco.pathname.indexOf("${BASE}") !== 0) return;
  for (var i = 0; i < CAMINHOS_DE_FORA.length; i++) {
    if (endereco.pathname.indexOf(CAMINHOS_DE_FORA[i]) === 0) return;
  }
  if (pedido.mode === "navigate") {
    evento.respondWith(fetch(pedido).catch(function () { return caches.match("${BASE}"); }));
    return;
  }
  evento.respondWith(caches.match(pedido).then(function (guardado) { return guardado || fetch(pedido); }));
});
`;
}
