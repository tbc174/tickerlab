// Números das ferramentas como as pessoas escrevem no Brasil: "1.234,56" na entrada e "R$ 1.234,56"
// na saída. A entrada é texto (não <input type="number">), para aceitar a vírgula.

const REAIS = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const DECIMAL = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

/** "1.234,56" → 1234.56; "12,5" → 12.5; "1234.5" → 1234.5; vazio ou texto → null. */
export function lerNumero(texto: string): number | null {
  let limpo = texto.trim().replace(/^R\$\s*/, "").replace(/%$/, "").replace(/\s/g, "");
  if (limpo === "") return null;
  if (limpo.includes(",")) {
    limpo = limpo.replace(/\./g, "").replace(",", "."); // 1.234,56: o ponto é de milhar
  } else if (/^-?[1-9]\d{0,2}(\.\d{3})+$/.test(limpo)) {
    limpo = limpo.replace(/\./g, ""); // 1.000 e 10.000.000 são milhares; 0.500 é decimal
  }
  if (!/^-?\d+(\.\d+)?$/.test(limpo)) return null;
  return Number(limpo);
}

/** 1234.5 → "R$ 1.234,50" (o espaço depois do R$ é o não separável do próprio Intl). */
export function formatarReais(valor: number): string {
  return REAIS.format(valor);
}

/** 12.5 → "12,5"; 1234 → "1.234". */
export function formatarNumero(valor: number): string {
  return DECIMAL.format(valor);
}

/** 0.0125 → "1,25%". */
export function formatarPorcentagem(fracao: number): string {
  return `${DECIMAL.format(fracao * 100)}%`;
}
