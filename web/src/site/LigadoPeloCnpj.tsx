// O "ligado pelo CNPJ" da página inicial (pedido do Tiago, 04/11/2026): o que a base junta de uma
// empresa, um cartão por tema. Os temas e as frases vêm de `base/vitrine.py` (`TEMAS_DO_CNPJ`); as
// contagens e os órgãos saem das colunas do catálogo: aqui não se digita número.
import { type TemaDoCnpj, catalogo } from "../conteudo";
import { ancora } from "./Leitura";

const DE_ONDE_VEM = "De onde vêm os dados";

function Tema({ tema }: { tema: TemaDoCnpj }) {
  return (
    <article className="cartao v2-tema-cnpj" aria-labelledby={`tema-cnpj-${tema.chave}`}>
      <h3 id={`tema-cnpj-${tema.chave}`}>{tema.titulo}</h3>
      <p>{tema.texto}</p>
      <ul className="v2-orgaos" aria-label="Órgãos">
        {tema.orgaos.map((orgao) => (
          <li key={orgao}>{orgao}</li>
        ))}
      </ul>
      <p className="v2-tema-cnpj-conta">
        {tema.tabelas === 1 ? "1 tabela" : `${tema.tabelas} tabelas`}
      </p>
    </article>
  );
}

export function LigadoPeloCnpj() {
  const { totais, ligado_pelo_cnpj: ligado } = catalogo;
  return (
    <section
      className="faixa secao v2-ligado-pelo-cnpj"
      id="ligado-pelo-cnpj"
      aria-labelledby="titulo-ligado-pelo-cnpj"
    >
      <p className="olho">Um CNPJ, muitas fontes</p>
      <h2 id="titulo-ligado-pelo-cnpj">
        {`${ligado.tabelas} das ${totais.tabelas} tabelas se ligam pelo CNPJ`}
      </h2>
      <p className="subtitulo">
        {`Cada órgão publica a sua parte sobre uma empresa. A base junta o que ${ligado.orgaos} órgãos públicos publicam pelo CNPJ, e a raiz dele liga a matriz às filiais. Cada linha guarda o dia em que ficou pública.`}
      </p>
      <div className="grade v2-temas-cnpj">
        {ligado.temas.map((tema) => (
          <Tema key={tema.chave} tema={tema} />
        ))}
      </div>
      <p className="v2-ligado-nota">
        O app mostra o que a licença de cada fonte deixa, e nome de pessoa física não aparece.
      </p>
      <a className="seta" href={`/dados.html#${ancora(DE_ONDE_VEM)}`}>
        Cada tabela, com a fonte e a licença
      </a>
    </section>
  );
}
