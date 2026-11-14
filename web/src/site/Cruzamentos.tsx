// Os cruzamentos da página inicial (plano do site para quem analisa, PR 6, tarefa 10; empresas fechadas
// desde a linha 925): fatos que só aparecem juntando duas tabelas da base ou mais, agrupados pela pergunta
// que respondem. Os textos, o parágrafo e os grupos vêm prontos de `base/vitrine.py` (`fatos_da_base`),
// com a fonte, a data e a conta recolhida; aqui não se digita número nem nome. O recorte de cada cartão de
// empresa fechada por estado e por setor (2º PR da linha 925) também vem pronto: aqui só se desenham as barras.
import type { CSSProperties } from "react";
import {
  type FatoDaBase,
  type GrupoDeFatos,
  type LadoDoRecorte,
  type RecorteDoFato,
  fatosDaBase,
} from "../conteudo";
import { ComoFoiCalculado } from "./ComoFoiCalculado";

function Lado({ titulo, lado }: { titulo: string; lado: LadoDoRecorte }) {
  return (
    <div className="v2-recorte-lado">
      <p className="v2-recorte-titulo">{titulo}</p>
      <ul className="v2-recorte-barras">
        {lado.barras.map((barra) => (
          <li key={barra.rotulo}>
            <span className="v2-recorte-rotulo">{barra.rotulo}</span>
            <span className="v2-recorte-barra" aria-hidden="true">
              <i style={{ "--p": (barra.largura / 100).toFixed(3) } as CSSProperties} />
            </span>
            <span className="v2-recorte-conta">
              {barra.parte} de {barra.todo} ({barra.porcento})
            </span>
          </li>
        ))}
      </ul>
      {lado.escondidas.length > 0 && (
        <p className="v2-recorte-escondidas">
          Não aparecem, por terem poucas empresas: {lado.escondidas.join(", ")}.
        </p>
      )}
    </div>
  );
}

function Recorte({ recorte }: { recorte: RecorteDoFato }) {
  return (
    <details className="v2-recorte">
      <summary>Por estado e por setor</summary>
      <Lado titulo="Por estado da matriz" lado={recorte.por_uf} />
      <Lado titulo="Por setor da matriz (seção da CNAE)" lado={recorte.por_setor} />
      <p className="v2-recorte-nota">{recorte.como_foi_calculado}</p>
    </details>
  );
}

export function Fato({ fato }: { fato: FatoDaBase }) {
  return (
    <article className="cartao v2-fato" aria-label={`${fato.numero} ${fato.texto}`}>
      <p className="v2-fato-numero">{fato.numero}</p>
      <p className="v2-fato-texto">{fato.texto}</p>
      <p className="v2-fato-fonte">Fonte: {fato.fonte}</p>
      {fato.recorte && <Recorte recorte={fato.recorte} />}
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
