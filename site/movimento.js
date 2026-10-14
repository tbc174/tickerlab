/* As animações do site (ADR 0065). Vieram do protótipo aprovado em 14/10/2026.
   Contínuas (param com o botão de pausa, fora da tela, com a aba escondida e com "reduzir
   movimento"): fundo "mercado vivo", aurora, borda viva do painel e fita de ativos.
   Uma vez: dígitos do número principal (sem contar: o valor nunca muda), títulos palavra por palavra,
   revelar ao rolar. Reações: o mouse acende o fundo, luz nos cartões, painel inclinado, botões
   magnéticos, profundidade ao rolar e menu que encolhe.
   O que esconde algo para animar (v2-anima, v2-revelar) só entra por aqui: sem JavaScript, ou para
   o Google, a página aparece inteira. */
(function () {
  "use strict";
  var raiz = document.documentElement;
  var menosMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var ponteiroFino = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var CHAVE_PAUSA = "tl-animacao-pausada";
  var pausado = menosMovimento || lerPausa();
  var aoMudarPausa = [];

  function lerPausa() { try { return localStorage.getItem(CHAVE_PAUSA) === "1"; } catch (e) { return false; } }
  function gravarPausa(v) { try { localStorage.setItem(CHAVE_PAUSA, v ? "1" : "0"); } catch (e) {} }

  /* ---------- botão de pausa (vale para tudo que roda sem parar) ---------- */
  var botaoPausa = document.querySelector("[data-pausa]");
  function aplicarPausa() {
    raiz.classList.toggle("v2-pausado", pausado);
    if (botaoPausa) {
      botaoPausa.setAttribute("aria-pressed", String(pausado));
      botaoPausa.querySelector("span").textContent = pausado ? "Retomar animação" : "Pausar animação";
    }
    aoMudarPausa.forEach(function (f) { f(); });
  }
  if (botaoPausa) {
    if (menosMovimento) botaoPausa.hidden = true;
    botaoPausa.addEventListener("click", function () { pausado = !pausado; gravarPausa(pausado); aplicarPausa(); });
  }

  /* ---------- 1. fundo "mercado vivo" ---------- */
  var heroi = document.querySelector(".v2-heroi-fundo");
  var tela = heroi ? heroi.querySelector("[data-fundo-mercado]") : null;   // a do hero, para a profundidade ao rolar
  // cada canvas [data-fundo-mercado] da página ganha a sua animação; a luz do mouse vale dentro da área dele
  Array.prototype.forEach.call(document.querySelectorAll("[data-fundo-mercado]"), function (tela) {
    var area = tela.closest(".v2-heroi-fundo, [data-fundo-area]") || tela.parentNode;
    var ctx = tela.getContext("2d");
    if (!ctx) return;
    var largura = 0, altura = 0, escala = Math.min(window.devicePixelRatio || 1, 1.5);
    var PASSO = 16, VELOCIDADE = 14, RAIO_LUZ = 170;
    var series = [], deslocamento = 0, ultimo = 0, rodando = false, visivel = true;
    var mouse = { x: -9999, y: -9999, ativo: false, forca: 0 };

    var aleatorio = function (a, b) { return a + Math.random() * (b - a); };

    var novaSerie = function (i, total) {
      var pontos = [], y = 0, n = Math.ceil(largura / PASSO) + 3;
      var tendencia = aleatorio(-0.15, 0.35);
      for (var k = 0; k < n; k++) { y += tendencia + aleatorio(-1.6, 1.6); pontos.push(y); }
      var perto = Math.random();
      return { base: (i + 0.5) / total, pontos: pontos, tendencia: tendencia, amplitude: aleatorio(6, 14),
        alfa: 0.05 + perto * 0.16, espessura: perto > 0.85 ? 1.8 : 1, destaque: perto > 0.9 };
    };

    var medir = function () {
      var r = tela.getBoundingClientRect();
      largura = Math.max(1, r.width); altura = Math.max(1, r.height);
      tela.width = Math.round(largura * escala); tela.height = Math.round(altura * escala);
      ctx.setTransform(escala, 0, 0, escala, 0, 0);
      var total = largura < 700 ? 14 : 26;
      series = [];
      for (var i = 0; i < total; i++) series.push(novaSerie(i, total));
    };

    var avancar = function (s) {
      var proximo = s.pontos[s.pontos.length - 1] + s.tendencia + aleatorio(-1.6, 1.6);
      if (Math.abs(proximo) > 40) proximo -= Math.sign(proximo) * 2.2;
      s.pontos.shift(); s.pontos.push(proximo);
    };

    var desenhar = function () {
      ctx.clearRect(0, 0, largura, altura);
      // luz do mouse: um halo azul suave que acompanha o cursor
      if (mouse.forca > 0.01) {
        var g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, RAIO_LUZ * 1.6);
        g.addColorStop(0, "rgba(41, 98, 255, " + (0.22 * mouse.forca).toFixed(3) + ")");
        g.addColorStop(1, "rgba(41, 98, 255, 0)");
        ctx.fillStyle = g; ctx.fillRect(0, 0, largura, altura);
      }
      for (var i = 0; i < series.length; i++) {
        var s = series[i], y0 = s.base * altura, esc = s.amplitude / 10;
        // perto do cursor a linha acende: compara a altura da série com a do mouse
        var kMouse = Math.round((mouse.x + deslocamento) / PASSO);
        var yMouse = (kMouse >= 0 && kMouse < s.pontos.length) ? y0 - s.pontos[kMouse] * esc : -9999;
        var perto = Math.max(0, 1 - Math.abs(yMouse - mouse.y) / RAIO_LUZ) * mouse.forca;
        ctx.beginPath();
        for (var k = 0; k < s.pontos.length; k++) {
          var x = k * PASSO - deslocamento, y = y0 - s.pontos[k] * esc;
          if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = "rgba(" + (110 + perto * 60 | 0) + ", " + (149 + perto * 50 | 0) + ", 255, " + Math.min(0.85, s.alfa + perto * 0.55).toFixed(3) + ")";
        ctx.lineWidth = s.espessura + perto * 0.8;
        ctx.stroke();
        if (s.destaque) {
          var n = s.pontos.length - 2;
          ctx.beginPath(); ctx.arc(n * PASSO - deslocamento, y0 - s.pontos[n] * esc, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(169, 193, 255, .7)"; ctx.fill();
        }
      }
    };

    var quadro = function (t) {
      if (!rodando) return;
      var dt = ultimo ? Math.min(0.05, (t - ultimo) / 1000) : 0;
      ultimo = t;
      deslocamento += VELOCIDADE * dt;
      while (deslocamento >= PASSO) { deslocamento -= PASSO; series.forEach(avancar); }
      mouse.forca += ((mouse.ativo ? 1 : 0) - mouse.forca) * Math.min(1, dt * 6);
      desenhar();
      requestAnimationFrame(quadro);
    };

    var atualizar = function () {
      var deve = !pausado && visivel && !document.hidden;
      if (deve && !rodando) { rodando = true; ultimo = 0; requestAnimationFrame(quadro); }
      if (!deve) rodando = false;
    };

    medir(); desenhar();
    var timer;
    window.addEventListener("resize", function () { clearTimeout(timer); timer = setTimeout(function () { medir(); desenhar(); }, 150); });
    document.addEventListener("visibilitychange", atualizar);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        visivel = es[0].isIntersecting;
        if (visivel && largura <= 1) { medir(); desenhar(); }   // estava escondido quando a página abriu
        atualizar();
      }).observe(tela);
    }
    if (ponteiroFino && !menosMovimento) {
      area.addEventListener("pointermove", function (e) {
        var r = tela.getBoundingClientRect();
        mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; mouse.ativo = true;
      });
      area.addEventListener("pointerleave", function () { mouse.ativo = false; });
    }
    aoMudarPausa.push(atualizar);
  });
  aplicarPausa();

  /* ---------- estrutura das páginas (vale mesmo com "reduzir movimento") ---------- */
  // barra de leitura (Termos, Privacidade, Metodologia, Novidades)
  var progresso = document.querySelector("[data-progresso]");

  // menu de atalhos que gruda no topo (Produto)
  var atalhos = document.querySelector(".v2-pagina-topo .atalhos");
  var subnav = null;
  if (atalhos) {
    subnav = document.createElement("nav");
    subnav.className = "v2-subnav"; subnav.setAttribute("aria-label", "Seções desta página");
    atalhos.querySelectorAll("a").forEach(function (a) {
      var c = document.createElement("a"); c.href = a.getAttribute("href"); c.textContent = a.textContent; subnav.appendChild(c);
    });
    document.body.appendChild(subnav);
    if ("IntersectionObserver" in window) {
      var secoes = Array.prototype.map.call(subnav.querySelectorAll("a"), function (a) { return document.querySelector(a.hash); }).filter(Boolean);
      var espiaSecao = new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (!e.isIntersecting) return;
          subnav.querySelectorAll("a").forEach(function (a) { a.toggleAttribute("aria-current", a.hash === "#" + e.target.id); });
        });
      }, { rootMargin: "-30% 0px -60% 0px" });
      secoes.forEach(function (s) { espiaSecao.observe(s); });
    }
  }

  // linha do tempo que se preenche ao rolar (Sobre)
  var linhaTempo = document.querySelector(".linha-do-tempo");

  function estruturaAoRolar() {
    var y = window.scrollY, vh = window.innerHeight;
    if (progresso) {
      var total = document.documentElement.scrollHeight - vh;
      progresso.style.transform = "scaleX(" + (total > 0 ? Math.min(1, y / total) : 0).toFixed(4) + ")";
    }
    if (subnav && heroi) subnav.classList.toggle("mostrar", heroi.getBoundingClientRect().bottom < 0);
    if (linhaTempo) {
      var r = linhaTempo.getBoundingClientRect();
      var p = Math.max(0, Math.min(1, (vh * 0.7 - r.top) / r.height));
      linhaTempo.style.setProperty("--progresso", p.toFixed(3));
    }
  }
  var estruturaAgendada = false;
  window.addEventListener("scroll", function () {
    if (!estruturaAgendada) { estruturaAgendada = true; requestAnimationFrame(function () { estruturaAgendada = false; estruturaAoRolar(); }); }
  }, { passive: true });
  estruturaAoRolar();

  if (menosMovimento) return;                            // daqui para baixo, só enfeites de movimento

  /* ---------- 2. o número principal sobe dígito por dígito (sem contar: o valor nunca muda) ---------- */
  document.querySelectorAll(".v2-numero").forEach(function (el) {
    var texto = el.textContent.trim();
    el.setAttribute("aria-label", texto);
    var html = "";
    Array.prototype.forEach.call(el.childNodes, function (no) {
      if (no.nodeType === 3) {
        no.textContent.split("").forEach(function (ch) {
          html += ch === " " ? " " : '<span class="v2-digito" aria-hidden="true"><span>' + ch + "</span></span>";
        });
      } else { html += no.outerHTML; }
    });
    el.innerHTML = html;
    el.querySelectorAll(".v2-digito > span").forEach(function (d, i) { d.style.animationDelay = (650 + i * 55) + "ms"; });
  });

  /* ---------- 3. títulos palavra por palavra ---------- */
  function separarPalavras(el) {
    var i = 0;
    Array.prototype.slice.call(el.childNodes).forEach(function (no) {
      if (no.nodeType === 3) {
        var frag = document.createDocumentFragment();
        no.textContent.split(/(\s+)/).forEach(function (p) {
          if (!p) return;
          if (/^\s+$/.test(p)) { frag.appendChild(document.createTextNode(p)); return; }
          var s = document.createElement("span"); s.className = "v2-palavra"; s.textContent = p;
          s.style.transitionDelay = (i++ * 45) + "ms"; frag.appendChild(s);
        });
        no.parentNode.replaceChild(frag, no);
      } else if (no.nodeType === 1) {
        no.classList.add("v2-palavra"); no.style.transitionDelay = (i++ * 45) + "ms";
      }
    });
  }

  /* ---------- 4. revelar ao rolar (uma vez) ---------- */
  if ("IntersectionObserver" in window) {
    raiz.classList.add("v2-anima");
    var titulos = document.querySelectorAll(".secao:not(.texto-longo):not(.v2-pagina-topo) > h2");
    titulos.forEach(function (h) { separarPalavras(h); h.classList.add("v2-titulo-palavras"); });
    var alvos = Array.prototype.filter.call(document.querySelectorAll(
      ".secao > .olho, .secao > .subtitulo, .secao > .modulo-topo, .v2-bento > *, .grade > *, " +
      ".v2-fontes li, .vitrine, .final > :not(h2), .v2-fita, .passos > li, .linha-do-tempo > li, .faq details, " +
      ".v2-planos > *, .v2-promessas > li, .v2-venn, .tabela, .pilares-sobre li"),
      function (el) { return !el.closest(".v2-pagina-topo, .texto-longo"); });
    var vistos = new IntersectionObserver(function (es) {
      var atraso = 0;
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        if (!e.target.classList.contains("v2-titulo-palavras")) { e.target.style.transitionDelay = atraso + "ms"; atraso += 70; }
        e.target.classList.add("visivel");
        vistos.unobserve(e.target);
        // depois de chegar, o atraso some para não atrasar o hover
        setTimeout(function (t) { t.style.transitionDelay = ""; }, 1400, e.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    alvos.forEach(function (el) { el.classList.add("v2-revelar"); vistos.observe(el); });
    titulos.forEach(function (el) { vistos.observe(el); });
    var faixas = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("visivel"); faixas.unobserve(e.target); } });
    }, { threshold: 0.25 });
    document.querySelectorAll(".v2-final-fundo, .v2-diferenca, .passos, .v2-acreditamos").forEach(function (el) { faixas.observe(el); });
  }

  /* ---------- 5. profundidade ao rolar e menu que encolhe ---------- */
  var pilha = document.querySelector(".v2-painel-pilha");
  var texto = document.querySelector(".v2-heroi-fundo .heroi-texto");
  var agendado = false;
  function aoRolar() {
    agendado = false;
    var y = window.scrollY;
    raiz.classList.toggle("v2-rolou", y > 40);
    if (heroi && y < heroi.offsetHeight + 200) {
      if (tela) tela.style.translate = "0 " + (y * 0.35).toFixed(1) + "px";
      if (pilha) pilha.style.translate = "0 " + (y * -0.12).toFixed(1) + "px";
      if (texto) texto.style.translate = "0 " + (y * 0.08).toFixed(1) + "px";
    }
  }
  window.addEventListener("scroll", function () { if (!agendado) { agendado = true; requestAnimationFrame(aoRolar); } }, { passive: true });
  aoRolar();

  if (!ponteiroFino) return;

  /* ---------- 6. luz que segue o cursor nos cartões ---------- */
  document.querySelectorAll(".v2-bento .cartao, .v2-principio, .grade .cartao, .pilar, .v2-plano").forEach(function (c) {
    c.addEventListener("pointermove", function (e) {
      var r = c.getBoundingClientRect();
      c.style.setProperty("--mx", (e.clientX - r.left) + "px");
      c.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  });

  /* ---------- 7. leve inclinação do painel do hero ---------- */
  var painel = document.querySelector(".v2-painel");
  if (heroi && painel) {
    heroi.addEventListener("pointermove", function (e) {
      var r = heroi.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      painel.style.transform = "perspective(1200px) rotateY(" + (x * 6).toFixed(2) + "deg) rotateX(" + (-y * 5).toFixed(2) + "deg)";
    });
    heroi.addEventListener("pointerleave", function () { painel.style.transform = ""; });
  }

  /* ---------- 8. botões magnéticos ---------- */
  document.querySelectorAll(".v2-heroi-fundo .botao.primario, .final .botao.primario").forEach(function (b) {
    b.addEventListener("pointermove", function (e) {
      var r = b.getBoundingClientRect();
      var x = (e.clientX - r.left - r.width / 2) / r.width, y = (e.clientY - r.top - r.height / 2) / r.height;
      b.style.translate = (x * 10).toFixed(1) + "px " + (y * 8).toFixed(1) + "px";
    });
    b.addEventListener("pointerleave", function () { b.style.translate = ""; });
  });
})();
