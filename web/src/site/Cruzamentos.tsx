// Os cruzamentos da página inicial (plano do site para quem analisa, PR 6, tarefa 10): fatos que só
// aparecem juntando duas tabelas da base ou mais. Os textos vêm prontos de `base/vitrine.py`
// (`fatos_agregados`), com a fonte, a data e a conta recolhida; aqui não se digita número nem nome.
import { type FatoDaBase, fatosDaBase } from "../conteudo";
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

export function Cruzamentos() {
  const { fatos, medido_em_curto } = fatosDaBase;
  return (
    <section
      className="faixa secao v2-cruzamentos"
      id="cruzamentos"
      aria-labelledby="titulo-cruzamentos"
    >
      <p className="olho">Cruzamentos</p>
      <h2 id="titulo-cruzamentos">O que só aparece juntando fontes</h2>
      <p className="subtitulo">
        {`Contagens da base inteira, medidas em ${medido_em_curto}, sem nome de empresa. Cada número diz de onde veio e como foi contado.`}
      </p>
      <div className="grade v2-fatos">
        {fatos.map((fato) => (
          <Fato key={fato.chave} fato={fato} />
        ))}
      </div>
    </section>
  );
}
