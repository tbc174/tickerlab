// As ferramentas que viram "ilhas" no site: o nome vai no HTML (data-ferramenta) e o
// ferramentas.js liga o componente certo no navegador. O build usa o mesmo componente para o HTML
// pronto, que o Google lê.
import type { ComponentType } from "react";
import { AportesEMetas } from "./AportesEMetas";
import { CalculadoraDeDarf } from "./CalculadoraDeDarf";
import { CalculadoraDeJuros } from "./CalculadoraDeJuros";
import { ConversorDeMoedas } from "./ConversorDeMoedas";
import { CorrecaoPelaInflacao } from "./CorrecaoPelaInflacao";
import { CustoDaTaxa, RecuperarAQueda } from "./CustoDasTaxas";
import { JuroReal, TaxaEquivalente } from "./JuroReal";
import { RendaFixa } from "./RendaFixa";
import { SorteEmSerie } from "./SorteEmSerie";
import { ViverDeRenda } from "./ViverDeRenda";

export const FERRAMENTAS = {
  juros: CalculadoraDeJuros,
  aportes: AportesEMetas,
  taxa: CustoDaTaxa,
  queda: RecuperarAQueda,
  renda: ViverDeRenda,
  sorte: SorteEmSerie,
  darf: CalculadoraDeDarf,
  moedas: ConversorDeMoedas,
  rendaFixa: RendaFixa,
  juroReal: JuroReal,
  equivalente: TaxaEquivalente,
  inflacao: CorrecaoPelaInflacao,
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
