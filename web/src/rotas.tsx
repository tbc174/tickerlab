// Cada página do site: o arquivo que ela vira (os mesmos endereços de hoje), os dados do <head> e
// o conteúdo. A moldura (topo, rodapé) é a mesma para todas.
import type { ReactElement } from "react";
import {
  DADOS_DA_VITRINE,
  DADOS_DOS_APORTES,
  DADOS_DOS_CUSTOS,
  DADOS_DO_CONVERSOR,
  DADOS_DO_DARF,
  DADOS_DO_JURO_REAL,
  DADOS_DA_INFLACAO,
  DADOS_DA_RENDA_FIXA,
  DADOS_DA_RENDA,
  DADOS_DA_SORTE,
  DADOS_DO_QUANTO_DARIA,
  DADOS_DO_PRECO_MEDIO,
  DADOS_DO_FINANCIAMENTO,
  DADOS_DO_FUNDO,
  DADOS_DOS_JUROS,
  PaginaDaRenda,
  PaginaDaSorte,
  PaginaDosAportes,
  PaginaDosCustos,
  PaginaDaInflacao,
  PaginaDaRendaFixa,
  PaginaDoConversor,
  PaginaDoDarf,
  PaginaDoJuroReal,
  PaginaDoQuantoDaria,
  PaginaDoPrecoMedio,
  PaginaDoFinanciamento,
  PaginaDoFundo,
  PaginaDosJuros,
  Vitrine,
} from "./ferramentas/paginas";
import { Aprender, DADOS as DADOS_DO_APRENDER } from "./paginas/Aprender";
import { ComoFunciona, DADOS as DADOS_DO_COMO_FUNCIONA } from "./paginas/ComoFunciona";
import { DADOS as DADOS_DOS_DADOS, Dados } from "./paginas/Dados";
import { DADOS as DADOS_DO_INICIO, Inicio } from "./paginas/Inicio";
import { DADOS_DA_PRIVACIDADE, DADOS_DOS_TERMOS, Legal } from "./paginas/Legal";
import { DADOS as DADOS_DA_METODOLOGIA, Metodologia } from "./paginas/Metodologia";
import { DADOS as DADOS_DA_404, NaoEncontrada } from "./paginas/NaoEncontrada";
import { DADOS as DADOS_DAS_NOVIDADES, Novidades } from "./paginas/Novidades";
import { DADOS as DADOS_DOS_PLANOS, Precos } from "./paginas/Precos";
import { DADOS as DADOS_DO_PRODUTO, Produto } from "./paginas/Produto";
import { DADOS as DADOS_DO_RELATORIO, RelatorioExemplo } from "./paginas/RelatorioExemplo";
import { DADOS as DADOS_DOS_RELATORIOS, Relatorios } from "./paginas/Relatorios";
import {
  DADOS as DADOS_DO_SEMANAL_ELETRICAS,
  RelatorioSemanalEletricas,
} from "./paginas/RelatorioSemanalEletricas";
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
  { arquivo: "dados.html", dados: DADOS_DOS_DADOS, conteudo: () => <Dados /> },
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
  {
    arquivo: "custo-das-taxas-e-da-queda.html",
    dados: DADOS_DOS_CUSTOS,
    conteudo: () => <PaginaDosCustos />,
  },
  {
    arquivo: "calculadora-viver-de-renda.html",
    dados: DADOS_DA_RENDA,
    conteudo: () => <PaginaDaRenda />,
  },
  { arquivo: "sorte-em-serie.html", dados: DADOS_DA_SORTE, conteudo: () => <PaginaDaSorte /> },
  { arquivo: "calculadora-de-darf.html", dados: DADOS_DO_DARF, conteudo: () => <PaginaDoDarf /> },
  { arquivo: "conversor-de-moedas.html", dados: DADOS_DO_CONVERSOR, conteudo: () => <PaginaDoConversor /> },
  {
    arquivo: "calculadora-de-renda-fixa.html",
    dados: DADOS_DA_RENDA_FIXA,
    conteudo: () => <PaginaDaRendaFixa />,
  },
  {
    arquivo: "calculadora-de-juro-real.html",
    dados: DADOS_DO_JURO_REAL,
    conteudo: () => <PaginaDoJuroReal />,
  },
  {
    arquivo: "calculadora-de-correcao-pela-inflacao.html",
    dados: DADOS_DA_INFLACAO,
    conteudo: () => <PaginaDaInflacao />,
  },
  { arquivo: "quanto-daria.html", dados: DADOS_DO_QUANTO_DARIA, conteudo: () => <PaginaDoQuantoDaria /> },
  {
    arquivo: "calculadora-de-preco-medio.html",
    dados: DADOS_DO_PRECO_MEDIO,
    conteudo: () => <PaginaDoPrecoMedio />,
  },
  {
    arquivo: "simulador-de-financiamento.html",
    dados: DADOS_DO_FINANCIAMENTO,
    conteudo: () => <PaginaDoFinanciamento />,
  },
  { arquivo: "fundo-ou-cdb.html", dados: DADOS_DO_FUNDO, conteudo: () => <PaginaDoFundo /> },
  { arquivo: "sobre.html", dados: DADOS_DO_SOBRE, conteudo: () => <Sobre /> },
  { arquivo: "precos.html", dados: DADOS_DOS_PLANOS, conteudo: () => <Precos /> },
  { arquivo: "metodologia.html", dados: DADOS_DA_METODOLOGIA, conteudo: () => <Metodologia /> },
  { arquivo: "relatorios.html", dados: DADOS_DOS_RELATORIOS, conteudo: () => <Relatorios /> },
  {
    arquivo: "relatorio-de-exemplo.html",
    dados: DADOS_DO_RELATORIO,
    conteudo: () => <RelatorioExemplo />,
  },
  {
    arquivo: "relatorio-de-setor-eletricas.html",
    dados: DADOS_DO_SEMANAL_ELETRICAS,
    conteudo: () => <RelatorioSemanalEletricas />,
  },
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
