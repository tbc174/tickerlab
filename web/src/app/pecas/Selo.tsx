// Peça única: o selo, uma etiqueta curta ao lado de um título ou numa célula ("Ativa", "Companhia aberta",
// "Novo", "Em breve"). O tom muda a cor, mas o sentido está sempre no texto: cor sozinha não informa.
import type { ReactNode } from "react";

/** neutro: um fato sem juízo; destaque: o que é novo; bom, atencao e alerta: a situação de um dado. */
export type TomDoSelo = "neutro" | "destaque" | "bom" | "atencao" | "alerta";

interface Propriedades {
  children: ReactNode;
  tom?: TomDoSelo;
}

export function Selo({ children, tom = "neutro" }: Propriedades) {
  return <span className={`selo-do-app ${tom}`}>{children}</span>;
}
