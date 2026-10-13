// Cada página do site: o arquivo que ela vira (os mesmos endereços de hoje), os dados do <head> e
// o conteúdo. A moldura (topo, rodapé) é a mesma para todas.
import type { ReactElement } from "react";
import type { DadosDaPagina } from "./site/Moldura";
import { DADOS as DADOS_DO_INICIO, Inicio } from "./paginas/Inicio";

export interface Rota {
  arquivo: string; // "index.html", "produto.html"...
  dados: DadosDaPagina;
  conteudo: () => ReactElement;
}

export const ROTAS: Rota[] = [{ arquivo: "index.html", dados: DADOS_DO_INICIO, conteudo: () => <Inicio /> }];

export function rotaDoArquivo(arquivo: string): Rota {
  const rota = ROTAS.find((r) => r.arquivo === arquivo);
  if (!rota) throw new Error(`Página sem rota: ${arquivo}`);
  return rota;
}
