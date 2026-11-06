// Produto: o resumo em três blocos (relatórios, a base, exportar) e, abaixo, os módulos do app, o que
// já está nele e o que vem por aí. Era `produto()`. A página inicial é o produto; esta resume.
import { Fragment } from "react";
import { ChamadaFinal, MODULOS_DO_PRODUTO, SecaoDoModulo } from "../site/comum";
import { TopoDaPagina } from "../site/Fundo";

export const DADOS = {
  caminho: "/produto.html",
  titulo: "Produto",
  descricao:
    "Relatórios com a fonte de cada número, a base com a data de cada dado e a exportação em " +
    "PDF: o que o TickerLab já faz e o que está em construção.",
  atual: "/produto.html",
};

const BLOCOS = [
  {
    id: "bloco-relatorios",
    titulo: "Relatórios",
    texto:
      "O PDF de uma empresa ou de um setor, com a fonte e a data de cada número, o que não foi " +
      "achado e a seção “Limites e cuidados”. Há dois de exemplo, abertos.",
    link: "/relatorios.html",
    rotulo: "Ver os relatórios de exemplo",
  },
  {
    id: "bloco-a-base",
    titulo: "A base",
    texto:
      "Tabelas de fontes públicas, cada uma com a licença da fonte e a data em que o dado ficou " +
      "público. Uma consulta a um dia só enxerga o que já era público nele.",
    link: "/dados.html",
    rotulo: "Ver as tabelas e as fontes",
  },
  {
    id: "bloco-exportar",
    titulo: "Exportar",
    texto:
      "O relatório sai em PDF, e o original que você gerou fica guardado para baixar de novo. A " +
      "exportação da base em tabela e a API aberta ainda estão em construção, sem data marcada.",
    link: "/metodologia.html#relatorios-em-pdf",
    rotulo: "Como os relatórios são feitos",
  },
];

export function Produto() {
  return (
    <>
      <TopoDaPagina
        olho="Produto"
        titulo="Relatórios, a base e a exportação, em resumo"
        subtitulo={
          "Três coisas para quem analisa empresas. Abaixo, os módulos do app, com o selo do que " +
          "já está nele e do que ainda está em construção."
        }
      >
        <p className="atalhos">
          {MODULOS_DO_PRODUTO.map((m, i) => (
            <Fragment key={m.chave}>
              {i > 0 ? " " : null}
              <a className="botao secundario pequeno" href={`#${m.chave}`}>
                {m.nome}
              </a>
            </Fragment>
          ))}
        </p>
      </TopoDaPagina>
      <section className="faixa secao" aria-label="O produto em três blocos">
        <div className="grade tres">
          {BLOCOS.map((b) => (
            <article key={b.id} id={b.id} className="cartao">
              <h3>{b.titulo}</h3>
              <p>{b.texto}</p>
              <a className="seta" href={b.link}>
                {b.rotulo}
              </a>
            </article>
          ))}
        </div>
      </section>
      <section className="faixa secao" aria-labelledby="titulo-modulos">
        <p className="olho">No app</p>
        <h2 id="titulo-modulos">Os módulos, um a um</h2>
        <p className="subtitulo">O que está em breve não tem data marcada.</p>
      </section>
      {MODULOS_DO_PRODUTO.map((m) => (
        <SecaoDoModulo key={m.chave} modulo={m} />
      ))}
      <ChamadaFinal />
    </>
  );
}
