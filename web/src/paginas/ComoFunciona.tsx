// Como funciona: do original ao relatório em cinco passos (a coleta vem primeiro), para quem é,
// confiança e perguntas. Era `como_funciona()`.
import { ChamadaFinal, ListaDeCartoes } from "../site/comum";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { TopoDaPagina } from "../site/Fundo";
import { CONFIANCA, PASSOS, PERGUNTAS, PUBLICOS } from "../site/textos";

export const DADOS = {
  caminho: "/como-funciona.html",
  titulo: "Como funciona",
  descricao:
    "Da fonte ao relatório: o original com hash, as versões, a consulta por data e o PDF. " +
    "Para quem analisa empresas.",
  atual: "/como-funciona.html",
};

export function ComoFunciona() {
  return (
    <>
      <TopoDaPagina
        olho="Como funciona"
        titulo="Da fonte ao relatório, em cinco passos"
        subtitulo="A coleta vem primeiro: cada número do relatório volta por este caminho até o original."
      />
      <section className="faixa secao" aria-label="Os cinco passos">
        <ol className="passos">
          {PASSOS.map(([titulo, texto, detalhe], i) => (
            <li key={titulo}>
              <span className="numero">{i + 1}</span>
              <h3>{titulo}</h3>
              <p>{texto}</p>
              <ComoFoiCalculado resumo="Como funciona por dentro">
                <p>{detalhe}</p>
              </ComoFoiCalculado>
            </li>
          ))}
        </ol>
      </section>

      <section className="faixa secao" aria-labelledby="titulo-quem">
        <p className="olho">Para quem é</p>
        <h2 id="titulo-quem">Feito para quem confere, não para quem quer palpite</h2>
        <div className="grade tres">
          <ListaDeCartoes itens={PUBLICOS} />
        </div>
      </section>

      <div className="escura">
        <section className="faixa secao" aria-labelledby="titulo-confianca">
          <p className="olho">Confiança</p>
          <h2 id="titulo-confianca">De onde vêm os números e o que eles não dizem</h2>
          <div className="grade quatro">
            <ListaDeCartoes itens={CONFIANCA} classe="pilar" />
          </div>
          <p>
            <a className="seta" href="/metodologia.html">
              Fontes e metodologia em detalhe
            </a>
          </p>
        </section>
      </div>

      <section className="faixa secao" aria-labelledby="titulo-faq">
        <p className="olho">Perguntas</p>
        <h2 id="titulo-faq">Perguntas frequentes</h2>
        <div className="faq">
          {PERGUNTAS.map(([pergunta, resposta]) => (
            <details key={pergunta}>
              <summary>{pergunta}</summary>
              <p>{resposta}</p>
            </details>
          ))}
        </div>
      </section>
      <ChamadaFinal />
    </>
  );
}
