// Correção pelo IPCA: cópia em TypeScript de src/ferramentas/inflacao.py (a referência).
// O mês inicial e o final entram, como na Calculadora do Cidadão do BC.

const MESES_POR_ANO = 12;
export type Meses = [string, number][]; // [["2024-12", 0.0052], ...], em ordem

export interface Correcao {
  valor_corrigido: number;
  fator: number;
  variacao: number;
  meses: number;
}

function conferirMes(mes: string): void {
  const [ano, numero] = mes.split("-");
  if (!/^\d+$/.test(ano ?? "") || !/^\d+$/.test(numero ?? "") || Number(numero) < 1 || Number(numero) > MESES_POR_ANO) {
    throw new RangeError(`Use o mês no formato AAAA-MM, não ${mes}.`);
  }
}

/** `valor` do começo de `inicio` corrigido até o fim de `fim` ("AAAA-MM") pelo IPCA. */
export function corrigir(valor: number, inicio: string, fim: string, meses: Meses): Correcao {
  conferirMes(inicio);
  conferirMes(fim);
  if (fim < inicio) throw new RangeError("O mês final precisa vir depois do inicial.");
  const [primeiro, ultimo] = [meses[0][0], meses[meses.length - 1][0]];
  if (inicio < primeiro) throw new RangeError(`O IPCA usado aqui começa em ${primeiro}.`);
  if (fim > ultimo) throw new RangeError(`O último IPCA divulgado é o de ${ultimo}.`);
  let fator = 1;
  let usados = 0;
  for (const [mes, variacao] of meses) {
    if (inicio <= mes && mes <= fim) {
      fator *= 1 + variacao;
      usados++;
    }
  }
  return { valor_corrigido: valor * fator, fator, variacao: fator - 1, meses: usados };
}

/** O IPCA acumulado nos últimos 12 meses da lista. */
export function em12Meses(meses: Meses): number {
  if (meses.length < MESES_POR_ANO) throw new RangeError("São precisos pelo menos 12 meses de IPCA.");
  let fator = 1;
  for (const [, variacao] of meses.slice(-MESES_POR_ANO)) fator *= 1 + variacao;
  return fator - 1;
}
