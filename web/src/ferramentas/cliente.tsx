// O ferramentas.js: no navegador, troca o HTML pronto de cada ferramenta pela versão que responde
// aos campos. Só as páginas de ferramentas carregam este script (vite.ferramentas.config.ts).
// Não usa hydrateRoot: o HTML do site sai de renderToStaticMarkup, sem as marcas que o React usa
// para religar; montar por cima dá o mesmo desenho (o estado começa nos mesmos valores de exemplo).
import { BuscaDaBase } from "../site/BuscaDaBase";
import { ConsultaDaBase, mostrarSeAConsultaResponde } from "../site/ConsultaDaBase";
import { ligarPregao } from "../site/PregaoAoVivo";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { PrefixoDoId } from "../idUnico";
import { ligarContinuacoes } from "./continuar";
import { FERRAMENTAS, type NomeDaFerramenta } from "./registro";

/** Liga as ferramentas que estiverem em `raiz`; devolve quantas ligou. */
export function ligarFerramentas(raiz: ParentNode = document): number {
  let ligadas = 0;
  for (const lugar of raiz.querySelectorAll<HTMLElement>("[data-ferramenta]")) {
    const nome = lugar.dataset.ferramenta as NomeDaFerramenta;
    const Componente = FERRAMENTAS[nome];
    if (!Componente || lugar.dataset.ligada) continue;
    lugar.dataset.ligada = "sim";
    ligadas++;
    createRoot(lugar).render(
      <PrefixoDoId.Provider value={`f${ligadas}-`}>
        <Componente />
      </PrefixoDoId.Provider>,
    );
  }
  ligadas += montar(raiz, "[data-busca-base]", <BuscaDaBase />);
  ligadas += montar(raiz, "[data-consulta-base]", <ConsultaDaBase />);
  return ligadas;
}

/** Monta `arvore` em cada lugar de `seletor` ainda não ligado; devolve quantos ligou. */
function montar(raiz: ParentNode, seletor: string, arvore: ReactNode): number {
  let ligados = 0;
  for (const lugar of raiz.querySelectorAll<HTMLElement>(seletor)) {
    if (lugar.dataset.ligada) continue;
    lugar.dataset.ligada = "sim";
    createRoot(lugar).render(arvore);
    ligados++;
  }
  return ligados;
}

if (typeof document !== "undefined" && !import.meta.env?.VITEST) {
  ligarContinuacoes(document);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => ligarFerramentas());
  } else {
    ligarFerramentas();
  }
  void ligarPregao(document);
  void mostrarSeAConsultaResponde(document);
}
