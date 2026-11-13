// Uma janela por cima da tela (`<dialog>`): a busca e a lista "Todas as telas" abrem e fecham do mesmo jeito.
import { type MouseEvent, type RefObject, useCallback, useRef, useState } from "react";

export interface Dialogo {
  ref: RefObject<HTMLDialogElement | null>;
  aberto: boolean;
  abrir(): void;
  fechar(): void;
  /** Para o `onClose` do dialog: o Esc fecha sem passar pelo `fechar`. */
  aoFechar(): void;
  /** Para o `onClick` do dialog: o fundo escuro em volta é o próprio dialog, e tocar nele fecha. */
  aoClicarNoFundo(evento: MouseEvent<HTMLDialogElement>): void;
}

export function useDialogo(): Dialogo {
  const ref = useRef<HTMLDialogElement>(null);
  const [aberto, setAberto] = useState(false);
  // o jsdom dos testes (e navegador antigo) não tem showModal: aí a janela abre sem o fundo escuro
  const abrir = useCallback(() => {
    const dialogo = ref.current;
    if (!dialogo || dialogo.open) return;
    if (typeof dialogo.showModal === "function") dialogo.showModal();
    else dialogo.open = true;
    setAberto(true);
  }, []);
  const fechar = useCallback(() => {
    const dialogo = ref.current;
    if (!dialogo) return;
    if (typeof dialogo.close === "function") dialogo.close();
    else dialogo.open = false;
    setAberto(false);
  }, []);
  const aoFechar = useCallback(() => setAberto(false), []);
  const aoClicarNoFundo = useCallback(
    (evento: MouseEvent<HTMLDialogElement>) => {
      if (evento.target === evento.currentTarget) fechar();
    },
    [fechar],
  );
  return { ref, aberto, abrir, fechar, aoFechar, aoClicarNoFundo };
}
