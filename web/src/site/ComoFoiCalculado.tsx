// "Como foi calculado": a explicação de um número ou de uma regra, recolhida (ADR 0099, item 7).
// É um <details> do HTML: abre e fecha sem JavaScript, e o texto fica no HTML para o Google ler.
import type { ReactNode } from "react";

export function ComoFoiCalculado({
  resumo = "Como foi calculado",
  children,
}: {
  resumo?: string;
  children: ReactNode;
}) {
  return (
    <details className="como-foi-calculado">
      <summary>{resumo}</summary>
      <div className="como-foi-calculado-texto">{children}</div>
    </details>
  );
}
