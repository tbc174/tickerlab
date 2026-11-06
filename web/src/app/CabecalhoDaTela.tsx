// O cabeçalho de toda tela com formulário (ADR 0096): o olho (a área do menu: Ativo, Estratégias...), o
// título, a descrição e, à direita, as ações da tela (ex.: o relatório).
import type { ReactNode } from "react";
import { type PaginaDoApp, conteudoDoApp } from "../conteudo";

interface Propriedades {
  pagina: PaginaDoApp;
  acoes?: ReactNode;
}

export function CabecalhoDaTela({ pagina, acoes }: Propriedades) {
  // direto do conteúdo (não de areas.ts): areas.ts lê rotas.tsx, que lê as telas, que leem este arquivo
  const area = conteudoDoApp.areas.find((a) => a.chave === pagina.area);
  return (
    <header className="cabecalho-da-tela">
      <div className="cabecalho-texto">
        {area ? <p className="olho">{area.rotulo}</p> : null}
        <h1>{pagina.titulo}</h1>
        <p className="apagado">{pagina.descricao}</p>
      </div>
      {acoes ? <div className="cabecalho-acoes">{acoes}</div> : null}
    </header>
  );
}
