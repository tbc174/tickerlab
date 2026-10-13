// Como funciona: os três passos, para quem é, confiança e perguntas. Era `como_funciona()`.
import { Cabecalho, ChamadaFinal, ListaDeCartoes } from "../site/comum";
import { CONFIANCA, PASSOS, PERGUNTAS, PUBLICOS } from "../site/textos";

export const DADOS = {
  caminho: "/como-funciona.html",
  titulo: "Como funciona",
  descricao:
    "Como o TickerLab funciona, para quem é, de onde vêm os números e as perguntas " +
    "frequentes.",
  atual: "/como-funciona.html",
};

export function ComoFunciona() {
  return (
    <>
      <Cabecalho
        olho="Como funciona"
        titulo="Em três passos"
        subtitulo="Da primeira busca ao relatório em PDF, com cada número explicado."
      />
      <section className="faixa secao" aria-label="Os três passos">
        <ol className="passos">
          {PASSOS.map(([titulo, texto], i) => (
            <li key={titulo}>
              <span className="numero">{i + 1}</span>
              <h3>{titulo}</h3>
              <p>{texto}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="faixa secao" aria-labelledby="titulo-quem">
        <p className="olho">Para quem é</p>
        <h2 id="titulo-quem">Feito para quem quer entender, não para quem quer palpite</h2>
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
