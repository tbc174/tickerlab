// Gráfico de linha em SVG, sem biblioteca: curvas em base 100 ao longo do tempo (uma série agora;
// até 5 na comparação). Linha de 2px, grade discreta, referência em 100, mira vertical que gruda no
// pregão mais próximo (mouse, toque ou setas do teclado) e uma dica com o dia e o valor de cada série.
// O eixo x é por pregão (sem buracos nos fins de semana). Textos vêm como texto do React (nada de HTML).
import { type KeyboardEvent, type PointerEvent, useId, useMemo, useState } from "react";
import { formatarData } from "../formatar";

export interface Serie {
  nome: string;
  cor: string; // uma variável da marca: "var(--azul)"
  valores: (number | null)[];
}

interface Propriedades {
  titulo: string; // nomeia o gráfico para leitores de tela (e a série, quando é uma só)
  datas: string[]; // "AAAA-MM-DD", uma por ponto
  series: Serie[];
  referencia?: number; // a linha de base (100)
  formatarValor?: (valor: number) => string;
}

const LARGURA = 720;
const ALTURA = 260;
const MARGEM = { topo: 12, direita: 16, baixo: 28, esquerda: 48 };
const LINHAS_DA_GRADE = 4;
const MARCAS_DE_DATA = 5;

function arredondar(valor: number): string {
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

/** Um passo "redondo" (1, 2, 2,5 ou 5 × 10^n) que divide a faixa em ~`partes`. */
function passoRedondo(faixa: number, partes: number): number {
  const bruto = faixa / partes;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const fator = [1, 2, 2.5, 5, 10].find((f) => f * potencia >= bruto) ?? 10;
  return fator * potencia;
}

export function limitesDoEixo(valores: number[], referencia?: number): [number, number, number] {
  const todos = referencia === undefined ? valores : [...valores, referencia];
  const minimo = Math.min(...todos);
  const maximo = Math.max(...todos);
  const passo = passoRedondo(maximo - minimo || 1, LINHAS_DA_GRADE);
  return [Math.floor(minimo / passo) * passo, Math.ceil(maximo / passo) * passo, passo];
}

export function GraficoDeLinha({
  titulo,
  datas,
  series,
  referencia,
  formatarValor = arredondar,
}: Propriedades) {
  const [indice, setIndice] = useState<number | null>(null);
  const idDoResumo = useId();
  const valores = useMemo(
    () => series.flatMap((s) => s.valores.filter((v): v is number => v !== null)),
    [series],
  );
  if (datas.length < 2 || valores.length === 0) return null;

  const [baixo, alto, passo] = limitesDoEixo(valores, referencia);
  const largura = LARGURA - MARGEM.esquerda - MARGEM.direita;
  const altura = ALTURA - MARGEM.topo - MARGEM.baixo;
  const x = (i: number) => MARGEM.esquerda + (i / (datas.length - 1)) * largura;
  const y = (v: number) => MARGEM.topo + (1 - (v - baixo) / (alto - baixo)) * altura;

  const caminho = (serie: Serie) =>
    serie.valores
      .map((v, i) => (v === null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`))
      .reduce<string>((d, ponto, i, todos) => {
        if (ponto === null) return d;
        return `${d}${i === 0 || todos[i - 1] === null ? "M" : "L"}${ponto}`;
      }, "");

  const grade: number[] = [];
  for (let v = baixo; v <= alto + passo / 2; v += passo) grade.push(v);
  const marcasDeData = Array.from({ length: MARCAS_DE_DATA }, (_, k) =>
    Math.round((k / (MARCAS_DE_DATA - 1)) * (datas.length - 1)),
  );

  const apontar = (evento: PointerEvent<SVGSVGElement>) => {
    const caixa = evento.currentTarget.getBoundingClientRect();
    const naEscala = ((evento.clientX - caixa.left) / (caixa.width || 1)) * LARGURA;
    const relativo = (naEscala - MARGEM.esquerda) / largura;
    setIndice(Math.min(datas.length - 1, Math.max(0, Math.round(relativo * (datas.length - 1)))));
  };
  const andar = (evento: KeyboardEvent<SVGSVGElement>) => {
    const passos: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, Home: -datas.length, End: datas.length };
    if (!(evento.key in passos)) return;
    evento.preventDefault();
    const atual = indice ?? datas.length - 1;
    setIndice(Math.min(datas.length - 1, Math.max(0, atual + passos[evento.key])));
  };

  const ultimo = (s: Serie) => [...s.valores].reverse().find((v) => v !== null) ?? null;
  const resumo = series
    .map((s) => {
      const fim = ultimo(s);
      return `${s.nome}: de ${formatarData(datas[0])} a ${formatarData(datas[datas.length - 1])}, termina em ${fim === null ? "—" : formatarValor(fim)}`;
    })
    .join(". ");

  return (
    <figure className="grafico">
      <svg
        viewBox={`0 0 ${LARGURA} ${ALTURA}`}
        role="img"
        aria-label={titulo}
        aria-describedby={idDoResumo}
        tabIndex={0}
        onPointerMove={apontar}
        onPointerDown={apontar}
        onPointerLeave={() => setIndice(null)}
        onKeyDown={andar}
        onBlur={() => setIndice(null)}
      >
        {grade.map((v) => (
          <g key={v} className="grafico-grade">
            <line x1={MARGEM.esquerda} x2={LARGURA - MARGEM.direita} y1={y(v)} y2={y(v)} />
            <text x={MARGEM.esquerda - 8} y={y(v)} dy="0.32em" textAnchor="end">
              {formatarValor(v)}
            </text>
          </g>
        ))}
        {referencia !== undefined ? (
          <line
            className="grafico-referencia"
            x1={MARGEM.esquerda}
            x2={LARGURA - MARGEM.direita}
            y1={y(referencia)}
            y2={y(referencia)}
          />
        ) : null}
        {marcasDeData.map((i) => (
          <text
            key={i}
            className="grafico-eixo-x"
            x={x(i)}
            y={ALTURA - 8}
            textAnchor={i === 0 ? "start" : i === datas.length - 1 ? "end" : "middle"}
          >
            {formatarData(datas[i])}
          </text>
        ))}
        {series.map((s) => (
          <path key={s.nome} className="grafico-linha" d={caminho(s)} stroke={s.cor} data-serie={s.nome} />
        ))}
        {indice !== null ? (
          <g className="grafico-mira">
            <line x1={x(indice)} x2={x(indice)} y1={MARGEM.topo} y2={ALTURA - MARGEM.baixo} />
            {series.map((s) => {
              const v = s.valores[indice];
              return v === null ? null : (
                <circle key={s.nome} cx={x(indice)} cy={y(v)} r={4} fill={s.cor} />
              );
            })}
          </g>
        ) : null}
      </svg>
      {indice !== null ? (
        <div
          className="grafico-dica"
          role="status"
          style={{ left: `${(x(indice) / LARGURA) * 100}%` }}
        >
          <strong>{formatarData(datas[indice])}</strong>
          {series.map((s) => {
            const v = s.valores[indice];
            return (
              <span key={s.nome}>
                <i style={{ background: s.cor }} aria-hidden="true" />
                {s.nome}: {v === null ? "—" : formatarValor(v)}
              </span>
            );
          })}
        </div>
      ) : null}
      <figcaption id={idDoResumo} className="apagado">
        {resumo}.
      </figcaption>
    </figure>
  );
}
