// Mapa de municípios em SVG, desenhado aqui a partir do GeoJSON da malha do IBGE: sem biblioteca de
// mapa nem fundo de outro serviço (sem token, sem custo, leve no celular). Quem usa diz a cor e o
// texto de cada município; o clique escolhe um.
import { useMemo } from "react";
import type { MalhaDoMapa } from "../tipos";

const LARGURA = 640;
type Ponto = [number, number];

function aneis(geometria: { type: string; coordinates: unknown }): Ponto[][] {
  if (geometria.type === "Polygon") return geometria.coordinates as Ponto[][];
  if (geometria.type === "MultiPolygon") return (geometria.coordinates as Ponto[][][]).flat();
  return [];
}

/** Os contornos em coordenadas da tela: longitude × cos(latitude média), latitude invertida. */
export function desenharMalha(malha: MalhaDoMapa) {
  const feicoes = malha.features.map((f) => ({ codigo: f.properties.codarea ?? "", aneis: aneis(f.geometry) }));
  let [x0, x1, y0, y1] = [Infinity, -Infinity, Infinity, -Infinity];
  for (const f of feicoes) // laço, não Math.min(...): a malha inteira tem pontos demais para a pilha
    for (const anel of f.aneis)
      for (const [x, y] of anel) {
        x0 = Math.min(x0, x);
        x1 = Math.max(x1, x);
        y0 = Math.min(y0, y);
        y1 = Math.max(y1, y);
      }
  const caminhos = new Map<string, string>();
  if (!Number.isFinite(x0)) return { altura: 0, caminhos };
  const fator = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
  const escala = LARGURA / Math.max((x1 - x0) * fator, 1e-9);
  const ponto = ([x, y]: Ponto) => `${((x - x0) * fator * escala).toFixed(1)},${((y1 - y) * escala).toFixed(1)}`;
  for (const f of feicoes) caminhos.set(f.codigo, f.aneis.map((anel) => `M${anel.map(ponto).join("L")}Z`).join(""));
  return { altura: Math.max((y1 - y0) * escala, 1), caminhos };
}

interface Propriedades {
  malha: MalhaDoMapa;
  rotulo: string;
  corDe: (codigo: string) => string;
  textoDe: (codigo: string) => string; // o que aparece ao passar o mouse
  semDado: (codigo: string) => boolean;
  escolhido: string;
  aoEscolher: (codigo: string) => void;
}

export function MapaDeMunicipios({ malha, rotulo, corDe, textoDe, semDado, escolhido, aoEscolher }: Propriedades) {
  const desenho = useMemo(() => desenharMalha(malha), [malha]);
  if (desenho.caminhos.size === 0) return null;
  return (
    <svg
      className="mapa-de-municipios"
      viewBox={`0 0 ${LARGURA} ${Math.ceil(desenho.altura) + 1}`}
      role="img"
      aria-label={rotulo}
    >
      {[...desenho.caminhos].map(([codigo, d]) => (
        <path
          key={codigo}
          d={d}
          fill={corDe(codigo)}
          className={[semDado(codigo) ? "sem-dado" : "", codigo === escolhido ? "escolhido" : ""].join(" ").trim()}
          data-codigo={codigo}
          onClick={() => aoEscolher(codigo)}
        >
          <title>{textoDe(codigo)}</title>
        </path>
      ))}
    </svg>
  );
}
