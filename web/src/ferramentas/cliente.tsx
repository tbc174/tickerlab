// O ferramentas.js: no navegador, troca o HTML pronto de cada ferramenta pela versão que responde
// aos campos. Só as páginas de ferramentas carregam este script (vite.ferramentas.config.ts).
// Não usa hydrateRoot: o HTML do site sai de renderToStaticMarkup, sem as marcas que o React usa
// para religar; montar por cima dá o mesmo desenho (o estado começa nos mesmos valores de exemplo).
import { createRoot } from "react-dom/client";
import { FERRAMENTAS, type NomeDaFerramenta } from "./registro";

/** Liga as ferramentas que estiverem em `raiz`; devolve quantas ligou. */
export function ligarFerramentas(raiz: ParentNode = document): number {
  let ligadas = 0;
  for (const lugar of raiz.querySelectorAll<HTMLElement>("[data-ferramenta]")) {
    const nome = lugar.dataset.ferramenta as NomeDaFerramenta;
    const Componente = FERRAMENTAS[nome];
    if (!Componente || lugar.dataset.ligada) continue;
    lugar.dataset.ligada = "sim";
    createRoot(lugar).render(<Componente />);
    ligadas++;
  }
  return ligadas;
}

if (typeof document !== "undefined" && !import.meta.env?.VITEST) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => ligarFerramentas());
  } else {
    ligarFerramentas();
  }
}
