// Peça única: o cabeçalho de toda tela. O olho (de onde a tela é: "Empresas", "Setores"), o título (o nome
// da tela ou, na ficha, o nome da empresa), os selos ao lado do título, a descrição e, à direita, as ações
// (baixar, comparar). A tela que tem página no mapa usa `CabecalhoDaTela`, que preenche tudo isto sozinha.
import type { ReactNode } from "react";
import { type PaginaDoApp, conteudoDoApp } from "../../conteudo";

interface Propriedades {
  titulo: string;
  olho?: string;
  descricao?: ReactNode;
  /** Selos ao lado do título (peça `Selo`): situação da empresa, "Companhia aberta". */
  selos?: ReactNode;
  /** Botões e links da tela, à direita no computador e embaixo no celular. */
  acoes?: ReactNode;
}

export function Cabecalho({ titulo, olho, descricao, selos, acoes }: Propriedades) {
  return (
    <header className="cabecalho-da-tela">
      <div className="cabecalho-texto">
        {olho ? <p className="olho">{olho}</p> : null}
        <div className="cabecalho-titulo">
          <h1>{titulo}</h1>
          {selos}
        </div>
        {descricao ? <p className="apagado">{descricao}</p> : null}
      </div>
      {acoes ? <div className="cabecalho-acoes">{acoes}</div> : null}
    </header>
  );
}

/** O cabeçalho de uma tela do mapa de páginas: o olho é a área dela (a "Mais" não diz nada sobre a tela e
 * fica sem olho), o título e a descrição vêm de `src/paginas.py`. */
export function CabecalhoDaTela({ pagina, acoes }: { pagina: PaginaDoApp; acoes?: ReactNode }) {
  // direto do conteúdo (não de areas.ts): areas.ts lê rotas.tsx, que lê as telas, que leem este arquivo
  const area = conteudoDoApp.areas.find((a) => a.chave === pagina.area && a.chave !== "mais");
  return <Cabecalho olho={area?.rotulo} titulo={pagina.titulo} descricao={pagina.descricao} acoes={acoes} />;
}
