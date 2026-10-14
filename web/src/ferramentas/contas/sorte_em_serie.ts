// Sorte em série: cópia em TypeScript de src/ferramentas/sorte_em_serie.py (a referência).
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.
import { criarGerador } from "./aleatorio";

export const MOVIMENTO_DIARIO = 0.01; // cada dia: +1% ou -1%
export const DIAS_POR_ANO = 252;
export const LIMITE_DO_SHARPE = 1;
export const ESTRATEGIAS_MAXIMAS = 1000;
export const DIAS_MAXIMOS = 2520;

export interface ResultadoDaSorte {
  estrategias: number;
  dias: number;
  curva_da_melhor: number[];
  curva_da_mediana: number[];
  curva_da_pior: number[];
  retorno_da_melhor: number;
  retorno_da_mediana: number;
  retorno_da_pior: number;
  sharpe_da_melhor: number;
  com_sharpe_acima_de_1: number;
  lucraram: number;
  media_dos_retornos_diarios: number;
}

const media = (valores: number[]) => valores.reduce((soma, v) => soma + v, 0) / valores.length;

/** Desvio-padrão da amostra (n − 1), como o statistics.stdev do Python. */
function desvioPadrao(valores: number[]): number {
  const m = media(valores);
  return Math.sqrt(valores.reduce((soma, v) => soma + (v - m) ** 2, 0) / (valores.length - 1));
}

/** Sharpe anualizado sem a taxa livre de risco: média / desvio-padrão × √252. */
export function sharpe(retornos: number[]): number {
  const desvio = desvioPadrao(retornos);
  return desvio ? (media(retornos) / desvio) * DIAS_POR_ANO ** 0.5 : 0;
}

function curva(retornos: number[]): number[] {
  const valores = [1];
  for (const r of retornos) valores.push(valores[valores.length - 1] * (1 + r));
  return valores;
}

/** `estrategias` estratégias de cara ou coroa por `dias` dias, todas da mesma `semente`. */
export function simular(estrategias: number, dias: number, semente: number): ResultadoDaSorte {
  if (estrategias < 2 || estrategias > ESTRATEGIAS_MAXIMAS) {
    throw new RangeError(`Use de 2 a ${ESTRATEGIAS_MAXIMAS} estratégias.`);
  }
  if (dias < 2 || dias > DIAS_MAXIMOS) throw new RangeError(`Use de 2 a ${DIAS_MAXIMOS} dias.`);
  const proximo = criarGerador(semente);
  const todas = Array.from({ length: estrategias }, () =>
    Array.from({ length: dias }, () => (proximo() < 0.5 ? MOVIMENTO_DIARIO : -MOVIMENTO_DIARIO)),
  );
  const curvas = todas.map(curva);
  const final = (k: number) => curvas[k][dias];
  // da pior para a melhor pelo valor final; empate fica na ordem em que foi sorteada (sort estável)
  const ordem = [...curvas.keys()].sort((a, b) => final(a) - final(b));
  const [melhor, mediana, pior] = [ordem[estrategias - 1], ordem[Math.floor((estrategias - 1) / 2)], ordem[0]];
  const sharpes = todas.map(sharpe);
  return {
    estrategias,
    dias,
    curva_da_melhor: curvas[melhor],
    curva_da_mediana: curvas[mediana],
    curva_da_pior: curvas[pior],
    retorno_da_melhor: final(melhor) - 1,
    retorno_da_mediana: final(mediana) - 1,
    retorno_da_pior: final(pior) - 1,
    sharpe_da_melhor: sharpes[melhor],
    com_sharpe_acima_de_1: sharpes.filter((s) => s > LIMITE_DO_SHARPE).length,
    lucraram: curvas.filter((c) => c[dias] > 1).length,
    media_dos_retornos_diarios: media(todas.flat()),
  };
}
