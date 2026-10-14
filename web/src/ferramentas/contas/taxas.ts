// Juro real e taxa nominal (Fisher): cópia em TypeScript de src/ferramentas/taxas.py.

function conferir(inflacao: number): void {
  if (inflacao <= -1) throw new RangeError("A inflação precisa ser maior que -100%.");
}

/** O rendimento acima da inflação no mesmo prazo das duas taxas. */
export function juroReal(nominal: number, inflacao: number): number {
  conferir(inflacao);
  if (nominal <= -1) throw new RangeError("A taxa precisa ser maior que -100%.");
  return (1 + nominal) / (1 + inflacao) - 1;
}

/** A taxa que rende `real` acima de uma `inflacao`. */
export function taxaNominal(real: number, inflacao: number): number {
  conferir(inflacao);
  if (real <= -1) throw new RangeError("O juro real precisa ser maior que -100%.");
  return (1 + real) * (1 + inflacao) - 1;
}
