// O esqueleto de carregamento (ADR 0096): blocos cinza do tamanho do que vai chegar, no lugar de um texto
// "Calculando…" que faz a página pular. O texto fica só como rótulo para o leitor de tela.
export type FormatoDoEsqueleto = "painel" | "grafico" | "lista";

const QUANTOS: Record<FormatoDoEsqueleto, number> = { painel: 4, grafico: 1, lista: 3 };

interface Propriedades {
  tipo: FormatoDoEsqueleto;
  rotulo: string;
}

export function Carregando({ tipo, rotulo }: Propriedades) {
  return (
    <div className={`esqueleto-da-tela esqueleto-${tipo}`} role="status" aria-busy="true" aria-label={rotulo}>
      {Array.from({ length: QUANTOS[tipo] }, (_, i) => (
        <span key={i} className={tipo === "grafico" ? "esqueleto esqueleto-grafico" : "esqueleto"} aria-hidden="true" />
      ))}
    </div>
  );
}
