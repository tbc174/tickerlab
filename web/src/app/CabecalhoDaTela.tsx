// O cabeçalho de toda tela com formulário (ADR 0096): o olho (por enquanto o grupo da página; vira a área
// no PR 2 da reorganização), o título, a descrição e, à direita, as ações da tela (ex.: o relatório).
import type { ReactNode } from "react";
import type { PaginaDoApp } from "../conteudo";

interface Propriedades {
  pagina: PaginaDoApp;
  acoes?: ReactNode;
}

export function CabecalhoDaTela({ pagina, acoes }: Propriedades) {
  return (
    <header className="cabecalho-da-tela">
      <div className="cabecalho-texto">
        <p className="olho">{pagina.grupo}</p>
        <h1>{pagina.titulo}</h1>
        <p className="apagado">{pagina.descricao}</p>
      </div>
      {acoes ? <div className="cabecalho-acoes">{acoes}</div> : null}
    </header>
  );
}
