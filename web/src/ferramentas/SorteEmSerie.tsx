// Sorte em série (contas/sorte_em_serie.ts, a mesma conta do Python): estratégias de cara ou coroa,
// e a melhor parece genial. Leva à ficha "Foi sorte?", que desconta as tentativas.
import { useState } from "react";
import { Escolha, Resultado } from "./campos";
import { type ResultadoDaSorte, simular } from "./contas/sorte_em_serie";
import { formatarDecimal } from "../app/formatar";
import { formatarNumero, formatarPorcentagem } from "./numeros";

export const SEMENTE_INICIAL = 42;
const DIAS_POR_ANO_DE_PREGAO = 250; // dias de pregão num ano, para o prazo da simulação

type Quantidade = "10" | "100" | "1000";
type Anos = "1" | "3" | "5";

const LARGURA = 600;
const ALTURA = 220;
const CURVAS: [keyof ResultadoDaSorte, string, string][] = [
  ["curva_da_melhor", "A melhor", "var(--azul)"],
  ["curva_da_mediana", "A do meio", "var(--apagado)"],
  ["curva_da_pior", "A pior", "var(--queda)"],
];

/** A altura no desenho de um valor, com a escala comum às três curvas (o maior fica no alto). */
const alturaNoDesenho = (minimo: number, maximo: number) => (valor: number) =>
  ALTURA - ((valor - minimo) / (maximo - minimo || 1)) * ALTURA;

function pontos(curva: number[], altura: (valor: number) => number): string {
  const passo = LARGURA / (curva.length - 1);
  return curva.map((v, i) => `${(i * passo).toFixed(1)},${altura(v).toFixed(1)}`).join(" ");
}

export function GraficoDaSorte({ resultado }: { resultado: ResultadoDaSorte }) {
  const todas = CURVAS.flatMap(([chave]) => resultado[chave] as number[]);
  const altura = alturaNoDesenho(Math.min(...todas), Math.max(...todas));
  const base = altura(1).toFixed(1); // o valor do começo
  return (
    <figure className="ferramenta-grafico">
      <svg viewBox={`0 0 ${LARGURA} ${ALTURA}`} role="img" aria-label="Patrimônio da melhor, da do meio e da pior estratégia, dia a dia">
        <line x1="0" x2={LARGURA} y1={base} y2={base} className="ferramenta-grafico-base" />
        {CURVAS.map(([chave, , cor]) => (
          <polyline key={chave} points={pontos(resultado[chave] as number[], altura)} fill="none" stroke={cor} strokeWidth="2" />
        ))}
      </svg>
      <figcaption>
        {CURVAS.map(([chave, nome, cor]) => (
          <span key={chave}>
            <i style={{ background: cor }} aria-hidden="true" /> {nome}
          </span>
        ))}
        <span className="apagado">linha fina: o valor do começo</span>
      </figcaption>
    </figure>
  );
}

export function SorteEmSerie() {
  const [quantidade, setQuantidade] = useState<Quantidade>("100");
  const [anos, setAnos] = useState<Anos>("1");
  const [semente, setSemente] = useState(SEMENTE_INICIAL);
  const r = simular(Number(quantidade), Number(anos) * DIAS_POR_ANO_DE_PREGAO, semente);
  const total = formatarNumero(r.estrategias);
  return (
    <div className="ferramenta">
      <form className="ferramenta-campos" onSubmit={(evento) => evento.preventDefault()}>
        <p>
          Cada estratégia ganha ou perde 1% por dia no cara ou coroa. Nenhuma tem vantagem: todas
          são moeda.
        </p>
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Quantas estratégias</span>
          <Escolha
            rotulo="Quantas estratégias"
            valor={quantidade}
            opcoes={[
              ["10", "10"],
              ["100", "100"],
              ["1000", "1.000"],
            ]}
            aoMudar={setQuantidade}
          />
        </div>
        <div className="ferramenta-campo">
          <span className="ferramenta-rotulo">Por quanto tempo</span>
          <Escolha
            rotulo="Por quanto tempo"
            valor={anos}
            opcoes={[
              ["1", "1 ano"],
              ["3", "3 anos"],
              ["5", "5 anos"],
            ]}
            aoMudar={setAnos}
          />
        </div>
        <button className="botao secundario" type="button" onClick={() => setSemente((s) => s + 1)}>
          Sortear de novo
        </button>
      </form>
      <Resultado rotulo={`A melhor de ${total}`} principal={formatarPorcentagem(r.retorno_da_melhor)} erro={null}>
        <dl className="ferramenta-numeros">
          <div>
            <dt>Sharpe da melhor</dt>
            <dd>{formatarDecimal(r.sharpe_da_melhor)}</dd>
          </div>
          <div>
            <dt>Com Sharpe acima de 1</dt>
            <dd>
              {formatarNumero(r.com_sharpe_acima_de_1)} de {total}
            </dd>
          </div>
          <div>
            <dt>Terminaram no lucro</dt>
            <dd>
              {formatarNumero(r.lucraram)} de {total}
            </dd>
          </div>
          <div>
            <dt>A do meio terminou em</dt>
            <dd>{formatarPorcentagem(r.retorno_da_mediana)}</dd>
          </div>
        </dl>
        <GraficoDaSorte resultado={r} />
      </Resultado>
    </div>
  );
}
