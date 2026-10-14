// Gerador pseudoaleatório pequeno (mulberry32): cópia de src/ferramentas/aleatorio.py. Com o mesmo
// algoritmo dos dois lados, a mesma semente dá as mesmas estratégias no site e no Python. Não serve
// para nada que precise de segurança: é só para simulações reproduzíveis.

/** Números entre 0 (incluído) e 1 (excluído), sempre os mesmos para a mesma semente. */
export function criarGerador(semente: number): () => number {
  let estado = semente | 0;
  return () => {
    estado = (estado + 0x6d2b79f5) | 0;
    let t = Math.imul(estado ^ (estado >>> 15), 1 | estado);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Os `quantidade` primeiros números da `semente` (o golden compara com o Python). */
export function sequencia(semente: number, quantidade: number): number[] {
  const proximo = criarGerador(semente);
  return Array.from({ length: quantidade }, () => proximo());
}
