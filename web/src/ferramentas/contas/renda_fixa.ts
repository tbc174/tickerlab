// Renda fixa com IR: cópia em TypeScript de src/ferramentas/renda_fixa.py (a referência).
// A tabela regressiva vem de src/regras_de_imposto.py pelo conteudo/regras_de_imposto.json.
import { regrasDeImposto } from "../../conteudo";

const DIAS_UTEIS_POR_ANO = 252;
const DIAS_POR_ANO = 365;
const DIAS_DO_ANIVERSARIO = 30;
export const DIAS_MAXIMOS = 3650;

export interface Opcao {
  nome: string;
  bruto: number;
  aliquota: number;
  imposto: number;
  liquido: number;
}

/** A alíquota da tabela regressiva para `dias` dias corridos. */
export function aliquotaDaRendaFixa(dias: number): number {
  if (dias < 1) throw new RangeError("O prazo da aplicação precisa ser de pelo menos 1 dia.");
  const faixa = regrasDeImposto.renda_fixa.find((f) => f.ate_dias === null || dias <= f.ate_dias);
  if (!faixa) throw new Error("a última faixa da tabela vale para qualquer prazo");
  return faixa.aliquota;
}

const diasUteis = (dias: number) => (dias * DIAS_UTEIS_POR_ANO) / DIAS_POR_ANO;

function peloCdi(valor: number, dias: number, cdiAoAno: number, percentual: number): number {
  const diaria = ((1 + cdiAoAno) ** (1 / DIAS_UTEIS_POR_ANO) - 1) * percentual;
  return valor * (1 + diaria) ** diasUteis(dias);
}

function comIr(nome: string, valor: number, bruto: number, dias: number): Opcao {
  const aliquota = aliquotaDaRendaFixa(dias);
  const imposto = Math.max(bruto - valor, 0) * aliquota;
  return { nome, bruto, aliquota, imposto, liquido: bruto - imposto };
}

const isento = (nome: string, bruto: number): Opcao => ({ nome, bruto, aliquota: 0, imposto: 0, liquido: bruto });

/** As quatro opções pelo mesmo `valor` e `dias` corridos (percentuais: 1.1 = 110% do CDI). */
export function comparar(
  valor: number,
  dias: number,
  cdiAoAno: number,
  percentualDoCdb: number,
  percentualDaLci: number,
  poupancaAoMes: number,
): Opcao[] {
  if (valor < 0) throw new RangeError("O valor aplicado não pode ser negativo.");
  if (dias < 1 || dias > DIAS_MAXIMOS) throw new RangeError(`O prazo precisa estar entre 1 e ${DIAS_MAXIMOS} dias.`);
  if (percentualDoCdb < 0 || percentualDaLci < 0) throw new RangeError("O percentual do CDI não pode ser negativo.");
  const aniversarios = Math.floor(dias / DIAS_DO_ANIVERSARIO);
  return [
    comIr("CDB", valor, peloCdi(valor, dias, cdiAoAno, percentualDoCdb), dias),
    isento("LCI ou LCA", peloCdi(valor, dias, cdiAoAno, percentualDaLci)),
    comIr("Tesouro Selic", valor, peloCdi(valor, dias, cdiAoAno, 1), dias),
    isento("Poupança", valor * (1 + poupancaAoMes) ** aniversarios),
  ];
}
