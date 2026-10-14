import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import "./app.css";

// o app instalável (PWA): o service worker guarda só a casca (src/app/pwa.ts); fora do build não
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  navigator.serviceWorker.register("/novo/sw.js", { scope: "/novo/" }).catch(() => {
    // sem service worker o app funciona igual, só não abre sem internet
  });
}

const raiz = document.getElementById("raiz");
if (raiz) {
  createRoot(raiz).render(
    <StrictMode>
      <BrowserRouter basename="/novo">
        <App />
      </BrowserRouter>
    </StrictMode>,
  );
}
