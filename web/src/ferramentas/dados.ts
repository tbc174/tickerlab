// Os dados abertos das ferramentas: /dados/ferramentas.json, gerado no VPS por
// scripts/exportar_dados_das_ferramentas.py (Banco Central: PTAX, CDI, Selic, poupança, IPCA e Focus;
// Tesouro Nacional: taxas do Tesouro Direto). O HTML pronto sai sem eles (o build não depende do
// dia); no navegador, a ferramenta busca o arquivo.
import { useEffect, useState } from "react";
import type { Meses } from "./contas/inflacao";

export const ENDERECO_DOS_DADOS = "/dados/ferramentas.json";
export const DIAS_UTEIS_ATE_FICAR_VELHO = 4; // feriado prolongado cabe; uma semana parada, não

export interface Moeda {
  codigo: string;
  nome: string;
  compra: number;
  venda: number;
  data: string;
  historico?: [string, number][]; // a PTAX de venda dos últimos 12 meses (ferramentas v2)
}

export interface ExpectativaDoFocus {
  data: string; // a data da pesquisa
  anos: Record<string, number>; // "2026" → 0,0522 (mediana, em fração)
}

export interface TituloDoTesouro {
  titulo: string; // "Tesouro Prefixado", "Tesouro IPCA+", "Tesouro Selic"
  vencimento: string;
  taxa: number; // de compra, em fração ao ano (a real, no IPCA+)
}

export interface DadosDoBc {
  gerado_em: string;
  fonte: string;
  moedas?: Moeda[];
  cdi?: { ao_ano: number; data: string };
  selic_meta?: { ao_ano: number; data: string };
  poupanca?: { ao_mes: number; data: string };
  ipca?: { meses: Meses; ultimo: string };
  focus?: { ipca?: ExpectativaDoFocus; selic?: ExpectativaDoFocus };
  cdi_mensal?: { meses: Meses; ultimo: string };
  poupanca_mensal?: { meses: Meses; ultimo: string };
  tesouro?: { data: string; titulos: TituloDoTesouro[] };
}

export type Carga = { estado: "carregando" } | { estado: "indisponivel" } | { estado: "pronto"; dados: DadosDoBc };

/** Busca o arquivo uma vez; sem ele (ou com erro), a ferramenta diz que está indisponível. */
export function useDadosDoBc(): Carga {
  const [carga, setCarga] = useState<Carga>({ estado: "carregando" });
  useEffect(() => {
    let ativo = true;
    // a mesma busca dos atalhos (carregarDadosDoBc): o arquivo vem uma vez por página
    carregarDadosDoBc().then((dados) => {
      if (ativo) setCarga(dados ? { estado: "pronto", dados } : { estado: "indisponivel" });
    });
    return () => {
      ativo = false;
    };
  }, []);
  return carga;
}

// uma busca por página, dividida entre as ferramentas dela (refeita se o fetch mudar: nos testes)
let emCurso: { buscar: typeof fetch; promessa: Promise<DadosDoBc | null> } | null = null;

/** O arquivo, ou null se não veio. Nunca rejeita: sem os dados, a ferramenta segue sem os atalhos. */
export function carregarDadosDoBc(): Promise<DadosDoBc | null> {
  const buscar = globalThis.fetch;
  if (!emCurso || emCurso.buscar !== buscar) {
    const promessa = Promise.resolve()
      .then(() => buscar(ENDERECO_DOS_DADOS))
      .then((resposta) => (resposta.ok ? (resposta.json() as Promise<DadosDoBc>) : null))
      .catch(() => null);
    emCurso = { buscar, promessa };
  }
  return emCurso.promessa;
}

/** Os dados quando chegarem; até lá (ou sem eles), null. Só muda de estado quando o arquivo vem,
 * então a falha não mexe na tela. */
export function useDadosOpcionais(): DadosDoBc | null {
  const [dados, setDados] = useState<DadosDoBc | null>(null);
  useEffect(() => {
    let ativo = true;
    carregarDadosDoBc().then((vieram) => {
      if (ativo && vieram) setDados(vieram);
    });
    return () => {
      ativo = false;
    };
  }, []);
  return dados;
}

/** Dias úteis (segunda a sexta, sem feriados) depois de `data` até `hoje`. */
export function diasUteisDesde(data: string, hoje: Date): number {
  const dia = new Date(`${data}T12:00:00`);
  let uteis = 0;
  while (dia.toDateString() !== hoje.toDateString() && dia < hoje) {
    dia.setDate(dia.getDate() + 1);
    const semana = dia.getDay();
    if (semana !== 0 && semana !== 6) uteis++;
  }
  return uteis;
}

export function estaVelho(data: string, hoje: Date): boolean {
  return diasUteisDesde(data, hoje) > DIAS_UTEIS_ATE_FICAR_VELHO;
}

/** "13/10/2026". */
export function dataBrasileira(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}
