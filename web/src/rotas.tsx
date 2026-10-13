// Cada página do site: o arquivo que ela vira (os mesmos endereços de hoje), os dados do <head> e
// o conteúdo. A moldura (topo, rodapé) é a mesma para todas.
import type { ReactElement } from "react";
import { Aprender, DADOS as DADOS_DO_APRENDER } from "./paginas/Aprender";
import { ComoFunciona, DADOS as DADOS_DO_COMO_FUNCIONA } from "./paginas/ComoFunciona";
import { DADOS as DADOS_DO_INICIO, Inicio } from "./paginas/Inicio";
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
  { arquivo: "sobre.html", dados: DADOS_DO_SOBRE, conteudo: () => <Sobre /> },
  { arquivo: "precos.html", dados: DADOS_DOS_PLANOS, conteudo: () => <Precos /> },
];

export function rotaDoArquivo(arquivo: string): Rota {
  const rota = ROTAS.find((r) => r.arquivo === arquivo);
  if (!rota) throw new Error(`Página sem rota: ${arquivo}`);
  return rota;
}
