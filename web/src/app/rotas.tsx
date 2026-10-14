// As telas do app novo: as páginas que já têm contrato na API (src/paginas.py), no mesmo endereço do
// app atual (/visao-geral vira /novo/visao-geral). Página sem tela nova ainda leva ao app atual.
import type { ReactNode } from "react";
import { type PaginaDoApp, paginasDoApp } from "../conteudo";
import { Backtest } from "./telas/Backtest";
import { Comparar } from "./telas/Comparar";
import { EmConstrucao } from "./telas/EmConstrucao";
import { JurosEInflacao } from "./telas/JurosEInflacao";
import { LinhaDoTempo } from "./telas/LinhaDoTempo";
import { RetornoMensal } from "./telas/RetornoMensal";
import { Risco } from "./telas/Risco";
import { VisaoGeral } from "./telas/VisaoGeral";

export const TELAS_DO_APP: PaginaDoApp[] = paginasDoApp.filter((p) => p.contrato !== null);

// as telas já feitas em React, pela chave da página
const TELAS_PRONTAS: Record<string, (pagina: PaginaDoApp) => ReactNode> = {
  visao_geral: (pagina) => <VisaoGeral pagina={pagina} />,
  juros_e_inflacao: (pagina) => <JurosEInflacao pagina={pagina} />,
  linha_do_tempo: (pagina) => <LinhaDoTempo pagina={pagina} />,
  risco: (pagina) => <Risco pagina={pagina} />,
  retorno_mensal: (pagina) => <RetornoMensal pagina={pagina} />,
  comparar: (pagina) => <Comparar pagina={pagina} />,
  backtest: (pagina) => <Backtest pagina={pagina} />,
};

/** A página já tem tela em React? (Sem tela, leva à mesma página no app atual.) */
export const temTelaPronta = (chave: string) => chave in TELAS_PRONTAS;

export function telaDa(pagina: PaginaDoApp): ReactNode {
  const tela = TELAS_PRONTAS[pagina.chave];
  return tela ? tela(pagina) : <EmConstrucao pagina={pagina} />;
}
