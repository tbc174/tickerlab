// Financiamento SAC e Price: cópia em TypeScript de src/ferramentas/financiamento.py (a referência).
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.
// SAC: amortização fixa e parcela que cai; Price: parcela fixa. Uma amortização extra opcional reduz
// o prazo ou a parcela.

export const SISTEMAS = ["sac", "price"] as const;
export const MODOS_DA_EXTRA = ["prazo", "parcela"] as const;
export const PRAZO_MAXIMO = 600;
const QUASE_ZERO = 1e-6;

export interface Linha {
  mes: number;
  parcela: number;
  juros: number;
  amortizacao: number;
  extra: number;
  saldo: number;
}

/** A parcela fixa que paga `valor` em `meses` meses à `taxa` ao mês. */
export function parcelaPrice(valor: number, taxa: number, meses: number): number {
  if (taxa === 0) return valor / meses;
  // 1 − (1 + taxa)^−meses sem perder os dígitos quando a taxa é quase zero
  return (valor * taxa) / -Math.expm1(-meses * Math.log1p(taxa));
}

function conferir(sistema: string, valor: number, taxa: number, meses: number, modo: string): void {
  if (!(SISTEMAS as readonly string[]).includes(sistema)) throw new RangeError(`Use um destes sistemas: ${SISTEMAS.join(", ")}.`);
  if (valor <= 0) throw new RangeError("O valor financiado precisa ser maior que zero.");
  if (taxa < 0 || taxa >= 1) throw new RangeError("A taxa ao mês precisa estar entre 0% e 100%.");
  if (meses < 1 || meses > PRAZO_MAXIMO) throw new RangeError(`O prazo precisa estar entre 1 e ${PRAZO_MAXIMO} meses.`);
  if (!(MODOS_DA_EXTRA as readonly string[]).includes(modo)) throw new RangeError("A amortização extra reduz o prazo ou a parcela.");
}

/** O financiamento mês a mês, até o saldo zerar. */
export function tabela(
  sistema: string,
  valor: number,
  taxa: number,
  meses: number,
  extraMes = 0,
  extraValor = 0,
  extraModo = "prazo",
): Linha[] {
  conferir(sistema, valor, taxa, meses, extraModo);
  let saldo = valor;
  let amortizacaoDoSac = valor / meses;
  let parcelaFixa = parcelaPrice(valor, taxa, meses);
  const linhas: Linha[] = [];
  for (let mes = 1; mes <= meses; mes++) {
    const juros = saldo * taxa;
    let amortizacao: number;
    let parcela: number;
    if (sistema === "sac") {
      amortizacao = Math.min(amortizacaoDoSac, saldo);
      parcela = amortizacao + juros;
    } else {
      parcela = Math.min(parcelaFixa, saldo + juros);
      amortizacao = parcela - juros;
    }
    if (mes === meses) {
      // quita o que sobrou: com taxa alta, o float deixa resíduo
      amortizacao = saldo;
      parcela = amortizacao + juros;
    }
    saldo -= amortizacao;
    let extra = 0;
    if (mes === extraMes && extraValor > 0 && saldo > QUASE_ZERO) {
      extra = Math.min(extraValor, saldo);
      saldo -= extra;
      const restantes = meses - mes;
      if (extraModo === "parcela" && restantes > 0) {
        amortizacaoDoSac = saldo / restantes;
        parcelaFixa = parcelaPrice(saldo, taxa, restantes);
      }
    }
    if (saldo <= QUASE_ZERO) saldo = 0;
    linhas.push({ mes, parcela, juros, amortizacao, extra, saldo });
    if (saldo === 0) break;
  }
  return linhas;
}
