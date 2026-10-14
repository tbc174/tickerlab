// Barras horizontais para comparar opções (renda fixa, cenários, ativos): o nome à esquerda, a barra
// saindo do zero (para a direita se positiva, para a esquerda se negativa) e o valor escrito na
// ponta. A ordem é a que vem (nada de ordenar do "melhor" ao "pior"). Cores só da marca.
import { limitesDoEixo } from "./escala";
import { SERIES } from "./cores";
import { useLargura } from "./useLargura";

export interface Barra {
  nome: string;
  valor: number;
  cor?: string; // padrão: a 1ª cor das séries
}

const ESPESSURA = 20;
const LINHA = 34;
const ESPACO_DO_VALOR = 96;

export function GraficoDeBarras({
  titulo,
  barras,
  formatarValor,
}: {
  titulo: string;
  barras: Barra[];
  formatarValor: (valor: number) => string;
}) {
  const [largura, medir] = useLargura(560);
  const colunaDoNome = Math.min(180, Math.round(largura * 0.36));
  const altura = barras.length * LINHA + 8;
  const valores = barras.map((b) => b.valor);
  const [baixo, alto] = limitesDoEixo(valores, 0);
  const negativos = baixo < 0;
  const inicio = colunaDoNome + (negativos ? ESPACO_DO_VALOR : 0);
  const fim = largura - ESPACO_DO_VALOR;
  const x = (valor: number) => inicio + ((valor - baixo) / (alto - baixo || 1)) * Math.max(1, fim - inicio);
  const zero = x(0);

  return (
    <figure className="grafico-ferramenta" ref={medir}>
      <svg width={largura} height={altura} viewBox={`0 0 ${largura} ${altura}`} role="img" aria-label={titulo}>
        <line className="grafico-ferramenta-zero" data-zero="" x1={zero} x2={zero} y1={0} y2={altura} />
        {barras.map((b, k) => {
          const meio = k * LINHA + LINHA / 2 + 4;
          const ponta = x(b.valor);
          const esquerda = Math.min(ponta, zero);
          const texto = formatarValor(b.valor);
          return (
            <g key={b.nome} className="grafico-ferramenta-barra">
              <title>{`${b.nome}: ${texto}`}</title>
              <text className="grafico-ferramenta-nome" x={0} y={meio} dy="0.32em">
                {b.nome}
              </text>
              <rect
                data-barra=""
                x={esquerda}
                y={meio - ESPESSURA / 2}
                width={Math.max(1, Math.abs(ponta - zero))}
                height={ESPESSURA}
                rx={4}
                fill={b.cor ?? SERIES[0]}
              />
              <text
                className="grafico-ferramenta-valor"
                x={b.valor < 0 ? ponta - 6 : ponta + 6}
                y={meio}
                dy="0.32em"
                textAnchor={b.valor < 0 ? "end" : "start"}
              >
                {texto}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="so-para-leitor">
        {titulo}. {barras.map((b) => `${b.nome}: ${formatarValor(b.valor)}`).join("; ")}.
      </figcaption>
    </figure>
  );
}
