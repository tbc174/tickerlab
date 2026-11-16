// Os cruzamentos da página inicial (plano do site para quem analisa, PR 6, tarefa 10; empresas fechadas
// desde a linha 925): fatos que só aparecem juntando duas tabelas da base ou mais, agrupados pela pergunta
// que respondem. Os textos, o parágrafo e os grupos vêm prontos de `base/vitrine.py` (`fatos_da_base`),
// com a fonte, a data e a conta recolhida; aqui não se digita número nem nome.
import { type FatoDaBase, type GrupoDeFatos, fatosDaBase } from "../conteudo";
import { ComoFoiCalculado } from "./ComoFoiCalculado";

function Fato({ fato }: { fato: FatoDaBase }) {
  return (
    <article className="cartao v2-fato" aria-label={`${fato.numero} ${fato.texto}`}>
      <p className="v2-fato-numero">{fato.numero}</p>
      <p className="v2-fato-texto">{fato.texto}</p>
      <p className="v2-fato-fonte">Fonte: {fato.fonte}</p>
      <ComoFoiCalculado>
        <p>{fato.como_foi_calculado}</p>
      </ComoFoiCalculado>
    </article>
  );
}

function Grupo({ grupo }: { grupo: GrupoDeFatos }) {
  const titulo = `cruzamentos-${grupo.chave}`;
  return (
    <div className="v2-fatos-grupo" aria-labelledby={titulo}>
      <h3 id={titulo} className="v2-fatos-pergunta">
        {grupo.pergunta}
      </h3>
      <div className="grade v2-fatos">
        {grupo.fatos.map((fato) => (
          <Fato key={fato.chave} fato={fato} />
        ))}
      </div>
    </div>
  );
}

export function Cruzamentos() {
  const { grupos, subtitulo } = fatosDaBase;
  return (
    <section
      className="faixa secao v2-cruzamentos"
      id="cruzamentos"
      aria-labelledby="titulo-cruzamentos"
    >
      <p className="olho">Cruzamentos</p>
      <h2 id="titulo-cruzamentos">O que só aparece juntando fontes</h2>
      <p className="subtitulo">{subtitulo}</p>
      {grupos.map((grupo) => (
        <Grupo key={grupo.chave} grupo={grupo} />
      ))}
    </section>
  );
}
