// Service worker do app TickerLab (gerado por web/src/app/pwa.ts; não editar à mão).
"use strict";
var VERSAO = "tl-casca-009b662748be";
var CASCA = ["/","/assets/ativos-D77YiDpN.js","/assets/index-063VYbUY.css","/assets/index-C14dV_lP.js","/estilo.css?v=99f281ccc6f2","/fontes/JetBrainsMono-VariableFont_wght.woff2","/fontes/Manrope-VariableFont_wght.woff2","/icones/apple-touch-icon.png","/icones/icone-192.png","/icones/icone-512.png","/icones/icone-mascaravel-512.png","/manifest.json","/simbolo.svg","/tema/sol.js?v=e36a88f10cf8"];
var CAMINHOS_DE_FORA = ["/classico/","/api/"];

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
  if (endereco.pathname.indexOf("/") !== 0) return;
  for (var i = 0; i < CAMINHOS_DE_FORA.length; i++) {
    if (endereco.pathname.indexOf(CAMINHOS_DE_FORA[i]) === 0) return;
  }
  if (pedido.mode === "navigate") {
    evento.respondWith(fetch(pedido).catch(function () { return caches.match("/"); }));
    return;
  }
  evento.respondWith(caches.match(pedido).then(function (guardado) { return guardado || fetch(pedido); }));
});
