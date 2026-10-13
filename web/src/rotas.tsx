// Cada página do site: o arquivo que ela vira (os mesmos endereços de hoje) e o componente.
import type { ReactElement } from "react";
import { Inicio } from "./paginas/Inicio";

export interface Rota {
  arquivo: string; // "index.html", "produto.html"...
  titulo: string;
  descricao: string;
  pagina: () => ReactElement;
}

export const ROTAS: Rota[] = [
  {
    arquivo: "index.html",
    titulo: "TickerLab",
    descricao: "Plataforma de inteligência financeira.",
    pagina: () => <Inicio />,
  },
];

export function rotaDoArquivo(arquivo: string): Rota {
  const rota = ROTAS.find((r) => r.arquivo === arquivo);
  if (!rota) throw new Error(`Página sem rota: ${arquivo}`);
  return rota;
}
