// Conversor pela PTAX: cópia em TypeScript de src/ferramentas/moedas.py (a referência).
// Cotações em reais por unidade (PTAX de venda); entre duas estrangeiras, passa pelo real.

export const REAL = "BRL";

function emReais(moeda: string, cotacoes: Record<string, number>): number {
  if (moeda === REAL) return 1;
  if (!(moeda in cotacoes)) throw new RangeError(`Sem cotação PTAX para ${moeda}.`);
  return cotacoes[moeda];
}

/** `valor` na moeda `de` convertido para `para` ("BRL" é o real). */
export function converter(valor: number, de: string, para: string, cotacoes: Record<string, number>): number {
  return (valor * emReais(de, cotacoes)) / emReais(para, cotacoes);
}
