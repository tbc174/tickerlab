// Preço médio de ações e FIIs: cópia em TypeScript de src/ferramentas/preco_medio.py (a referência).
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.
// Compra soma as taxas ao custo; venda não muda o médio; bonificação entra com o valor atribuído;
// desdobro e grupamento só mudam a quantidade; amortização de FII baixa o custo.

export const TIPOS = ["compra", "venda", "bonificacao", "desdobro", "grupamento", "amortizacao"] as const;
export type TipoDeOperacao = (typeof TIPOS)[number];
const QUASE_ZERO = 1e-9;

export interface Operacao {
  tipo: string;
  quantidade: number;
  preco?: number; // por ação; na bonificação, o valor atribuído; na amortização, por cota
  custos?: number; // corretagem e taxas da operação, em reais
}

export interface Linha {
  tipo: string;
  quantidade: number;
  custo_total: number;
  preco_medio: number | null;
  resultado: number | null; // na venda; na amortização, o que passou do custo (ganho de capital)
}

/** A posição depois de cada operação, na ordem em que foram feitas. */
export function calcular(operacoes: Operacao[]): Linha[] {
  let quantidade = 0;
  let custo = 0;
  const linhas: Linha[] = [];
  for (const op of operacoes) {
    const preco = op.preco ?? 0;
    const custos = op.custos ?? 0;
    if (!(TIPOS as readonly string[]).includes(op.tipo)) throw new RangeError(`Operação de tipo desconhecido: '${op.tipo}'`);
    if (op.quantidade < 0 || preco < 0 || custos < 0) throw new RangeError("Quantidade, preço e custos não podem ser negativos.");
    let resultado: number | null = null;
    if (op.tipo === "compra") {
      quantidade += op.quantidade;
      custo += op.quantidade * preco + custos;
    } else if (op.tipo === "bonificacao") {
      quantidade += op.quantidade;
      custo += op.quantidade * preco;
    } else if (op.tipo === "desdobro") {
      quantidade += op.quantidade;
    } else if (op.tipo === "amortizacao") {
      if (quantidade <= QUASE_ZERO) throw new RangeError("Amortização sem cotas na posição.");
      const abatido = preco * quantidade;
      if (abatido > custo) resultado = abatido - custo; // o que passa do custo é ganho de capital
      custo = Math.max(custo - abatido, 0);
    } else {
      if (op.quantidade > quantidade + QUASE_ZERO) throw new RangeError("Saem mais ações do que há na posição.");
      if (op.tipo === "venda" && quantidade <= QUASE_ZERO) throw new RangeError("Venda sem ações na posição.");
      if (op.tipo === "venda") {
        const custoDaVenda = (custo / quantidade) * op.quantidade;
        resultado = op.quantidade * preco - custos - custoDaVenda;
        custo -= custoDaVenda;
      }
      quantidade -= op.quantidade;
      if (quantidade <= QUASE_ZERO) {
        quantidade = 0;
        custo = 0;
      }
    }
    const medio = quantidade > QUASE_ZERO ? custo / quantidade : null;
    linhas.push({ tipo: op.tipo, quantidade, custo_total: custo, preco_medio: medio, resultado });
  }
  return linhas;
}
