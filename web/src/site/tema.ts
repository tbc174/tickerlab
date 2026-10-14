// O tema do TickerLab (Claro, Escuro, Automático pelo sol): o script do <head> e os ícones do menu.
// Sem Node: serve ao site (HTML pronto) e ao app em React (no navegador).

// Roda no <head>, antes de pintar a página (o sol.js vem antes, sem defer): decide o tema pela
// escolha guardada; quem nunca escolheu fica no Automático (claro de dia, escuro à noite, pelo fuso
// do aparelho). Também avisa o CSS que há JavaScript.
export const TEMA_SALVO =
  '<script>(function () { var raiz = document.documentElement, escolha = "auto";' +
  ' raiz.classList.add("com-js");' +
  ' try { escolha = localStorage.getItem("tema") || "auto"; } catch (e) {}' +
  " var sol = window.TickerLabSol;" +
  ' var tema = escolha !== "auto" ? escolha' +
  ' : sol ? sol.temaDoMomento(new Date(), sol.fusoDoAparelho()) : "claro";' +
  " raiz.dataset.escolha = escolha;" +
  ' if (tema === "escuro") raiz.dataset.tema = "escuro"; })();</script>';

// ícones do Material ("light_mode", "dark_mode" e "contrast"); o botão mostra o da escolha atual
const ICONE_SOL =
  "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM2 13h2a1 1 0 0 0 0-2H2a1 1 0 0 0 0 2zm18 0h2a1" +
  " 1 0 0 0 0-2h-2a1 1 0 0 0 0 2zM11 2v2a1 1 0 0 0 2 0V2a1 1 0 0 0-2 0zm0 18v2a1 1 0 0 0 2 0v-2a1" +
  " 1 0 0 0-2 0zM5.99 4.58a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41L5.99 4.58zm12.37" +
  " 12.37a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41l-1.06-1.06zm1.06-10.96a1 1 0 0 0-1.41" +
  "-1.41l-1.06 1.06a1 1 0 0 0 1.41 1.41l1.06-1.06zM7.05 18.36a1 1 0 0 0-1.41-1.41l-1.06 1.06a1 1" +
  " 0 0 0 1.41 1.41l1.06-1.06z";
const ICONE_LUA =
  "M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 0 1-4.4 2.26 5.4 5.4 0 0 1" +
  "-3.14-9.8c-.44-.06-.9-.1-1.36-.1z";
const ICONE_AUTOMATICO =
  "M12 22c5.52 0 10-4.48 10-10S17.52 2 12 2 2 6.48 2 12s4.48 10 10 10zm1-17.93c3.94.49" +
  " 7 3.85 7 7.93s-3.06 7.44-7 7.93V4.07z";

// (valor guardado, nome, ícone, explicação curta)
export const OPCOES_DO_TEMA: [string, string, string, string][] = [
  ["claro", "Claro", ICONE_SOL, ""],
  ["escuro", "Escuro", ICONE_LUA, ""],
  ["auto", "Automático", ICONE_AUTOMATICO, "Claro de dia, escuro à noite"],
];
