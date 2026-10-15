// Service worker do app TickerLab (gerado por web/src/app/pwa.ts; não editar à mão).
"use strict";
var VERSAO = "tl-casca-bf8409577eb2";
var CASCA = ["/novo/","/novo/assets/index-DRfoafEo.js","/novo/assets/index-Dgu3o3gX.css","/novo/estilo.css?v=26a365eec439","/novo/fontes/JetBrainsMono-VariableFont_wght.ttf","/novo/fontes/Manrope-VariableFont_wght.ttf","/novo/icones/apple-touch-icon.png","/novo/icones/icone-192.png","/novo/icones/icone-512.png","/novo/icones/icone-mascaravel-512.png","/novo/manifest.json","/novo/simbolo.svg","/novo/tema/sol.js?v=e36a88f10cf8"];

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
  // API, token, escrita e outros endereços: direto à rede, nunca pelo cache
  if (pedido.method !== "GET" || pedido.headers.has("Authorization")) return;
  if (endereco.origin !== self.location.origin) return;
  if (endereco.pathname.indexOf("/novo/") !== 0) return;
  if (pedido.mode === "navigate") {
    evento.respondWith(fetch(pedido).catch(function () { return caches.match("/novo/"); }));
    return;
  }
  evento.respondWith(caches.match(pedido).then(function (guardado) { return guardado || fetch(pedido); }));
});
