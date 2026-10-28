// Sobre: o texto das peças institucionais aprovadas (carrosséis e Reels, 13/10/2026). Era `sobre()`.
// Mude só junto com as peças: há teste no Python que confere as frases aprovadas.
import { ListaDeCartoes } from "../site/comum";
import { Fundo } from "../site/Fundo";
import { ASSINATURA, TICKER_DO_EXEMPLO, linkDoApp } from "../site/textos";

export const DADOS = {
  caminho: "/sobre.html",
  titulo: "Sobre",
  descricao:
    "Quem somos, nossa história e no que acreditamos: o TickerLab conecta perspectivas de " +
    "análise para quem analisa empresas e precisa conferir a fonte.",
  atual: "/sobre.html",
};

const PILARES = ["Dados confiáveis", "Método e contexto", "Múltiplas perspectivas"];

const HISTORIA: [string, string][] = [
  ["Tudo começou com Python e Pandas.", "A história do TickerLab."],
  [
    "O primeiro projeto universitário.",
    "Usávamos dados do Yahoo Finance para fazer análises financeiras básicas, como calcular o " +
      "retorno total de ativos.",
  ],
  [
    "A evolução.",
    "Vieram a infraestrutura própria em um servidor doméstico (NAS), os backtests, o banco de " +
      "dados e análises mais elaboradas.",
  ],
  [
    "O ponto de virada.",
    "Percebemos que aquelas ferramentas poderiam facilitar a pesquisa financeira de muitas " +
      "outras pessoas. O projeto começou a crescer.",
  ],
  [
    "De projeto acadêmico à construção de uma plataforma de inteligência financeira.",
    "Nossa história continua.",
  ],
];

const PERSPECTIVAS: [string, string][] = [
  [
    "Fundamentos.",
    "Resultados, endividamento e geração de valor ajudam a compreender uma empresa. Mas essa " +
      "é apenas uma perspectiva.",
  ],
  [
    "Comportamento e estatística.",
    "Gráficos, tendências, volatilidade e estudos históricos revelam outros aspectos — e nem " +
      "sempre apontam na mesma direção.",
  ],
  [
    "Inteligência Integrada.",
    "Nossa visão é conectar métodos, mostrar concordâncias, divergências, riscos e limitações.",
  ],
];

// Para quem é (plano do site para quem analisa, PR 9): fora do texto aprovado das peças institucionais.
const PARA_QUEM_E: [string, string][] = [
  [
    "Analistas e equipes de análise.",
    "Quem confere uma empresa e o grupo dela contra as bases públicas, com a data de cada fonte.",
  ],
  [
    "Estudantes e pesquisadores.",
    "Quem precisa de um número que possa citar, com fonte, data e versão.",
  ],
  [
    "Equipes.",
    "O plano Casa, por assento, para quem analisa junto. Ainda está em construção.",
  ],
];

/** A Inteligência Integrada: três círculos que se juntam quando a seção aparece (movimento.js). */
function TresPerspectivas() {
  return (
    <figure
      className="v2-venn"
      aria-label="Três perspectivas que se juntam: fundamentalista, técnica e quantitativa"
    >
      <svg viewBox="0 0 420 340" aria-hidden="true">
        <circle className="c1" cx="160" cy="130" r="105" />
        <circle className="c2" cx="260" cy="130" r="105" />
        <circle className="c3" cx="210" cy="215" r="105" />
        <text className="t1" x="112" y="104">Fundamentalista</text>
        <text className="t2" x="308" y="104">Técnica</text>
        <text className="t3" x="210" y="292">Quantitativa</text>
        <text className="centro" x="210" y="156">Inteligência</text>
        <text className="centro" x="210" y="176">Integrada</text>
      </svg>
    </figure>
  );
}

export function Sobre() {
  return (
    <>
      <Fundo classe="v2-heroi-pagina v2-heroi-sobre">
        <section id="quem-somos" className="faixa secao sobre-topo" aria-labelledby="titulo-sobre">
          <p className="olho">Quem somos</p>
          <h1 id="titulo-sobre">Uma análise não conta toda a história.</h1>
          <div className="sobre-colunas">
            <p className="subtitulo">
              O mercado financeiro oferece inúmeros dados, gráficos e indicadores. Mas
              informações isoladas nem sempre ajudam a compreender o conjunto.
            </p>
            <p className="subtitulo">
              Nossa visão é conectar diferentes perspectivas de análise. Queremos tornar a
              pesquisa de investimentos mais clara, profunda e organizada.
            </p>
          </div>
          <ul className="pilares-sobre">
            {PILARES.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
          <p className="assinatura-sobre">
            <strong>{ASSINATURA}</strong> Uma plataforma brasileira de inteligência financeira.
          </p>
        </section>
      </Fundo>

      <section id="para-quem-e" className="faixa secao" aria-labelledby="titulo-para-quem">
        <p className="olho">Para quem é</p>
        <h2 id="titulo-para-quem">Para quem analisa empresas</h2>
        <p className="subtitulo">
          O TickerLab é uma ferramenta de dados auditáveis: cada número chega com a fonte e a
          data, e o que a base não achou também aparece.
        </p>
        <div className="grade tres">
          <ListaDeCartoes itens={PARA_QUEM_E} />
        </div>
      </section>

      <section id="nossa-historia" className="faixa secao" aria-labelledby="titulo-historia">
        <p className="olho">Nossa história</p>
        <h2 id="titulo-historia">De um projeto universitário a uma plataforma</h2>
        <ol className="linha-do-tempo">
          {HISTORIA.map(([titulo, texto]) => (
            <li key={titulo}>
              <h3>{titulo}</h3>
              <p>{texto}</p>
            </li>
          ))}
        </ol>
      </section>

      <section
        id="no-que-acreditamos"
        className="faixa secao"
        aria-labelledby="titulo-acreditamos"
      >
        <p className="olho">No que acreditamos</p>
        <h2 id="titulo-acreditamos">Diferentes perspectivas. Uma visão mais completa.</h2>
        <p className="subtitulo">
          O princípio da Inteligência Integrada: fundamentalista, técnica e quantitativa.
        </p>
        <div className="v2-acreditamos">
          <TresPerspectivas />
          <div className="grade tres v2-tres-um">
            <ListaDeCartoes itens={PERSPECTIVAS} />
          </div>
        </div>
        <p className="contagem v2-lema">Mais contexto · Mais clareza · Mais autonomia</p>
      </section>

      <div className="escura v2-final-fundo">
        <div className="v2-horizonte v2-horizonte-alto" aria-hidden="true" />
        <section className="faixa secao final" aria-labelledby="titulo-decisoes">
          <h2 id="titulo-decisoes">Não queremos substituir suas decisões.</h2>
          <p className="subtitulo">
            Queremos contribuir para uma pesquisa de investimentos mais clara, fundamentada e
            autônoma.
          </p>
          <a
            className="botao primario"
            href={linkDoApp("visao-geral", { ticker: TICKER_DO_EXEMPLO })}
          >
            Comece pela sua primeira análise
          </a>
        </section>
      </div>
    </>
  );
}
