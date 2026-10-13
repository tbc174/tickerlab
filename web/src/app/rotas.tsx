// As telas do app novo: as páginas que já têm contrato na API (src/paginas.py), no mesmo endereço do
// app atual (/visao-geral vira /novo/visao-geral). Página sem tela nova ainda leva ao app atual.
import type { ReactNode } from "react";
import { type PaginaDoApp, paginasDoApp } from "../conteudo";
import { EmConstrucao } from "./telas/EmConstrucao";
import { VisaoGeral } from "./telas/VisaoGeral";

export const TELAS_DO_APP: PaginaDoApp[] = paginasDoApp.filter((p) => p.contrato !== null);

// as telas já feitas em React, pela chave da página
const TELAS_PRONTAS: Record<string, (pagina: PaginaDoApp) => ReactNode> = {
  visao_geral: (pagina) => <VisaoGeral pagina={pagina} />,
};

export function telaDa(pagina: PaginaDoApp): ReactNode {
  const tela = TELAS_PRONTAS[pagina.chave];
  return tela ? tela(pagina) : <EmConstrucao pagina={pagina} />;
}
