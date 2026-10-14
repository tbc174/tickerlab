// A largura real do lugar do gráfico, para desenhar em pixels de verdade (o texto do eixo não
// encolhe no celular, como aconteceria esticando um viewBox fixo). No HTML pronto do build não há
// medida: vale a largura padrão, e o navegador redesenha ao ligar.
import { useCallback, useRef, useState } from "react";

export function useLargura(padrao: number): [number, (elemento: HTMLElement | null) => void] {
  const [largura, setLargura] = useState(padrao);
  const observador = useRef<ResizeObserver | null>(null);
  const ref = useCallback((elemento: HTMLElement | null) => {
    // o gráfico some e volta quando um campo fica inválido: solta o observador do elemento velho
    observador.current?.disconnect();
    observador.current = null;
    if (!elemento || typeof ResizeObserver === "undefined") return;
    const medir = () => {
      const medida = Math.round(elemento.getBoundingClientRect().width);
      if (medida > 0) setLargura(medida);
    };
    medir();
    observador.current = new ResizeObserver(medir);
    observador.current.observe(elemento);
  }, []);
  return [largura, ref];
}
