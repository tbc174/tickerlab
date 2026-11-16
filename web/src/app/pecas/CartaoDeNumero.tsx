// Peça única: um número com o que ele é. O rótulo em cima, o valor em fonte de largura fixa, uma linha de
// detalhe (a comparação, o período) e a fonte com a data embaixo. Vários cartões lado a lado vão dentro de
// `<div className="numeros">`. O valor chega já escrito (formatar.ts): a peça não faz conta.
import type { ReactNode } from "react";

interface Propriedades {
  rotulo: string;
  /** O número já formatado ("1.284", "R$ 3,2 mi"); sem dado, o travessão, nunca um zero inventado. */
  valor: string | null;
  /** Uma linha curta embaixo do valor: o período, a comparação. */
  detalhe?: ReactNode;
  /** A fonte e a data do número (peça `Fonte`). */
  fonte?: ReactNode;
  /** A explicação do termo, ao lado do rótulo (peça `Ajuda`). */
  ajuda?: ReactNode;
  /** O número principal do painel: maior e com a borda mais forte. */
  principal?: boolean;
}

const SEM_DADO = "—";

export function CartaoDeNumero({ rotulo, valor, detalhe, fonte, ajuda, principal }: Propriedades) {
  return (
    <div className={principal ? "numero-do-painel principal" : "numero-do-painel"}>
      <span className="numero-rotulo">
        <span>{rotulo}</span>
        {ajuda}
      </span>
      <span className="numero-valor">{valor ?? SEM_DADO}</span>
      {detalhe ? <span className="numero-detalhe">{detalhe}</span> : null}
      {fonte}
    </div>
  );
}
