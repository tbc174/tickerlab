// Cada página do site: o arquivo que ela vira (os mesmos endereços de hoje), os dados do <head> e
// o conteúdo. A moldura (topo, rodapé) é a mesma para todas.
import type { ReactElement } from "react";
import {
  DADOS_DA_VITRINE,
  DADOS_DOS_APORTES,
  DADOS_DOS_JUROS,
  PaginaDosAportes,
  PaginaDosJuros,
  Vitrine,
} from "./ferramentas/paginas";
import { Aprender, DADOS as DADOS_DO_APRENDER } from "./paginas/Aprender";
import { ComoFunciona, DADOS as DADOS_DO_COMO_FUNCIONA } from "./paginas/ComoFunciona";
import { DADOS as DADOS_DO_INICIO, Inicio } from "./paginas/Inicio";
import { DADOS_DA_PRIVACIDADE, DADOS_DOS_TERMOS, Legal } from "./paginas/Legal";
import { DADOS as DADOS_DA_METODOLOGIA, Metodologia } from "./paginas/Metodologia";
import { DADOS as DADOS_DA_404, NaoEncontrada } from "./paginas/NaoEncontrada";
import { DADOS as DADOS_DAS_NOVIDADES, Novidades } from "./paginas/Novidades";
import { DADOS as DADOS_DOS_PLANOS, Precos } from "./paginas/Precos";
import { DADOS as DADOS_DO_PRODUTO, Produto } from "./paginas/Produto";
import { DADOS as DADOS_DO_SOBRE, Sobre } from "./paginas/Sobre";
import type { DadosDaPagina } from "./site/Moldura";

export interface Rota {
  arquivo: string; // "index.html", "produto.html"...
  dados: DadosDaPagina;
  conteudo: () => ReactElement;
}

export const ROTAS: Rota[] = [
  { arquivo: "index.html", dados: DADOS_DO_INICIO, conteudo: () => <Inicio /> },
  { arquivo: "produto.html", dados: DADOS_DO_PRODUTO, conteudo: () => <Produto /> },
  {
    arquivo: "como-funciona.html",
    dados: DADOS_DO_COMO_FUNCIONA,
    conteudo: () => <ComoFunciona />,
  },
  { arquivo: "aprender.html", dados: DADOS_DO_APRENDER, conteudo: () => <Aprender /> },
  { arquivo: "ferramentas.html", dados: DADOS_DA_VITRINE, conteudo: () => <Vitrine /> },
  {
    arquivo: "calculadora-de-juros-compostos.html",
    dados: DADOS_DOS_JUROS,
    conteudo: () => <PaginaDosJuros />,
  },
  {
    arquivo: "calculadora-de-aportes-e-metas.html",
    dados: DADOS_DOS_APORTES,
    conteudo: () => <PaginaDosAportes />,
  },
  { arquivo: "sobre.html", dados: DADOS_DO_SOBRE, conteudo: () => <Sobre /> },
  { arquivo: "precos.html", dados: DADOS_DOS_PLANOS, conteudo: () => <Precos /> },
  { arquivo: "metodologia.html", dados: DADOS_DA_METODOLOGIA, conteudo: () => <Metodologia /> },
  { arquivo: "novidades.html", dados: DADOS_DAS_NOVIDADES, conteudo: () => <Novidades /> },
  {
    arquivo: "termos.html",
    dados: DADOS_DOS_TERMOS,
    conteudo: () => <Legal titulo="Termos de uso" texto="termos" />,
  },
  {
    arquivo: "privacidade.html",
    dados: DADOS_DA_PRIVACIDADE,
    conteudo: () => <Legal titulo="Política de privacidade" texto="privacidade" />,
  },
  { arquivo: "404.html", dados: DADOS_DA_404, conteudo: () => <NaoEncontrada /> },
];

export function rotaDoArquivo(arquivo: string): Rota {
  const rota = ROTAS.find((r) => r.arquivo === arquivo);
  if (!rota) throw new Error(`Página sem rota: ${arquivo}`);
  return rota;
}
