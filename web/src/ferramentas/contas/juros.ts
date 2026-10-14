// Juros simples e compostos: cópia em TypeScript de src/ferramentas/juros.py (a referência).
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.
// Taxas são frações (0.01 = 1%) por período; entrada inválida lança RangeError.
import { aliquotaDaRendaFixa } from "./renda_fixa";

export const PRAZO_MAXIMO = 1200; // períodos: 100 anos em meses
export type Unidade = "mes" | "ano";

/** Um período da evolução: o juro dele, o acumulado até ele e o montante no fim dele. */
export interface Linha {
  periodo: number;
  juros_no_periodo: number;
  juros_acumulados: number;
  montante: number;
}

function conferir(capital: number, taxa: number, periodos: number): void {
  if (capital < 0) throw new RangeError("O capital não pode ser negativo.");
  if (taxa <= -1) throw new RangeError("A taxa precisa ser maior que -100%.");
  if (periodos < 0 || periodos > PRAZO_MAXIMO) {
    throw new RangeError(`O prazo precisa estar entre 0 e ${PRAZO_MAXIMO} períodos.`);
  }
}

/** O valor no fim de `periodos` períodos, com a `taxa` de cada período. */
export function montante(capital: number, taxa: number, periodos: number, composto = true): number {
  conferir(capital, taxa, periodos);
  return composto ? capital * (1 + taxa) ** periodos : capital * (1 + taxa * periodos);
}

/** A tabela período a período, do 0 (só o capital) ao último. */
export function evolucao(capital: number, taxa: number, periodos: number, composto = true): Linha[] {
  conferir(capital, taxa, periodos);
  const linhas: Linha[] = [{ periodo: 0, juros_no_periodo: 0, juros_acumulados: 0, montante: capital }];
  for (let periodo = 1; periodo <= periodos; periodo++) {
    const valor = montante(capital, taxa, periodo, composto);
    linhas.push({
      periodo,
      juros_no_periodo: valor - linhas[linhas.length - 1].montante,
      juros_acumulados: valor - capital,
      montante: valor,
    });
  }
  return linhas;
}

/** A taxa composta de um prazo de `paraMeses` equivalente a `taxa` em `deMeses`. */
export function taxaEquivalente(taxa: number, deMeses: number, paraMeses: number): number {
  if (taxa <= -1) throw new RangeError("A taxa precisa ser maior que -100%.");
  if (deMeses <= 0 || paraMeses <= 0) {
    throw new RangeError("Os prazos da taxa precisam ser maiores que zero.");
  }
  return (1 + taxa) ** (paraMeses / deMeses) - 1;
}

/** A taxa ao mês, a partir de uma taxa "ao mês" ou "ao ano". */
export function taxaPorMes(taxa: number, unidade: Unidade): number {
  if (unidade === "mes") return taxa;
  if (unidade === "ano") return taxaEquivalente(taxa, 12, 1);
  throw new RangeError('A unidade da taxa precisa ser "mes" ou "ano".');
}

const DIAS_POR_ANO = 365;

/** Quanto `valor`, recebido daqui a `meses`, compra em dinheiro de hoje (descontada a inflação). */
export function emReaisDeHoje(valor: number, inflacaoAoAno: number, meses: number): number {
  if (inflacaoAoAno <= -1) throw new RangeError("A inflação precisa ser maior que -100%.");
  return valor / (1 + inflacaoAoAno) ** (meses / 12);
}

/** O montante depois do IR da tabela regressiva da renda fixa, sobre o ganho. Os meses viram dias
 * corridos (365/12 por mês): 6 meses são ~183 dias, já na faixa de 20%. */
export function liquidoDeIr(capital: number, montanteBruto: number, meses: number): number {
  const ganho = montanteBruto - capital;
  if (meses < 1 || ganho <= 0) return montanteBruto;
  return montanteBruto - ganho * aliquotaDaRendaFixa(Math.round((meses * DIAS_POR_ANO) / 12));
}
