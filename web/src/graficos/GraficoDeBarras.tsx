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
const LINHA_COMPACTA = 52; // o nome em cima da barra
const LARGURA_COMPACTA = 520; // abaixo disso, o nome vai para cima da barra
const ESPACO_DO_VALOR = 96;
const COLUNA_DO_NOME = 180;

/** Onde as barras podem ir: depois da coluna do nome (ou com o nome em cima, em tela estreita) e
 * deixando espaço para o valor na ponta (dos dois lados, se houver valor negativo). */
export function geometriaDasBarras(largura: number, temNegativos: boolean) {
  const compacto = largura < LARGURA_COMPACTA;
  const espacoDoValor = Math.min(ESPACO_DO_VALOR, Math.round(largura * 0.2));
  const colunaDoNome = compacto ? 0 : Math.min(COLUNA_DO_NOME, Math.round(largura * 0.3));
  return {
    compacto,
    inicio: colunaDoNome + (temNegativos ? espacoDoValor : 0),
    fim: largura - espacoDoValor,
  };
}

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
  const valores = barras.map((b) => b.valor);
  const [baixo, alto] = limitesDoEixo(valores, 0);
  const { compacto, inicio, fim } = geometriaDasBarras(largura, baixo < 0);
  const linha = compacto ? LINHA_COMPACTA : LINHA;
  const altura = barras.length * linha + 8;
  const x = (valor: number) => inicio + ((valor - baixo) / (alto - baixo || 1)) * Math.max(1, fim - inicio);
  const zero = x(0);

  return (
    <figure className="grafico-ferramenta" ref={medir}>
      <svg width={largura} height={altura} viewBox={`0 0 ${largura} ${altura}`} role="img" aria-label={titulo}>
        <line className="grafico-ferramenta-zero" data-zero="" x1={zero} x2={zero} y1={0} y2={altura} />
        {barras.map((b, k) => {
          // em tela estreita, o nome fica numa linha própria em cima da barra
          const meio = k * linha + (compacto ? linha - ESPESSURA / 2 - 4 : linha / 2 + 4);
          const ponta = x(b.valor);
          const esquerda = Math.min(ponta, zero);
          const texto = formatarValor(b.valor);
          return (
            <g key={b.nome} className="grafico-ferramenta-barra">
              <title>{`${b.nome}: ${texto}`}</title>
              <text className="grafico-ferramenta-nome" x={0} y={compacto ? meio - ESPESSURA / 2 - 6 : meio} dy={compacto ? 0 : "0.32em"}>
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
