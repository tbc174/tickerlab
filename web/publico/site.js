// web/publico/site.js — tema, busca de ativos e vitrine do Report Studio (era gerado por scripts/gerar_site.py)
(() => {
  "use strict";

  // --- tema: claro, escuro ou automático (claro de dia, escuro à noite, pelo fuso do aparelho) --
  // A escolha fica neste navegador ("tema" no localStorage); o <head> já aplicou a da última vez.
  const raiz = document.documentElement;
  const corDaBarra = document.querySelector('meta[name="theme-color"]');
  const NOMES = { claro: "Claro", escuro: "Escuro", auto: "Automático" };
  const temaDaEscolha = (escolha) => {
    if (escolha !== "auto") return escolha;
    const sol = window.TickerLabSol;
    return sol ? sol.temaDoMomento(new Date(), sol.fusoDoAparelho()) : "claro";
  };
  const pintar = (tema) => {
    if (tema === "escuro") raiz.dataset.tema = "escuro"; else delete raiz.dataset.tema;
    // a barra do navegador no celular acompanha o fundo (a cor vem do próprio CSS)
    if (corDaBarra) corDaBarra.content = getComputedStyle(raiz).getPropertyValue("--fundo").trim();
  };
  const aplicarTema = (escolha, comTransicao) => {
    raiz.dataset.escolha = escolha;
    const tema = temaDaEscolha(escolha);
    const mudou = (raiz.dataset.tema === "escuro") !== (tema === "escuro");
    const calmo = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (mudou && comTransicao && document.startViewTransition && !calmo) {
      document.startViewTransition(() => pintar(tema));
    } else {
      pintar(tema);
    }
    for (const opcao of document.querySelectorAll("[data-tema-escolha]")) {
      opcao.setAttribute("aria-checked", String(opcao.dataset.temaEscolha === escolha));
    }
    for (const botao of document.querySelectorAll("[data-tema-botao]")) {
      botao.setAttribute("aria-label", "Tema: " + NOMES[escolha]);
      botao.title = "Tema: " + NOMES[escolha];
    }
  };
  aplicarTema(raiz.dataset.escolha || "auto", false);
  // no automático, confere a cada minuto: troca sozinho no nascer e no pôr do sol
  setInterval(() => { if (raiz.dataset.escolha === "auto") aplicarTema("auto", true); }, 60000);

  for (const menu of document.querySelectorAll(".tema-menu")) {
    const botao = menu.querySelector("[data-tema-botao]");
    const lista = menu.querySelector(".tema-opcoes");
    const opcoes = [...lista.querySelectorAll("[data-tema-escolha]")];
    const fechar = (devolverFoco) => {
      lista.hidden = true;
      botao.setAttribute("aria-expanded", "false");
      if (devolverFoco) botao.focus();
    };
    const abrir = () => {
      lista.hidden = false;
      botao.setAttribute("aria-expanded", "true");
      (opcoes.find((o) => o.getAttribute("aria-checked") === "true") || opcoes[0]).focus();
    };
    botao.addEventListener("click", () => (lista.hidden ? abrir() : fechar(true)));
    for (const opcao of opcoes) {
      opcao.addEventListener("click", () => {
        const escolha = opcao.dataset.temaEscolha;
        try { localStorage.setItem("tema", escolha); } catch (e) {}
        aplicarTema(escolha, true);
        fechar(true);
      });
    }
    lista.addEventListener("keydown", (e) => {
      const atual = opcoes.indexOf(document.activeElement);
      if (e.key === "Escape") { fechar(true); }
      else if (e.key === "ArrowDown") { opcoes[(atual + 1) % opcoes.length].focus(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { opcoes[(atual - 1 + opcoes.length) % opcoes.length].focus(); e.preventDefault(); }
      else if (e.key === "Tab") { fechar(false); }
    });
    document.addEventListener("click", (e) => { if (!menu.contains(e.target)) fechar(false); });
  }
  // --- menu do celular: o botão abre e fecha a lista do topo ------------------------------------
  const botaoDoMenu = document.querySelector("[data-menu-botao]");
  const menuPrincipal = botaoDoMenu && document.getElementById(botaoDoMenu.getAttribute("aria-controls"));
  if (menuPrincipal) {
    const mostrarMenu = (aberto) => {
      menuPrincipal.toggleAttribute("data-aberto", aberto);
      botaoDoMenu.setAttribute("aria-expanded", String(aberto));
      botaoDoMenu.setAttribute("aria-label", aberto ? "Fechar o menu" : "Abrir o menu");
    };
    const estaAberto = () => menuPrincipal.hasAttribute("data-aberto");
    botaoDoMenu.addEventListener("click", () => mostrarMenu(!estaAberto()));
    // "Relatórios" é uma âncora na inicial: sem fechar, o menu ficaria aberto sobre a seção
    menuPrincipal.addEventListener("click", (e) => { if (e.target.closest("a")) mostrarMenu(false); });
    document.addEventListener("click", (e) => {
      if (estaAberto() && !menuPrincipal.contains(e.target) && !botaoDoMenu.contains(e.target)) mostrarMenu(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && estaAberto()) { mostrarMenu(false); botaoDoMenu.focus(); }
    });
  }

  const semAcento = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // --- busca: filtra o catálogo enquanto a pessoa digita e abre a análise no app -----------
  const form = document.querySelector("[data-busca]");
  if (form) {
    const campo = form.querySelector("input");
    const lista = form.querySelector("#sugestoes");
    const app = form.dataset.app;
    let ativos = null, achados = [], escolhido = -1;
    const carregar = async () => {
      if (ativos) return ativos;
      try {
        const resposta = await fetch("/catalogo.json");
        ativos = (await resposta.json()).map((a) => ({
          simbolo: a[0], codigo: a[1], nome: a[2], bolsa: a[3], tipo: a[4],
          busca: semAcento(a[1] + " " + a[2]),
        }));
      } catch (erro) { ativos = []; }
      return ativos;
    };
    const fechar = () => { lista.hidden = true; campo.setAttribute("aria-expanded", "false"); escolhido = -1; };
    const abrirNoApp = (simbolo) => {
      window.location.href = app + "/visao-geral?ticker=" + encodeURIComponent(simbolo);
    };
    const mostrar = () => {
      lista.replaceChildren();
      achados.forEach((a, i) => {
        const item = document.createElement("li");
        item.id = "sugestao-" + i;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", i === escolhido ? "true" : "false");
        for (const [classe, texto] of [["codigo", a.codigo], ["nome", a.nome], ["tipo", a.bolsa + (a.tipo && a.tipo !== a.bolsa ? " · " + a.tipo : "")]]) {
          const parte = document.createElement("span");
          parte.className = classe; parte.textContent = texto; item.append(parte);
        }
        item.addEventListener("mousedown", (e) => { e.preventDefault(); abrirNoApp(a.simbolo); });
        lista.append(item);
      });
      lista.hidden = achados.length === 0;
      campo.setAttribute("aria-expanded", String(!lista.hidden));
      campo.setAttribute("aria-activedescendant", escolhido >= 0 ? "sugestao-" + escolhido : "");
    };
    campo.addEventListener("input", async () => {
      const termo = semAcento(campo.value.trim());
      if (!termo) { achados = []; fechar(); return; }
      const todos = await carregar();
      const comeca = todos.filter((a) => semAcento(a.codigo).startsWith(termo));
      const contem = todos.filter((a) => !semAcento(a.codigo).startsWith(termo) && a.busca.includes(termo));
      achados = comeca.concat(contem).slice(0, 8);
      escolhido = achados.length ? 0 : -1;
      mostrar();
    });
    campo.addEventListener("keydown", (e) => {
      if (lista.hidden) return;
      if (e.key === "ArrowDown") { escolhido = Math.min(escolhido + 1, achados.length - 1); mostrar(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { escolhido = Math.max(escolhido - 1, 0); mostrar(); e.preventDefault(); }
      else if (e.key === "Escape") { fechar(); }
    });
    campo.addEventListener("blur", () => setTimeout(fechar, 120));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (escolhido >= 0 && achados[escolhido]) { abrirNoApp(achados[escolhido].simbolo); return; }
      const texto = campo.value.trim();
      if (texto) abrirNoApp(texto.toUpperCase());
    });
  }

  // --- vitrine: troca o estilo das páginas do PDF de exemplo -------------------------------
  for (const vitrine of document.querySelectorAll("[data-vitrine]")) {
    const botoes = vitrine.querySelectorAll("button[data-estilo]");
    const folhas = vitrine.querySelectorAll("img[data-pagina]");
    botoes.forEach((botao) => botao.addEventListener("click", () => {
      botoes.forEach((b) => b.setAttribute("aria-pressed", String(b === botao)));
      folhas.forEach((img) => {
        img.classList.add("trocando");
        const nova = new Image();
        nova.onload = () => { img.src = nova.src; img.classList.remove("trocando"); };
        nova.src = "/relatorio/" + botao.dataset.estilo + "-" + img.dataset.pagina + ".webp";
      });
    }));
  }

  // --- Dados: busca de tabelas pelo nome (sem JavaScript a lista inteira fica à mostra) --------
  const filtroDeTabelas = document.querySelector("[data-filtro-tabelas]");
  if (filtroDeTabelas) {
    filtroDeTabelas.hidden = false;
    const linhas = document.querySelectorAll("tr[data-tabela]");
    const blocos = document.querySelectorAll("[data-modulo-da-lista]");
    const vazio = document.querySelector("[data-filtro-vazio]");
    filtroDeTabelas.addEventListener("input", () => {
      const termo = semAcento(filtroDeTabelas.value.trim());
      linhas.forEach((linha) => { linha.hidden = !semAcento(linha.dataset.tabela).includes(termo); });
      let achou = false;
      blocos.forEach((bloco) => {
        const algum = bloco.querySelector("tr[data-tabela]:not([hidden])") !== null;
        bloco.hidden = !algum;
        achou = achou || algum;
      });
      if (vazio) vazio.hidden = achou;
    });
  }
})();
