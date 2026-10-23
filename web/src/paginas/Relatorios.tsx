// Relatórios: os dois de exemplo, o de uma empresa e o de um setor (o item do topo do plano do site
// para quem analisa, 18/10/2026). Cada cartão usa o título e a descrição da própria página.
import { TopoDaPagina } from "../site/Fundo";
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

export function Relatorios() {
  return (
    <>
      <TopoDaPagina titulo={DADOS.titulo} subtitulo={FRASE} />
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
