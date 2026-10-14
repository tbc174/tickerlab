// Gráfico das ferramentas ao longo do tempo (eixo x em meses): linhas, ou áreas empilhadas ("o que
// você pôs" embaixo, "juros" em cima). Desenhado em pixels reais (useLargura), com grade discreta,
// eixos redondos (escala.ts), mira com mouse, toque e teclado, dica, legenda a partir de duas séries
// e um resumo para leitor de tela. Cores só das variáveis da marca; texto nunca na cor da série.
import { useId } from "react";
import { limitesDoEixo, marcasDeMeses, rotuloDaDica, rotuloDoMes } from "./escala";
import { useLargura } from "./useLargura";
import { useMira } from "./useMira";

export interface SerieNoTempo {
  nome: string;
  cor: string; // uma de SERIES (cores.ts)
  valores: number[]; // um por mês de `meses`
}

const ALTURA = 240;
const ALTURA_NO_CELULAR = 200;
const CELULAR = 480;
const MARGEM = { topo: 14, direita: 14, baixo: 28, esquerda: 70 };

/** As camadas acumuladas: a 2ª fica em cima da 1ª, a 3ª em cima das duas... */
export function empilhar(camadas: number[][]): number[][] {
  return camadas.map((_, k) => camadas[0].map((__, i) => camadas.slice(0, k + 1).reduce((soma, c) => soma + c[i], 0)));
}

export function GraficoDoTempo({
  titulo,
  meses,
  series,
  formatarValor,
  formatarEixo = formatarValor,
  empilhado = false,
  zeroNaBase = empilhado,
  referencia,
}: {
  titulo: string; // nomeia o gráfico para leitores de tela
  meses: number[]; // o mês de cada ponto, desde o início (0, 1, 2... ou 0, 12, 24...)
  series: SerieNoTempo[];
  formatarValor: (valor: number) => string;
  formatarEixo?: (valor: number) => string;
  empilhado?: boolean;
  zeroNaBase?: boolean;
  referencia?: { valor: number; rotulo: string }; // uma linha horizontal com nome (a meta)
}) {
  const [largura, medir] = useLargura(640);
  const idDoResumo = useId();
  const celular = largura < CELULAR;
  const altura = celular ? ALTURA_NO_CELULAR : ALTURA;
  const ultimoMes = meses[meses.length - 1] || 1;
  const larguraUtil = Math.max(1, largura - MARGEM.esquerda - MARGEM.direita);
  const alturaUtil = altura - MARGEM.topo - MARGEM.baixo;
  const mira = useMira(meses.length, (xNoDesenho) => {
    const mes = ((xNoDesenho - MARGEM.esquerda) / larguraUtil) * ultimoMes;
    let melhor = 0;
    meses.forEach((m, i) => {
      if (Math.abs(m - mes) < Math.abs(meses[melhor] - mes)) melhor = i;
    });
    return melhor;
  });

  const topos = empilhado ? empilhar(series.map((s) => s.valores)) : series.map((s) => s.valores);
  const todos = referencia ? [...topos.flat(), referencia.valor] : topos.flat();
  const [baixo, alto, passo] = limitesDoEixo(todos, zeroNaBase ? 0 : undefined);
  const x = (mes: number) => MARGEM.esquerda + (mes / ultimoMes) * larguraUtil;
  const y = (valor: number) => MARGEM.topo + (1 - (valor - baixo) / (alto - baixo)) * alturaUtil;
  const linha = (valores: number[]) =>
    valores.map((v, i) => `${i === 0 ? "M" : "L"}${x(meses[i]).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = (de: number[], ate: number[]) => {
    const volta = [...de].reverse().map((v, k) => `L${x(meses[de.length - 1 - k]).toFixed(1)},${y(v).toFixed(1)}`);
    return `${linha(ate)}${volta.join("")}Z`;
  };
  const piso = meses.map(() => Math.max(baixo, 0));

  const grade: number[] = [];
  for (let v = baixo; v <= alto + passo / 2; v += passo) grade.push(v);
  const marcas = marcasDeMeses(ultimoMes, celular ? 4 : 6);
  const i = mira.indice;
  const resumo = series
    .map((s) => `${s.nome}: começa em ${formatarValor(s.valores[0])} e termina em ${formatarValor(s.valores[s.valores.length - 1])}`)
    .join("; ");

  return (
    <figure className="grafico-ferramenta" ref={medir}>
      <svg
        width={largura}
        height={altura}
        viewBox={`0 0 ${largura} ${altura}`}
        role="img"
        aria-label={titulo}
        aria-describedby={idDoResumo}
        tabIndex={0}
        onPointerMove={mira.apontar}
        onPointerDown={mira.apontar}
        onPointerLeave={mira.sair}
        onBlur={mira.sair}
        onKeyDown={mira.teclar}
      >
        {grade.map((v) => (
          <g key={v} className="grafico-ferramenta-grade">
            <line x1={MARGEM.esquerda} x2={largura - MARGEM.direita} y1={y(v)} y2={y(v)} />
            <text x={MARGEM.esquerda - 8} y={y(v)} dy="0.32em" textAnchor="end">
              {formatarEixo(v)}
            </text>
          </g>
        ))}
        {marcas.map((m) => (
          <text
            key={m}
            className="grafico-ferramenta-eixo-x"
            x={x(m)}
            y={altura - 8}
            textAnchor={m === 0 ? "start" : m === ultimoMes ? "end" : "middle"}
          >
            {rotuloDoMes(m, ultimoMes)}
          </text>
        ))}
        {referencia ? (
          <g className="grafico-ferramenta-referencia" data-meta={referencia.valor}>
            <line x1={MARGEM.esquerda} x2={largura - MARGEM.direita} y1={y(referencia.valor)} y2={y(referencia.valor)} />
            <text x={MARGEM.esquerda + 6} y={y(referencia.valor) - 6}>
              {referencia.rotulo}: {formatarValor(referencia.valor)}
            </text>
          </g>
        ) : null}
        {series.map((s, k) => {
          const topo = topos[k];
          const base = empilhado && k > 0 ? topos[k - 1] : piso;
          return (
            <g key={s.nome} className="grafico-ferramenta-serie">
              {empilhado || series.length === 1 ? (
                <path className="grafico-ferramenta-area" d={area(base, topo)} fill={s.cor} />
              ) : null}
              <path className="grafico-ferramenta-linha" d={linha(topo)} stroke={s.cor} fill="none" />
              <circle
                className="grafico-ferramenta-ponta"
                cx={x(ultimoMes)}
                cy={y(topo[topo.length - 1])}
                r={4}
                fill={s.cor}
                data-fim={topo[topo.length - 1]}
              />
            </g>
          );
        })}
        {i !== null ? (
          <g className="grafico-ferramenta-mira">
            <line x1={x(meses[i])} x2={x(meses[i])} y1={MARGEM.topo} y2={altura - MARGEM.baixo} />
            {series.map((s, k) => (
              <circle key={s.nome} cx={x(meses[i])} cy={y(topos[k][i])} r={4} fill={s.cor} />
            ))}
          </g>
        ) : null}
      </svg>
      {i !== null ? (
        <div
          className="grafico-ferramenta-dica"
          role="status"
          style={{ left: `${Math.min(85, Math.max(15, (x(meses[i]) / largura) * 100))}%` }}
        >
          <strong>{rotuloDaDica(meses[i], ultimoMes)}</strong>
          {[...series].reverse().map((s) => (
            <span key={s.nome}>
              <i style={{ background: s.cor }} aria-hidden="true" />
              {s.nome}: {formatarValor(s.valores[i])}
            </span>
          ))}
          {empilhado && series.length > 1 ? <span>Total: {formatarValor(topos[topos.length - 1][i])}</span> : null}
        </div>
      ) : null}
      {series.length > 1 ? (
        <ul className="grafico-ferramenta-legenda" aria-hidden="true">
          {series.map((s) => (
            <li key={s.nome}>
              <i style={{ background: s.cor }} />
              {s.nome}
            </li>
          ))}
        </ul>
      ) : null}
      <figcaption id={idDoResumo} className="so-para-leitor">
        {titulo}. {resumo}.
      </figcaption>
    </figure>
  );
}
