// A mira dos gráficos: o ponto apontado pelo mouse, pelo toque ou pelas setas do teclado
// (Home e End vão às pontas). Sem ponto apontado, não há dica.
import { type KeyboardEvent, type PointerEvent, useState } from "react";

export function useMira(total: number, indiceDoX: (xNoDesenho: number) => number) {
  const [indice, setIndice] = useState<number | null>(null);
  const limitar = (i: number) => Math.min(total - 1, Math.max(0, i));
  return {
    indice,
    sair: () => setIndice(null),
    apontar: (evento: PointerEvent<SVGSVGElement>) => {
      const caixa = evento.currentTarget.getBoundingClientRect();
      setIndice(limitar(indiceDoX(evento.clientX - caixa.left)));
    },
    teclar: (evento: KeyboardEvent<SVGSVGElement>) => {
      const passos: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, Home: -total, End: total };
      if (!(evento.key in passos)) return;
      evento.preventDefault();
      setIndice((atual) => limitar((atual ?? total - 1) + passos[evento.key]));
    },
  };
}
