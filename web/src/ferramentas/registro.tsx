// As ferramentas que viram "ilhas" no site: o nome vai no HTML (data-ferramenta) e o
// ferramentas.js liga o componente certo no navegador. O build usa o mesmo componente para o HTML
// pronto, que o Google lê.
import type { ComponentType } from "react";
import { CalculadoraDeJuros } from "./CalculadoraDeJuros";

export const FERRAMENTAS = {
  juros: CalculadoraDeJuros,
} satisfies Record<string, ComponentType>;

export type NomeDaFerramenta = keyof typeof FERRAMENTAS;

/** O lugar da ferramenta na página. */
export function Ilha({ nome }: { nome: NomeDaFerramenta }) {
  const Componente = FERRAMENTAS[nome];
  return (
    <div className="ferramenta-ilha" data-ferramenta={nome}>
      <Componente />
    </div>
  );
}
