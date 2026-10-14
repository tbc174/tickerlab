// O CSS das ferramentas grátis do site (calculadoras), por cima de estilo.ts e estilo-v2.ts. Usa só as
// variáveis da marca (--fundo, --superficie, --linha, --azul...), então segue o tema claro e o escuro.
import { marca } from "./conteudo";

// as cores das séries dos gráficos (marca.json, `series`), uma lista por tema; validadas para
// daltonismo e contraste sobre o fundo e a superfície do site (ferramentas v2, 14/10/2026)
const series = (cores: string[]) => cores.map((cor, i) => `--serie-${i + 1}: ${cor};`).join(" ");

export function cssFerramentas(): string {
  return `/* --- ferramentas grátis (plano de 14/10/2026) ---------------------------------------------- */
:root { ${series(marca.paleta_clara.series)} }
:root[data-tema="escuro"] { ${series(marca.paleta_escura.series)} }
.so-para-leitor { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden;
  clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
/* gráficos das ferramentas (web/src/graficos/) */
.grafico-ferramenta { position: relative; margin: 1.25rem 0 0; min-width: 0; }
.grafico-ferramenta svg { display: block; max-width: 100%; height: auto; overflow: visible; touch-action: pan-y; }
.grafico-ferramenta svg:focus-visible { outline: 2px solid var(--azul); outline-offset: 4px; border-radius: 6px; }
.grafico-ferramenta text { fill: var(--apagado); font: 500 12px "Manrope", sans-serif; font-variant-numeric: tabular-nums; }
.grafico-ferramenta-grade line { stroke: var(--linha); stroke-width: 1; }
.grafico-ferramenta-zero { stroke: var(--linha-forte); stroke-width: 1; }
.grafico-ferramenta-linha { stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.grafico-ferramenta-area { opacity: .16; }
.grafico-ferramenta-ponta, .grafico-ferramenta-mira circle { stroke: var(--fundo); stroke-width: 2; }
.grafico-ferramenta-mira line { stroke: var(--linha-forte); stroke-width: 1; }
.grafico-ferramenta .grafico-ferramenta-nome { fill: var(--texto); font-weight: 600; font-size: 13px; }
.grafico-ferramenta .grafico-ferramenta-valor { fill: var(--texto); font-weight: 700; font-size: 13px; }
.grafico-ferramenta-dica { position: absolute; top: 0; transform: translateX(-50%); display: grid; gap: .15rem;
  padding: .5rem .7rem; border-radius: 10px; border: 1px solid var(--linha-forte); background: var(--destaque);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--sombra) 60%, transparent); font-size: .82rem; white-space: nowrap;
  pointer-events: none; font-variant-numeric: tabular-nums; }
.grafico-ferramenta-dica i, .grafico-ferramenta-legenda i { display: inline-block; width: .7rem; height: .7rem;
  border-radius: 3px; margin-right: .4rem; vertical-align: -.05rem; }
.grafico-ferramenta-legenda { display: flex; flex-wrap: wrap; gap: .3rem 1rem; margin: .5rem 0 0; padding: 0;
  list-style: none; font-size: .85rem; color: var(--apagado); }
.ferramenta { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1.5rem; align-items: start;
  padding: clamp(1rem, 3vw, 1.75rem); border: 1px solid var(--linha); border-radius: var(--raio);
  background: var(--superficie); box-shadow: 0 12px 40px color-mix(in srgb, var(--sombra) 35%, transparent); }
.ferramenta-campos { display: grid; gap: 1rem; margin: 0; }
.ferramenta-campo { display: grid; gap: .35rem; margin: 0; border: 0; padding: 0; min-width: 0; }
.ferramenta-campo > label, .ferramenta-campo > legend { font-weight: 700; font-size: .92rem; padding: 0; }
.ferramenta-campo small { font-size: .82rem; }
.ferramenta-entrada { display: flex; align-items: center; gap: .5rem; min-width: 0; }
.ferramenta-entrada > span { color: var(--apagado); font-weight: 600; }
.ferramenta input[type="text"], .ferramenta select { min-width: 0; padding: .65rem .8rem; border-radius: 10px;
  border: 1px solid var(--linha-forte); background: var(--fundo); color: var(--texto); font: 500 1rem "Manrope", sans-serif;
  transition: border-color 160ms ease, box-shadow 160ms ease; }
.ferramenta input[type="text"] { flex: 1; font-variant-numeric: tabular-nums; }
.ferramenta input[type="text"]:focus, .ferramenta select:focus { border-color: var(--azul); outline: none;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--azul) 35%, transparent); }
.ferramenta-deslizante { width: 100%; margin: .35rem 0 0; accent-color: var(--azul); cursor: pointer; }
.ferramenta-atalhos { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .3rem; }
.ferramenta-atalhos button { padding: .25rem .65rem; border-radius: 999px; border: 1px solid var(--linha-forte);
  background: var(--fundo); color: var(--texto); font: 600 .8rem "Manrope", sans-serif; cursor: pointer; }
.ferramenta-atalhos button:hover, .ferramenta-atalhos button:focus-visible { border-color: var(--azul); color: var(--azul-texto); }
.ferramenta-alternativas { display: flex; flex-wrap: wrap; gap: .4rem .9rem; }
.ferramenta-alternativas legend { width: 100%; margin-bottom: .35rem; }
.ferramenta-alternativas label { display: inline-flex; align-items: center; gap: .35rem; cursor: pointer; }
.ferramenta-alternativas input { accent-color: var(--azul); }
.ferramenta-resultado { position: sticky; top: 5.5rem; padding: 1.25rem; border-radius: var(--raio);
  background: var(--fundo); border: 1px solid var(--linha); min-width: 0; }
.ferramenta-principal { margin: 0 0 1rem; font-size: clamp(1.8rem, 4vw, 2.5rem); font-weight: 800; letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums; color: var(--azul-texto); overflow-wrap: anywhere; }
.ferramenta-numeros { display: grid; gap: .6rem; margin: 0; }
.ferramenta-numeros div { display: flex; justify-content: space-between; gap: 1rem; border-top: 1px solid var(--linha); padding-top: .6rem; }
.ferramenta-numeros dt { color: var(--apagado); }
.ferramenta-numeros dd { margin: 0; font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }
.ferramenta-erro { margin: 0; color: var(--atencao); font-weight: 600; }
.ferramenta-tabela { margin-top: 1rem; }
.ferramenta-tabela summary { cursor: pointer; font-weight: 700; color: var(--azul-texto); }
.ferramenta-tabela table { margin-top: .75rem; font-size: .88rem; font-variant-numeric: tabular-nums; }
.ferramenta-tabela td:not(:first-child), .ferramenta-tabela th:not(:first-child) { text-align: right; }
.ferramenta-aviso { margin-top: 1rem; font-size: .9rem; }
.ferramenta-aviso p { margin: .3rem 0; }
.ferramenta-explicacao { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 2rem; align-items: start; }
.ferramenta-texto h2 { font-size: 1.4rem; margin-top: 1.5rem; }
.ferramenta-texto h2:first-child { margin-top: 0; }
.ferramenta-nome { font-size: 1.12rem; }
.ferramenta-rotulo { font-weight: 700; font-size: .92rem; }
.ferramenta-bloco + .ferramenta-bloco { margin-top: 2.5rem; }
.ferramenta-grafico { margin: 1.25rem 0 0; }
.ferramenta-grafico svg { width: 100%; height: auto; display: block; }
.ferramenta-grafico-base { stroke: var(--linha-forte); stroke-width: 1; stroke-dasharray: 4 4; }
.ferramenta-grafico figcaption { display: flex; flex-wrap: wrap; gap: .4rem 1rem; margin-top: .5rem; font-size: .85rem; }
.ferramenta-grafico figcaption i { display: inline-block; width: .9rem; height: .2rem; border-radius: 2px; vertical-align: middle; }
.ferramenta-anteriores { display: grid; gap: 1rem; padding: .8rem 1rem; border: 1px dashed var(--linha-forte); border-radius: 10px; }
.ferramenta-anteriores summary { cursor: pointer; font-weight: 700; color: var(--azul-texto); }
.ferramenta-depois { margin-top: 1.25rem; }
.ferramenta-espera { margin: 0; padding: 1.5rem; }
.ferramenta-data { margin: .75rem 0 0; font-size: .85rem; }
.ferramenta-velho { color: var(--atencao); }
.ferramenta-comparacao { font-variant-numeric: tabular-nums; }
.ferramenta-comparacao td { text-align: right; }
.ferramenta-compartilhar { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; margin-top: 1rem; }
.ferramenta-compartilhar [role="status"] { font-size: .85rem; }
.ferramenta-link-manual { display: grid; gap: .25rem; width: 100%; font-size: .85rem; }
.ferramenta-link-manual input { width: 100%; padding: .5rem .6rem; border-radius: 8px; border: 1px solid var(--linha-forte);
  background: var(--fundo); color: var(--texto); font: 500 .85rem "JetBrains Mono", monospace; }
.anuncio-da-casa { padding: 1.5rem; border-radius: var(--raio); border: 1px solid color-mix(in srgb, var(--azul) 40%, var(--linha));
  background: color-mix(in srgb, var(--azul) 7%, var(--superficie)); }
.anuncio-da-casa h2 { font-size: 1.3rem; }
@media (max-width: 860px) {
  .ferramenta, .ferramenta-explicacao { grid-template-columns: 1fr; }
  .ferramenta-resultado { position: static; }
}
`;
}
