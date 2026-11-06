// O id de um campo ou de um gráfico, único na página inteira. No navegador cada ferramenta é uma raiz
// própria (ferramentas/cliente.tsx), e o useId do Preact (o ferramentas.js roda nele) recomeça em
// cada raiz: duas ferramentas na mesma página repetiriam o mesmo id, e o rótulo de uma apontaria para
// o campo da outra. O cliente dá a cada raiz um prefixo; no HTML do build (uma raiz só), não há.
import { createContext, useContext, useId } from "react";

export const PrefixoDoId = createContext("");

export function useIdUnico(): string {
  return useContext(PrefixoDoId) + useId();
}
