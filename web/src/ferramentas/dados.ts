// Os dados do Banco Central das ferramentas: /dados/ferramentas.json, gerado uma vez por dia no VPS
// por scripts/exportar_dados_das_ferramentas.py (PTAX, CDI, Selic, poupança e IPCA). O HTML pronto
// sai sem eles (o build não depende do dia); no navegador, a ferramenta busca o arquivo.
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
}

export interface DadosDoBc {
  gerado_em: string;
  fonte: string;
  moedas?: Moeda[];
  cdi?: { ao_ano: number; data: string };
  selic_meta?: { ao_ano: number; data: string };
  poupanca?: { ao_mes: number; data: string };
  ipca?: { meses: Meses; ultimo: string };
}

export type Carga = { estado: "carregando" } | { estado: "indisponivel" } | { estado: "pronto"; dados: DadosDoBc };

/** Busca o arquivo uma vez; sem ele (ou com erro), a ferramenta diz que está indisponível. */
export function useDadosDoBc(): Carga {
  const [carga, setCarga] = useState<Carga>({ estado: "carregando" });
  useEffect(() => {
    let ativo = true;
    fetch(ENDERECO_DOS_DADOS)
      .then((resposta) => (resposta.ok ? (resposta.json() as Promise<DadosDoBc>) : Promise.reject()))
      .then((dados) => ativo && setCarga({ estado: "pronto", dados }))
      .catch(() => ativo && setCarga({ estado: "indisponivel" }));
    return () => {
      ativo = false;
    };
  }, []);
  return carga;
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
