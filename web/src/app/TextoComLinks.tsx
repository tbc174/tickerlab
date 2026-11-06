import type { ReactNode } from "react";

// Endereço escrito no fim da fonte (src/enderecos_das_fontes.py): só https://, sem pontuação final.
const ENDERECO = /(https:\/\/[^\s;,)]*[^\s;,).])/g;

/** O texto da fonte com cada endereço https:// virando link para uma aba nova; o resto fica como texto. */
export function TextoComLinks({ texto }: { texto: string }) {
  const partes: ReactNode[] = [];
  texto.split(ENDERECO).forEach((trecho, i) => {
    // com o grupo de captura, os índices ímpares são os endereços
    if (i % 2 === 1) {
      partes.push(
        <a key={i} href={trecho} target="_blank" rel="noopener noreferrer">
          {trecho}
        </a>,
      );
    } else if (trecho) {
      partes.push(trecho);
    }
  });
  return <>{partes}</>;
}
