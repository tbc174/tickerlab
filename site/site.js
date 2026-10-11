// gerado por scripts/gerar_site.py — busca de ativos e vitrine do Report Studio
(() => {
  "use strict";
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
})();
