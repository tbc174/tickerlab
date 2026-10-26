// Relatórios: os dois de exemplo, o de uma empresa e o de um setor (o item do topo do plano do site
// para quem analisa, 18/10/2026). Cada cartão usa o título e a descrição da própria página.
import { TopoDaPagina } from "../site/Fundo";
import { DADOS as DADOS_DO_RAIO_X, MOMENTO_DO_RAIO_X, RAIO_X } from "./RaioXDoChoque";
import { DADOS as DADOS_DA_EMPRESA } from "./RelatorioExemplo";
import { DADOS as DADOS_DO_SETOR } from "./RelatorioSemanalEletricas";

const FRASE = "Dois relatórios de exemplo, feitos com a base: o de uma empresa e o de um setor.";

export const DADOS = {
  caminho: "/relatorios.html",
  titulo: "Relatórios",
  descricao: FRASE,
  atual: "/relatorios.html",
};

// o olho de cada cartão é o mesmo do topo da página do relatório
const RELATORIOS = [
  { olho: "Relatório de exemplo", ...DADOS_DA_EMPRESA },
  { olho: "Relatório de setor", ...DADOS_DO_SETOR },
];

/** Os estudos de um acontecimento do mercado (o primeiro: o circuit breaker de 26/10/2026). */
function Estudos() {
  return (
    <section className="faixa" aria-labelledby="titulo-estudos">
      <h2 id="titulo-estudos" className="olho">
        Estudo do dia
      </h2>
      <article className="cartao cartao-de-relatorio">
        <p className="olho">
          {DADOS_DO_RAIO_X.titulo} · {MOMENTO_DO_RAIO_X}
        </p>
        <h3>
          <a href={DADOS_DO_RAIO_X.caminho}>{RAIO_X.titulo}</a>
        </h3>
        <p>{DADOS_DO_RAIO_X.descricao}</p>
      </article>
    </section>
  );
}

export function Relatorios() {
  return (
    <>
      <TopoDaPagina titulo={DADOS.titulo} subtitulo={FRASE} />
      <Estudos />
      <section className="faixa secao" aria-label={DADOS.titulo}>
        <div className="grade dois">
          {RELATORIOS.map((r) => (
            <article className="cartao cartao-de-relatorio" key={r.caminho}>
              <p className="olho">{r.olho}</p>
              <h2>
                <a href={r.caminho}>{r.titulo}</a>
              </h2>
              <p>{r.descricao}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
