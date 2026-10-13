// Aplica no app o tema que a pessoa escolheu (claro, escuro ou automático). Vai na página junto
// com o sol.js, montado por src/tema_do_app.py. Testado em tests/test_tema_do_app.py (pelo Node).
//
// O Streamlit só lê o tema ao carregar, de uma chave do navegador por página ("stActiveTheme-" +
// endereço da página + "-v2", com "Light" ou "Dark"). O script grava o tema certo na chave de todas
// as páginas e, se a tela aberta estiver no tema errado, recarrega uma vez só.
// Atenção: nada de "menor que" colado em letra neste arquivo nem no sol.js; o Streamlit apaga o
// script inteiro quando acha algo parecido com uma etiqueta de HTML (há teste).
(function (raiz) {
  "use strict";
  const MARCA_DA_RECARGA = "tickerlab-tema-recarregado";
  const ESCOLHA_NO_NAVEGADOR = "tickerlab-tema-escolha";
  const ESCOLHAS = ["auto", "claro", "escuro"];

  // Sem login, a sessão do Streamlit some ao recarregar e volta ao padrão: vale então a escolha
  // guardada neste navegador. Quando a escolha veio da conta ou a pessoa acabou de escolher
  // (guardada), ela manda.
  function escolhaEfetiva(escolha, guardada, noNavegador) {
    if (guardada) return escolha;
    return ESCOLHAS.includes(noNavegador) ? noNavegador : escolha;
  }

  // tema certo, valor para o Streamlit e se precisa recarregar (nunca duas vezes para o mesmo tema)
  function decidir(escolha, agora, fuso, ativo, jaRecarregouPara, sol) {
    const tema = escolha === "claro" || escolha === "escuro" ? escolha : sol.temaDoMomento(agora, fuso);
    return {
      tema,
      valorDoStreamlit: tema === "escuro" ? "Dark" : "Light",
      recarregar: ativo !== tema && jaRecarregouPara !== tema,
    };
  }

  function aplicar(escolhaDoServidor, guardada, paginas, versao) {
    const app = document.querySelector(".stApp");
    if (!app) return;
    let escolha = escolhaDoServidor;
    try {
      escolha = escolhaEfetiva(escolhaDoServidor, guardada, localStorage.getItem(ESCOLHA_NO_NAVEGADOR));
      if (guardada) localStorage.setItem(ESCOLHA_NO_NAVEGADOR, escolhaDoServidor);
    } catch (e) {}
    const ativo = getComputedStyle(app).colorScheme === "light" ? "claro" : "escuro";
    let jaRecarregou = null;
    try { jaRecarregou = sessionStorage.getItem(MARCA_DA_RECARGA); } catch (e) {}
    const sol = raiz.TickerLabSol;
    const r = decidir(escolha, new Date(), sol.fusoDoAparelho(), ativo, jaRecarregou, sol);
    try {
      for (const pagina of new Set([...paginas, location.pathname])) {
        localStorage.setItem("stActiveTheme-" + pagina + "-v" + versao, JSON.stringify(r.valorDoStreamlit));
      }
      if (r.recarregar) {
        sessionStorage.setItem(MARCA_DA_RECARGA, r.tema);
        location.reload();
      }
    } catch (e) {
      // sem acesso ao armazenamento do navegador: fica o tema que o Streamlit abriu
    }
  }

  const temaDoApp = { escolhaEfetiva, decidir, aplicar };
  if (typeof module !== "undefined" && module.exports) module.exports = temaDoApp;
  else raiz.TickerLabTemaDoApp = temaDoApp;
})(typeof window !== "undefined" ? window : globalThis);
