// Histograma: quantos valores caíram em cada faixa (ex.: o retorno final de cada estratégia da sorte
// em série). Barras verticais encostadas, com 2px de folga entre elas, contagem no eixo y e as
// pontas das faixas no eixo x. Cores só da marca.
import { limitesDoEixo } from "./escala";
import { SERIES } from "./cores";
import { useLargura } from "./useLargura";

export interface Faixa {
  de: number;
  ate: number;
  quantas: number;
}

/** Divide do menor ao maior valor em `quantas` faixas iguais; o maior valor fica na última. */
export function faixas(valores: number[], quantas: number): Faixa[] {
  const minimo = Math.min(...valores);
  const maximo = Math.max(...valores);
  if (minimo === maximo) return [{ de: minimo, ate: maximo, quantas: valores.length }];
  const largura = (maximo - minimo) / quantas;
  const lista = Array.from({ length: quantas }, (_, k) => ({
    de: minimo + k * largura,
    ate: k === quantas - 1 ? maximo : minimo + (k + 1) * largura,
    quantas: 0,
  }));
  for (const v of valores) lista[Math.min(quantas - 1, Math.floor((v - minimo) / largura))].quantas++;
  return lista;
}

const ALTURA = 200;
const MARGEM = { topo: 10, direita: 12, baixo: 28, esquerda: 40 };
const FOLGA = 2;

export function GraficoDeHistograma({
  titulo,
  valores,
  quantasFaixas = 20,
  formatarFaixa,
  nomeDaContagem,
}: {
  titulo: string;
  valores: number[];
  quantasFaixas?: number;
  formatarFaixa: (valor: number) => string;
  nomeDaContagem: string; // "estratégias"
}) {
  const [largura, medir] = useLargura(560);
  const lista = faixas(valores, quantasFaixas);
  const [, alto, passo] = limitesDoEixo(lista.map((f) => f.quantas), 0, 4);
  const larguraUtil = Math.max(1, largura - MARGEM.esquerda - MARGEM.direita);
  const alturaUtil = ALTURA - MARGEM.topo - MARGEM.baixo;
  const larguraDaBarra = larguraUtil / lista.length;
  const y = (n: number) => MARGEM.topo + (1 - n / alto) * alturaUtil;
  const grade: number[] = [];
  for (let n = 0; n <= alto + passo / 2; n += passo) grade.push(n);
  const pontas = [0, Math.floor(lista.length / 2), lista.length - 1];
  return (
    <figure className="grafico-ferramenta" ref={medir}>
      <svg width={largura} height={ALTURA} viewBox={`0 0 ${largura} ${ALTURA}`} role="img" aria-label={titulo}>
        {grade.map((n) => (
          <g key={n} className="grafico-ferramenta-grade">
            <line x1={MARGEM.esquerda} x2={largura - MARGEM.direita} y1={y(n)} y2={y(n)} />
            <text x={MARGEM.esquerda - 8} y={y(n)} dy="0.32em" textAnchor="end">
              {n.toLocaleString("pt-BR")}
            </text>
          </g>
        ))}
        {lista.map((f, k) => (
          <rect
            key={k}
            data-quantas={f.quantas}
            x={MARGEM.esquerda + k * larguraDaBarra + FOLGA / 2}
            y={y(f.quantas)}
            width={Math.max(1, larguraDaBarra - FOLGA)}
            height={Math.max(0, y(0) - y(f.quantas))}
            rx={2}
            fill={SERIES[0]}
          >
            <title>{`${formatarFaixa(f.de)} a ${formatarFaixa(f.ate)}: ${f.quantas} ${nomeDaContagem}`}</title>
          </rect>
        ))}
        {pontas.map((k) => (
          <text
            key={k}
            className="grafico-ferramenta-eixo-x"
            x={MARGEM.esquerda + (k + 0.5) * larguraDaBarra}
            y={ALTURA - 8}
            textAnchor={k === 0 ? "start" : k === lista.length - 1 ? "end" : "middle"}
          >
            {formatarFaixa((lista[k].de + lista[k].ate) / 2)}
          </text>
        ))}
      </svg>
      <figcaption className="so-para-leitor">
        {titulo}. {lista.filter((f) => f.quantas).map((f) => `${formatarFaixa(f.de)} a ${formatarFaixa(f.ate)}: ${f.quantas}`).join("; ")}.
      </figcaption>
    </figure>
  );
}
