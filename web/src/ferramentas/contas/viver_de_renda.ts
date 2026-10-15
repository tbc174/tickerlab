// Viver de renda: cópia em TypeScript de src/ferramentas/viver_de_renda.py (a referência).
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.
// Tudo em dinheiro de hoje: a taxa é real (acima da inflação); a retirada sai no começo do mês.
import { taxaEquivalente } from "./juros";

export const ANOS_MAXIMOS = 100;
const MESES_MAXIMOS = ANOS_MAXIMOS * 12;
const RETIRADA_DA_REGRA_DOS_4 = 0.04;
const FOLGA = 1e-9; // o último mês fecha com o arredondamento da conta, não com um centavo a menos

function conferir(rendaMensal: number, taxaReal: number): void {
  if (rendaMensal < 0) throw new RangeError("A renda mensal não pode ser negativa.");
  if (taxaReal <= -1) throw new RangeError("O rendimento precisa ser maior que -100% ao ano.");
}

/** O patrimônio que paga `rendaMensal` para sempre (`anos` null) ou por `anos` anos. */
export function patrimonioNecessario(rendaMensal: number, taxaReal: number, anos: number | null): number {
  conferir(rendaMensal, taxaReal);
  const i = taxaEquivalente(taxaReal, 12, 1);
  if (anos === null) {
    if (i <= 0) throw new RangeError("Só com os juros não dá: sem rendimento, o dinheiro acaba.");
    return (rendaMensal * (1 + i)) / i;
  }
  if (anos < 1 || anos > ANOS_MAXIMOS) {
    throw new RangeError(`O prazo precisa estar entre 1 e ${ANOS_MAXIMOS} anos.`);
  }
  const meses = anos * 12;
  if (i === 0) return rendaMensal * meses;
  // anuidade com a retirada no começo do mês: renda × (1 − (1 + i)^−n) / i × (1 + i)
  return ((rendaMensal * -Math.expm1(-meses * Math.log1p(i))) / i) * (1 + i);
}

/** Quantos meses de retirada o patrimônio paga; null se passa de 100 anos. */
export function duracaoEmMeses(patrimonio: number, rendaMensal: number, retornosAnuais: number[]): number | null {
  if (retornosAnuais.length === 0) throw new RangeError("Informe pelo menos um retorno anual.");
  if (rendaMensal <= 0) throw new RangeError("A retirada mensal precisa ser maior que zero.");
  let saldo = patrimonio;
  for (let mes = 0; mes < MESES_MAXIMOS; mes++) {
    if (saldo < rendaMensal * (1 - FOLGA)) return mes;
    const ano = Math.min(Math.floor(mes / 12), retornosAnuais.length - 1);
    const i = taxaEquivalente(retornosAnuais[ano], 12, 1);
    saldo = (saldo - rendaMensal) * (1 + i);
  }
  return null;
}

/** O saldo no começo de cada mês, do mês 0 até o mês em que não dá mais para tirar a renda
 * inteira (o último saldo é o que sobrou) ou até `horizonte` meses. A mesma conta de duracaoEmMeses. */
export function trajetoria(
  patrimonio: number,
  rendaMensal: number,
  retornosAnuais: number[],
  horizonte: number,
): number[] {
  if (horizonte < 1 || horizonte > MESES_MAXIMOS) {
    throw new RangeError(`O horizonte precisa estar entre 1 e ${MESES_MAXIMOS} meses.`);
  }
  if (retornosAnuais.length === 0) throw new RangeError("Informe pelo menos um retorno anual.");
  if (rendaMensal <= 0) throw new RangeError("A retirada mensal precisa ser maior que zero.");
  const saldos = [patrimonio];
  for (let mes = 0; mes < horizonte; mes++) {
    const saldo = saldos[saldos.length - 1];
    if (saldo < rendaMensal * (1 - FOLGA)) break;
    const ano = Math.min(Math.floor(mes / 12), retornosAnuais.length - 1);
    const i = taxaEquivalente(retornosAnuais[ano], 12, 1);
    saldos.push((saldo - rendaMensal) * (1 + i));
  }
  return saldos;
}

/** A renda mensal da "regra dos 4%": 4% do patrimônio do começo por ano, dividido em 12. */
export function rendaDaRegraDos4(patrimonio: number): number {
  return (patrimonio * RETIRADA_DA_REGRA_DOS_4) / 12;
}
