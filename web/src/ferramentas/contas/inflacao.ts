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

/** O valor no começo e no fim de cada mês de `inicio` a `fim` (para o gráfico). Serve a qualquer
 * série mensal no mesmo formato (IPCA, CDI ou poupança do mês). */
export function evolucao(valor: number, inicio: string, fim: string, meses: Meses): number[] {
  corrigir(valor, inicio, fim, meses); // as mesmas conferências de período
  const caminho = [valor];
  for (const [mes, variacao] of meses) {
    if (inicio <= mes && mes <= fim) caminho.push(caminho[caminho.length - 1] * (1 + variacao));
  }
  return caminho;
}

/** Por ano: o fator acumulado e quantos meses a série tem naquele ano. */
function fatoresPorAno(meses: Meses): Map<number, [number, number]> {
  const porAno = new Map<number, [number, number]>();
  for (const [mes, variacao] of meses) {
    const ano = Number(mes.slice(0, 4));
    const [fator, quantos] = porAno.get(ano) ?? [1, 0];
    porAno.set(ano, [fator * (1 + variacao), quantos + 1]);
  }
  return porAno;
}

/** [em quantos anos o rendimento ficou abaixo da inflação, quantos anos deu para comparar], nos
 * `anos` anos até `anoFinal`; só entram anos completos (12 meses) nas duas séries. */
export function anosAbaixo(rendimento: Meses, inflacao: Meses, anoFinal: number, anos: number): [number, number] {
  const doRendimento = fatoresPorAno(rendimento);
  const daInflacao = fatoresPorAno(inflacao);
  let [perdeu, comparados] = [0, 0];
  for (let ano = anoFinal - anos + 1; ano <= anoFinal; ano++) {
    const [r, mesesR] = doRendimento.get(ano) ?? [1, 0];
    const [i, mesesI] = daInflacao.get(ano) ?? [1, 0];
    if (mesesR === MESES_POR_ANO && mesesI === MESES_POR_ANO) {
      comparados++;
      if (r < i) perdeu++;
    }
  }
  return [perdeu, comparados];
}
