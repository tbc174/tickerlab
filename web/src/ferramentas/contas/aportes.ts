// Aportes e metas: cópia em TypeScript de src/ferramentas/aportes.py (a referência).
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.
// Taxa ao mês, composta; o aporte entra no fim do mês (padrão) ou no começo (`noInicio`).
// Com `reajusteAnual`, o aporte sobe essa fração a cada 12 meses (do 13º mês em diante).
import { PRAZO_MAXIMO } from "./juros";

/** Um mês: quanto saiu do bolso até ele (com o valor inicial), os juros e o saldo. */
export interface Linha {
  mes: number;
  aportado: number;
  juros: number;
  saldo: number;
}

function conferir(inicial: number, aporte: number, taxa: number, meses: number): void {
  if (inicial < 0) throw new RangeError("O valor inicial não pode ser negativo.");
  if (aporte < 0) throw new RangeError("O aporte mensal não pode ser negativo.");
  if (taxa <= -1) throw new RangeError("A taxa precisa ser maior que -100%.");
  if (meses < 0 || meses > PRAZO_MAXIMO) {
    throw new RangeError(`O prazo precisa estar entre 0 e ${PRAZO_MAXIMO} meses.`);
  }
}

/** Quanto R$ 1 aportado por mês vira em `meses` meses. */
function fatorDosAportes(taxa: number, meses: number, noInicio: boolean): number {
  if (taxa === 0) return meses;
  // ((1 + taxa) ** meses - 1) / taxa, sem perder os dígitos quando a taxa é quase zero
  const fator = Math.expm1(meses * Math.log1p(taxa)) / taxa;
  return noInicio ? fator * (1 + taxa) : fator;
}

/** O aporte do `mes` (1, 2, ...): o primeiro, reajustado uma vez a cada 12 meses. */
export function aporteDoMes(aporte: number, mes: number, reajusteAnual: number): number {
  return aporte * (1 + reajusteAnual) ** Math.floor((mes - 1) / 12);
}

function conferirReajuste(reajusteAnual: number): void {
  if (reajusteAnual <= -1) throw new RangeError("O reajuste precisa ser maior que -100%.");
}

/** O saldo depois de `meses` meses. */
export function valorFuturo(
  inicial: number,
  aporte: number,
  taxa: number,
  meses: number,
  noInicio = false,
  reajusteAnual = 0,
): number {
  conferir(inicial, aporte, taxa, meses);
  conferirReajuste(reajusteAnual);
  if (reajusteAnual === 0) {
    return inicial * (1 + taxa) ** meses + aporte * fatorDosAportes(taxa, meses, noInicio);
  }
  let saldo = inicial;
  for (let mes = 1; mes <= meses; mes++) {
    saldo = proximoSaldo(saldo, aporteDoMes(aporte, mes, reajusteAnual), taxa, noInicio);
  }
  return saldo;
}

/** O primeiro aporte mensal para chegar a `meta` em `meses` meses (0 se o valor inicial já
 * basta). O saldo cresce em linha reta com o aporte: basta dividir pelo que R$ 1 vira. */
export function aporteParaMeta(
  meta: number,
  inicial: number,
  taxa: number,
  meses: number,
  noInicio = false,
  reajusteAnual = 0,
): number {
  conferir(inicial, 0, taxa, meses);
  if (meta < 0) throw new RangeError("A meta não pode ser negativa.");
  if (meses === 0) throw new RangeError("O prazo precisa ser de pelo menos 1 mês.");
  const falta = meta - inicial * (1 + taxa) ** meses;
  return Math.max(falta / valorFuturo(0, 1, taxa, meses, noInicio, reajusteAnual), 0);
}

function proximoSaldo(saldo: number, aporte: number, taxa: number, noInicio: boolean): number {
  return noInicio ? (saldo + aporte) * (1 + taxa) : saldo * (1 + taxa) + aporte;
}

/** Quantos meses até o saldo chegar a `meta`; null se não chega em PRAZO_MAXIMO meses. */
export function mesesAteMeta(
  meta: number,
  inicial: number,
  aporte: number,
  taxa: number,
  noInicio = false,
  reajusteAnual = 0,
): number | null {
  conferir(inicial, aporte, taxa, 0);
  conferirReajuste(reajusteAnual);
  let saldo = inicial;
  for (let mes = 0; mes <= PRAZO_MAXIMO; mes++) {
    if (saldo >= meta) return mes;
    saldo = proximoSaldo(saldo, aporteDoMes(aporte, mes + 1, reajusteAnual), taxa, noInicio);
  }
  return null;
}

/** A tabela mês a mês, do mês 0 (só o valor inicial) ao último. */
export function evolucao(
  inicial: number,
  aporte: number,
  taxa: number,
  meses: number,
  noInicio = false,
  reajusteAnual = 0,
): Linha[] {
  conferir(inicial, aporte, taxa, meses);
  conferirReajuste(reajusteAnual);
  const linhas: Linha[] = [{ mes: 0, aportado: inicial, juros: 0, saldo: inicial }];
  for (let mes = 1; mes <= meses; mes++) {
    const anterior = linhas[linhas.length - 1];
    const doMes = aporteDoMes(aporte, mes, reajusteAnual);
    const saldo = proximoSaldo(anterior.saldo, doMes, taxa, noInicio);
    const aportado = anterior.aportado + doMes;
    linhas.push({ mes, aportado, juros: saldo - aportado, saldo });
  }
  return linhas;
}

/** O primeiro mês em que os juros do mês rendem pelo menos o aporte daquele mês; null se não
 * acontece no prazo. */
export function mesDaVirada(
  inicial: number,
  aporte: number,
  taxa: number,
  meses: number,
  noInicio = false,
  reajusteAnual = 0,
): number | null {
  const linhas = evolucao(inicial, aporte, taxa, meses, noInicio, reajusteAnual);
  for (let i = 1; i < linhas.length; i++) {
    const doMes = linhas[i].aportado - linhas[i - 1].aportado;
    const jurosDoMes = linhas[i].juros - linhas[i - 1].juros;
    if (doMes > 0 && jurosDoMes >= doMes) return linhas[i].mes;
  }
  return null;
}
