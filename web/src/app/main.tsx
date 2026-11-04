import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { caminhoSemONovo, desregistrarServicoDoNovo } from "./raiz";
import "./app.css";
// quem chega ao app por link de campanha (as calculadoras do site, por exemplo) também ganha o
// cookie `tl_origem`, lido no primeiro login: o mesmo script do site (publico/origem.js)
import "../../publico/origem.js";

// quem chegou pelo endereço antigo (/novo/...) vai ao mesmo caminho na raiz (src/app/raiz.ts)
const naRaiz = caminhoSemONovo(window.location);
if (naRaiz !== null) window.location.replace(naRaiz);

// o app instalável (PWA): o service worker guarda só a casca (src/app/pwa.ts); fora do build não
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  desregistrarServicoDoNovo(navigator.serviceWorker)
    .then(() => navigator.serviceWorker.register("/sw.js", { scope: "/" }))
    .catch(() => {
      // sem service worker o app funciona igual, só não abre sem internet
    });
}

const raiz = document.getElementById("raiz");
if (raiz && naRaiz === null) {
  createRoot(raiz).render(
    <StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </StrictMode>,
  );
}
