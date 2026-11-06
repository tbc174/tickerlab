// Régua de posição ("Foi sorte?"): onde a data escolhida ficou entre todas as datas de início com o
// mesmo prazo. A régua é de posição (percentil), não de valor: a pior na ponta esquerda, a mediana no
// meio, a melhor na ponta direita e a sua no percentil dela. Com retornos muito tortos (o Ibovespa
// tem janelas de -30% e de +60.000%), uma régua de valor espremeria quase tudo num canto. Só números
// soltos (ADR 0070): nada de série.
import { useLargura } from "./useLargura";

const ALTURA = 92;
const MARGEM = 14;
const Y_DA_REGUA = 40;

export function FaixaDePosicao({
  titulo,
  pior,
  mediana,
  melhor,
  sua,
  abaixoDaSua,
  formatarValor,
}: {
  titulo: string;
  pior: number;
  mediana: number;
  melhor: number;
  sua: number;
  abaixoDaSua: number; // das outras janelas, a fração que daria menos (0 = a pior, 1 = a melhor)
  formatarValor: (valor: number) => string;
}) {
  const [largura, medir] = useLargura(560);
  const x = (posicao: number) => MARGEM + posicao * Math.max(1, largura - 2 * MARGEM);
  const marcas: [string, number, number, string][] = [
    ["pior", 0, pior, "A pior"],
    ["mediana", 0.5, mediana, "A do meio"],
    ["melhor", 1, melhor, "A melhor"],
  ];
  const porcentagem = Math.round(abaixoDaSua * 100);
  return (
    <figure className="grafico-ferramenta faixa-de-posicao" ref={medir}>
      <svg width={largura} height={ALTURA} viewBox={`0 0 ${largura} ${ALTURA}`} role="img" aria-label={titulo}>
        <line className="faixa-de-posicao-regua" x1={x(0)} x2={x(1)} y1={Y_DA_REGUA} y2={Y_DA_REGUA} />
        {marcas.map(([nome, posicao, valor, rotulo]) => (
          <g key={nome} data-marca={nome} data-posicao={posicao}>
            <line className="faixa-de-posicao-marca" x1={x(posicao)} x2={x(posicao)} y1={Y_DA_REGUA - 6} y2={Y_DA_REGUA + 6} />
            <text x={x(posicao)} y={Y_DA_REGUA + 24} textAnchor={posicao === 0 ? "start" : posicao === 1 ? "end" : "middle"}>
              {rotulo}
            </text>
            <text
              className="grafico-ferramenta-valor"
              x={x(posicao)}
              y={Y_DA_REGUA + 40}
              textAnchor={posicao === 0 ? "start" : posicao === 1 ? "end" : "middle"}
            >
              {formatarValor(valor)}
            </text>
          </g>
        ))}
        <g data-marca="sua" data-posicao={abaixoDaSua}>
          <circle className="faixa-de-posicao-sua" cx={x(abaixoDaSua)} cy={Y_DA_REGUA} r={8} />
          <text
            className="grafico-ferramenta-valor"
            x={x(abaixoDaSua)}
            y={Y_DA_REGUA - 16}
            textAnchor={abaixoDaSua < 0.15 ? "start" : abaixoDaSua > 0.85 ? "end" : "middle"}
          >
            A sua: {formatarValor(sua)}
          </text>
        </g>
      </svg>
      <figcaption className="so-para-leitor">
        {titulo}. {porcentagem}% das outras datas dariam menos que a sua. A pior daria {formatarValor(pior)}, a do meio{" "}
        {formatarValor(mediana)} e a melhor {formatarValor(melhor)}.
      </figcaption>
    </figure>
  );
}
