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

/** 0.0125 → "1,25%"; com `casas` = 3, 0.00005 → "0,005%". */
export function formatarPorcentagem(fracao: number, casas = 2): string {
  const formato = casas === 2 ? DECIMAL : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: casas });
  return `${formato.format(fracao * 100)}%`;
}

const CURTO = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

/** Para o eixo dos gráficos: 800 → "R$ 800"; 30000 → "R$ 30 mil"; 1500000 → "R$ 1,5 mi". */
export function formatarReaisCurto(valor: number): string {
  const sinal = valor < 0 ? "−" : "";
  const absoluto = Math.abs(valor);
  if (absoluto >= 1e6) return `${sinal}R$ ${CURTO.format(absoluto / 1e6)} mi`;
  if (absoluto >= 1e3) return `${sinal}R$ ${CURTO.format(absoluto / 1e3)} mil`;
  return `${sinal}R$ ${CURTO.format(absoluto)}`;
}
