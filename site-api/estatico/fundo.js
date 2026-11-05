/* Fundo "fluxo de dados" do hero: pacotes de luz que correm pelas linhas da grade (56 px, a mesma
   do .v2-grade), virando nos cruzamentos, e trechos de requisição e resposta que se escrevem letra a
   letra, bem apagados, atrás do texto. Obedece ao botão de pausa do v2 (classe v2-pausado no <html>)
   e ao "reduzir movimento" (um quadro parado). O mouse acende o que está perto. */
(function () {
  "use strict";
  var tela = document.querySelector("[data-fundo-api]");
  if (!tela || !tela.getContext) return;
  var raiz = document.documentElement;
  var area = tela.closest(".v2-heroi-fundo") || tela.parentNode;
  var ctx = tela.getContext("2d");
  var menosMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var ponteiroFino = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var PASSO = 56, RAIO_LUZ = 190, FONTE = '13px "JetBrains Mono", ui-monospace, monospace';
  var LETRAS_POR_SEGUNDO = 42;
  var FRASES = [
    "GET /data/v1/companies/33000167000101/financials?known_at=2024-09-30",
    "200 OK · application/json",
    '"source": "cvm-hist-dfp"',
    '"published_at": "2025-02-27"',
    '"license": "ODbL (dados abertos da CVM; citar a fonte)"',
    "GET /data/v1/companies/33000167000101",
    '"document": "ITR", "revision": 1, "valid_until": "2024-11-07"',
    "GET /data/v1/funds/{cnpj}?known_at=2025-06-30",
    '"state": { "value": "EM FUNCIONAMENTO NORMAL" }',
    "POST /data/v1/companies/batch",
    '"attribution": "Fonte: CVM, Portal de Dados Abertos (ODbL)"',
    "GET /data/v1/catalog",
    '"observed_at": null, "sources": [ … ]',
    "Authorization: Bearer <sua chave>",
    "GET /data/v1/usage",
    '"remaining_requests": …'
  ];
  var DIRECOES = [[1, 0], [0, 1], [-1, 0], [0, -1]];
  var largura = 0, altura = 0, escala = Math.min(window.devicePixelRatio || 1, 1.5);
  var pacotes = [], linhas = [], rodando = false, visivel = true, ultimo = 0;
  var mouse = { x: -9999, y: -9999, ativo: false, forca: 0 };

  function aleatorio(a, b) { return a + Math.random() * (b - a); }
  function pausado() { return menosMovimento || raiz.classList.contains("v2-pausado"); }

  function novoPacote(naBorda) {
    var colunas = Math.floor(largura / PASSO), fileiras = Math.floor(altura / PASSO);
    var dir = Math.floor(Math.random() * 4), x, y;
    if (naBorda) {
      // nasce fora da tela, na borda oposta ao sentido em que anda
      if (dir === 0) { x = -PASSO; y = Math.floor(aleatorio(1, fileiras)) * PASSO; }
      else if (dir === 2) { x = (colunas + 1) * PASSO; y = Math.floor(aleatorio(1, fileiras)) * PASSO; }
      else if (dir === 1) { x = Math.floor(aleatorio(1, colunas)) * PASSO; y = -PASSO; }
      else { x = Math.floor(aleatorio(1, colunas)) * PASSO; y = (fileiras + 1) * PASSO; }
    } else {
      x = Math.floor(aleatorio(0, colunas)) * PASSO; y = Math.floor(aleatorio(0, fileiras)) * PASSO;
    }
    var perto = Math.random();
    return { x: x, y: y, dir: dir, vel: aleatorio(55, 130), cauda: aleatorio(50, 140),
      alfa: 0.25 + perto * 0.5, brilho: perto > 0.8, andado: 0 };
  }

  function novaLinha(i, total) {
    var y = altura * (0.12 + 0.8 * (i + 0.5) / total);
    return { y: y, x: 0, frase: "", mostrados: 0, estado: "espera", t: aleatorio(0, 2.5), espera: aleatorio(1.5, 2.5), alfa: 0 };
  }

  function medir() {
    var r = tela.getBoundingClientRect();
    largura = Math.max(1, r.width); altura = Math.max(1, r.height);
    tela.width = Math.round(largura * escala); tela.height = Math.round(altura * escala);
    ctx.setTransform(escala, 0, 0, escala, 0, 0);
    var n = largura < 700 ? 9 : 18;
    pacotes = [];
    for (var i = 0; i < n; i++) pacotes.push(novoPacote(false));
    var total = Math.max(4, Math.min(9, Math.floor(altura / 70)));
    linhas = [];
    for (var k = 0; k < total; k++) linhas.push(novaLinha(k, total));
  }

  function comecarFrase(l) {
    l.frase = FRASES[Math.floor(Math.random() * FRASES.length)];
    ctx.font = FONTE;
    var comp = ctx.measureText(l.frase).width;
    l.x = Math.max(PASSO / 2, aleatorio(PASSO / 2, largura - comp - PASSO / 2));
    l.mostrados = 0; l.estado = "escrevendo"; l.t = 0; l.alfa = 1; l.espera = aleatorio(3, 5);
  }

  function avancarLinha(l, dt) {
    l.t += dt;
    if (l.estado === "espera") { if (l.t >= l.espera) comecarFrase(l); return; }
    if (l.estado === "escrevendo") {
      l.mostrados = Math.min(l.frase.length, l.mostrados + dt * LETRAS_POR_SEGUNDO);
      if (l.mostrados >= l.frase.length) { l.estado = "parado"; l.t = 0; }
      return;
    }
    if (l.estado === "parado") { if (l.t > l.espera) { l.estado = "sumindo"; l.t = 0; } return; }
    l.alfa = Math.max(0, 1 - l.t / 0.8);
    if (l.alfa === 0) { l.estado = "espera"; l.t = 0; l.frase = ""; l.espera = aleatorio(1.5, 2.5); }
  }

  function avancarPacote(p, dt) {
    var passo = p.vel * dt, d = DIRECOES[p.dir];
    p.x += d[0] * passo; p.y += d[1] * passo; p.andado += passo;
    // nos cruzamentos da grade, às vezes vira
    if (p.andado >= PASSO) {
      p.andado -= PASSO;
      p.x = Math.round(p.x / PASSO) * PASSO; p.y = Math.round(p.y / PASSO) * PASSO;
      if (Math.random() < 0.28) p.dir = (p.dir + (Math.random() < 0.5 ? 1 : 3)) % 4;
    }
    var folga = p.cauda + PASSO;
    var fora = p.x < -folga || p.x > largura + folga || p.y < -folga || p.y > altura + folga;
    if (fora) { var novo = novoPacote(true); for (var k in novo) p[k] = novo[k]; }
  }

  function desenhar() {
    ctx.clearRect(0, 0, largura, altura);
    if (mouse.forca > 0.01) {
      var g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, RAIO_LUZ * 1.5);
      g.addColorStop(0, "rgba(41, 98, 255, " + (0.2 * mouse.forca).toFixed(3) + ")");
      g.addColorStop(1, "rgba(41, 98, 255, 0)");
      ctx.fillStyle = g; ctx.fillRect(0, 0, largura, altura);
    }
    // trechos de código
    ctx.font = FONTE; ctx.textBaseline = "middle";
    for (var i = 0; i < linhas.length; i++) {
      var l = linhas[i];
      if (!l.frase) continue;
      var perto = Math.max(0, 1 - Math.hypot(mouse.x - (l.x + 120), mouse.y - l.y) / (RAIO_LUZ * 1.4)) * mouse.forca;
      var texto = l.frase.slice(0, Math.ceil(l.mostrados));
      ctx.fillStyle = "rgba(143, 176, 255, " + ((0.13 + perto * 0.35) * l.alfa).toFixed(3) + ")";
      ctx.fillText(texto, l.x, l.y);
      if (l.estado === "escrevendo") {                         // cursor
        var w = ctx.measureText(texto).width;
        ctx.fillStyle = "rgba(143, 176, 255, " + (0.45 * l.alfa).toFixed(3) + ")";
        ctx.fillRect(l.x + w + 2, l.y - 7, 7, 14);
      }
    }
    // pacotes
    for (var j = 0; j < pacotes.length; j++) {
      var p = pacotes[j], d = DIRECOES[p.dir];
      var x0 = p.x - d[0] * p.cauda, y0 = p.y - d[1] * p.cauda;
      var pertoP = Math.max(0, 1 - Math.hypot(mouse.x - p.x, mouse.y - p.y) / RAIO_LUZ) * mouse.forca;
      var alfa = Math.min(0.95, p.alfa + pertoP * 0.5);
      var gr = ctx.createLinearGradient(x0, y0, p.x, p.y);
      gr.addColorStop(0, "rgba(41, 98, 255, 0)");
      gr.addColorStop(1, "rgba(" + Math.round(110 + pertoP * 80) + ", " + Math.round(149 + pertoP * 60) + ", 255, " + alfa.toFixed(3) + ")");
      ctx.strokeStyle = gr; ctx.lineWidth = p.brilho ? 2 : 1.2; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(p.x, p.y); ctx.stroke();
      ctx.beginPath(); ctx.arc(p.x, p.y, p.brilho ? 2.6 : 1.8, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(200, 216, 255, " + alfa.toFixed(3) + ")"; ctx.fill();
    }
  }

  function quadro(t) {
    if (!rodando) return;
    var dt = ultimo ? Math.min(0.05, (t - ultimo) / 1000) : 0;
    ultimo = t;
    pacotes.forEach(function (p) { avancarPacote(p, dt); });
    linhas.forEach(function (l) { avancarLinha(l, dt); });
    mouse.forca += ((mouse.ativo ? 1 : 0) - mouse.forca) * Math.min(1, dt * 6);
    desenhar();
    requestAnimationFrame(quadro);
  }

  function atualizar() {
    var deve = !pausado() && visivel && !document.hidden;
    if (deve && !rodando) { rodando = true; ultimo = 0; requestAnimationFrame(quadro); }
    if (!deve) rodando = false;
  }

  function quadroParado() {                                   // "reduzir movimento": tudo no lugar, sem andar
    linhas.forEach(function (l) { comecarFrase(l); l.mostrados = l.frase.length; l.estado = "parado"; });
    desenhar();
  }

  function redesenhar() { medir(); if (menosMovimento) quadroParado(); else desenhar(); }

  redesenhar();
  var timer;
  window.addEventListener("resize", function () { clearTimeout(timer); timer = setTimeout(redesenhar, 150); });
  document.addEventListener("visibilitychange", atualizar);
  new MutationObserver(atualizar).observe(raiz, { attributes: true, attributeFilter: ["class"] });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (es) { visivel = es[0].isIntersecting; atualizar(); }).observe(tela);
  }
  if (ponteiroFino && !menosMovimento) {
    area.addEventListener("pointermove", function (e) {
      var r = tela.getBoundingClientRect();
      mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; mouse.ativo = true;
    });
    area.addEventListener("pointerleave", function () { mouse.ativo = false; });
  }
  // profundidade ao rolar, como o fundo do site faz
  var agendado = false;
  window.addEventListener("scroll", function () {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(function () {
      agendado = false;
      var y = window.scrollY;
      if (y < area.offsetHeight + 200) tela.style.translate = "0 " + (y * 0.35).toFixed(1) + "px";
    });
  }, { passive: true });
  atualizar();
})();
