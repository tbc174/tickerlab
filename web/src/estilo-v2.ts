// O visual v2 do site e do app (ADR 0065), por cima do CSS de estilo.ts: hero escuro com o fundo
// "mercado vivo", vidro, bento, painel do número principal, faixa das fontes e as animações (as
// contínuas obedecem ao botão de pausa e ao "reduzir movimento"). Veio do protótipo aprovado em
// 14/10/2026 (C:/Users/tiago/projetos/tickerlab-site-v2/v2.css), com as cores tiradas da marca.
import { marca } from "./conteudo";

const claro = marca.paleta_clara;
const escuro = marca.paleta_escura;
// verde e vermelho só para alta e queda (src/marca.py), um par por tema
const sinal = (p: { alta: string; queda: string }) => `--alta: ${p.alta}; --queda: ${p.queda};`;

export function cssV2(): string {
  return `/* --- visual v2 (ADR 0065) ------------------------------------------------------------- */
:root { ${sinal(claro)} }
:root[data-tema="escuro"], .escura { ${sinal(escuro)} }
.alta { color: var(--alta); }
.queda { color: var(--queda); }

/* tema claro em camadas (Clarix): fundo com um leve degradê, cartões brancos que flutuam */
body { background: radial-gradient(90rem 40rem at 85% -10%, color-mix(in srgb, var(--azul) 7%, transparent), transparent 60%), var(--fundo); }
:root[data-tema="escuro"] body { background: var(--fundo); }

/* topo em pílula de vidro */
.topo { background: transparent; border-bottom: 0; backdrop-filter: none; padding-top: .6rem; }
.topo .faixa { max-width: calc(var(--largura) + 1rem); min-height: 3.6rem; border-radius: 16px;
  background: color-mix(in srgb, var(--fundo) 78%, transparent); backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--linha); box-shadow: 0 8px 30px color-mix(in srgb, var(--sombra) 40%, transparent); }
.topo nav a { position: relative; padding: .3rem .1rem; }
.topo nav a::after { content: ""; position: absolute; left: 0; right: 0; bottom: -2px; height: 2px; border-radius: 2px;
  background: var(--azul); transform: scaleX(0); transition: transform 180ms ease; }
.topo nav a:hover::after { transform: scaleX(1); }

/* hero: fundo marinho com grade fina e horizonte azul (Sora), linha de preço desenhada uma vez */
.v2-heroi-fundo { position: relative; isolation: isolate; margin-top: -4.2rem; padding-top: 4.2rem;
  background: linear-gradient(180deg, #061430 0%, ${marca.marinho} 70%, ${marca.marinho} 100%); }
.v2-grade { position: absolute; inset: 0; z-index: -1; pointer-events: none;
  background-image: linear-gradient(rgba(232, 240, 255, .05) 1px, transparent 1px), linear-gradient(90deg, rgba(232, 240, 255, .05) 1px, transparent 1px);
  background-size: 56px 56px;
  -webkit-mask-image: radial-gradient(70% 60% at 50% 35%, #000 30%, transparent 75%); mask-image: radial-gradient(70% 60% at 50% 35%, #000 30%, transparent 75%); }
.v2-horizonte { position: absolute; left: -10%; right: -10%; bottom: -55%; height: 90%; z-index: -1; pointer-events: none; border-radius: 50%;
  background: radial-gradient(closest-side, rgba(41, 98, 255, .55), rgba(41, 98, 255, .18) 55%, transparent 75%);
  filter: blur(10px); animation: v2-amanhecer 1400ms cubic-bezier(.2, .7, .2, 1) 100ms both; }
@keyframes v2-amanhecer { from { opacity: 0; transform: translateY(40px) scale(.96); } to { opacity: 1; transform: none; } }

.heroi { grid-template-columns: 1.05fr .95fr; }
.heroi h1 { font-size: clamp(2.3rem, 5.4vw, 4.1rem); letter-spacing: -0.04em; }
.v2-degrade { background: linear-gradient(90deg, ${escuro.azul_texto} 0%, #a9c1ff 55%, ${escuro.azul_texto} 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }

.v2-pilula { display: inline-flex; align-items: center; gap: .55rem; margin-bottom: 1.4rem; padding: .35rem .8rem .35rem .6rem;
  border-radius: 999px; border: 1px solid var(--linha-forte); background: rgba(16, 39, 82, .6);
  color: var(--texto); font-size: .86rem; font-weight: 600; text-decoration: none; backdrop-filter: blur(8px);
  transition: border-color 160ms ease; }
.v2-pilula:hover { border-color: var(--azul-texto); }
.v2-ponto { width: 8px; height: 8px; border-radius: 50%; background: ${escuro.atencao}; box-shadow: 0 0 0 4px rgba(245, 184, 61, .18); }
.v2-pilula-seta { color: var(--azul-texto); transition: transform 160ms ease; }
.v2-pilula:hover .v2-pilula-seta { transform: translateX(3px); }

/* painel do número principal (Ledger): vidro escuro, um número grande, o gráfico e três métricas */
.v2-painel-pilha { position: relative; padding: 0 0 2.5rem 0; animation: tl-chegar 700ms cubic-bezier(.2, .7, .2, 1) 220ms both; }
.v2-painel { position: relative; padding: 1.4rem 1.5rem 1.1rem; border-radius: 20px;
  background: linear-gradient(180deg, rgba(22, 49, 96, .72), rgba(10, 31, 68, .72));
  border: 1px solid rgba(232, 240, 255, .14); backdrop-filter: blur(16px);
  box-shadow: 0 40px 90px rgba(0, 0, 0, .45), inset 0 1px 0 rgba(255, 255, 255, .08); }
.v2-painel::before { content: ""; position: absolute; inset: -1px; border-radius: inherit; padding: 1px; pointer-events: none;
  background: linear-gradient(140deg, rgba(110, 149, 255, .7), transparent 40%, transparent 70%, rgba(110, 149, 255, .35));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude; }
.v2-painel-topo { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.v2-painel-topo .ticker { color: var(--apagado); font-weight: 700; }
.v2-etiqueta { display: inline-block; padding: .15rem .6rem; border-radius: 999px; font-size: .72rem; font-weight: 700;
  letter-spacing: .04em; color: var(--azul-texto); background: rgba(41, 98, 255, .14); border: 1px solid rgba(110, 149, 255, .35); }
.v2-etiqueta-ambar { color: ${escuro.atencao}; background: rgba(245, 184, 61, .12); border-color: rgba(245, 184, 61, .4); }
.v2-rotulo { margin: 0; color: var(--apagado); font-size: .85rem; }
.v2-numero { margin: .1rem 0 0; font: 800 clamp(2.4rem, 4.6vw, 3.4rem)/1.05 "Manrope", sans-serif; letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums; }
.v2-apoio { margin: .3rem 0 0; color: var(--apagado); font-size: .92rem; font-variant-numeric: tabular-nums; }
.v2-grafico { display: block; width: 100%; height: 110px; margin: 1rem 0 .4rem; overflow: visible; }
.v2-grafico .area { fill: url(#v2-area); animation: tl-chegar 900ms ease 900ms both; }
.v2-grafico .linha { fill: none; stroke: ${escuro.azul_texto}; stroke-width: 2.2; stroke-linejoin: round; stroke-linecap: round;
  vector-effect: non-scaling-stroke; stroke-dasharray: 1; animation: tl-desenhar 1400ms cubic-bezier(.3, .7, .2, 1) 450ms both; }
.v2-metricas { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .5rem; margin: 0;
  padding: .9rem 0; border-top: 1px solid var(--linha); border-bottom: 1px solid var(--linha); }
.v2-metricas div { min-width: 0; }
.v2-metricas dt { color: var(--sutil); font-size: .76rem; }
.v2-metricas dd { margin: 0; font: 700 1.05rem "JetBrains Mono", monospace; font-variant-numeric: tabular-nums; }
.v2-painel-rodape { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding-top: .8rem;
  color: var(--apagado); font-size: .86rem; }
.v2-flutuante { position: absolute; left: -2.2rem; bottom: .2rem; width: min(17rem, 70%); padding: .9rem 1rem;
  border-radius: 16px; background: rgba(10, 31, 68, .88); border: 1px solid rgba(245, 184, 61, .3);
  box-shadow: 0 24px 60px rgba(0, 0, 0, .5); backdrop-filter: blur(12px);
  animation: tl-chegar 600ms cubic-bezier(.2, .7, .2, 1) 1100ms both; }
.v2-flutuante p { margin: .5rem 0 0; color: var(--texto); font-size: .88rem; line-height: 1.45; }
.v2-nota { position: absolute; right: 0; bottom: -1.3rem; margin: 0; color: var(--sutil); font-size: .75rem; text-align: right; max-width: 22rem; }

/* faixa das fontes (o que aprendemos com o Fundamentei e o Fiscal.ai: mostrar de onde vem cada dado) */
.v2-fontes { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 2rem; padding-block: 1.6rem; }
.v2-fontes .olho { margin: 0; }
.v2-fontes ul { display: flex; flex-wrap: wrap; gap: .5rem 1.6rem; list-style: none; margin: 0; padding: 0; flex: 1; }
.v2-fontes li { display: grid; max-width: none; }
.v2-fontes strong { font-size: .98rem; letter-spacing: -0.01em; }
.v2-fontes span { color: var(--sutil); font-size: .78rem; }

/* bento das seis frentes */
.v2-bento { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 1rem; margin: 1.5rem 0 1.25rem; }
.v2-bento .cartao { grid-column: span 2; background: var(--destaque); box-shadow: 0 1px 2px var(--linha), 0 14px 34px -18px var(--sombra); }
:root[data-tema="escuro"] .v2-bento .cartao { background: var(--superficie); }
.v2-bento .v2-larga { grid-column: span 3; display: grid; grid-template-columns: 1fr minmax(0, 13rem); gap: 1rem; align-items: center; }
.v2-bento .v2-faixa-cartao { grid-column: span 6; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
.v2-bento .v2-faixa-cartao p { margin-bottom: 0; }
.v2-mini { width: 100%; height: auto; }
.v2-mini .ref { fill: none; stroke: var(--sutil); stroke-width: 1.5; stroke-dasharray: 3 4; }
.v2-mini .est { fill: none; stroke: var(--azul); stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
.v2-mini text { font: 600 9px "Manrope", sans-serif; fill: var(--azul-texto); }
.v2-mini .ref-t { fill: var(--sutil); }
.v2-mini-doc { display: grid; gap: .45rem; padding: .9rem; border-radius: 12px; background: var(--fundo); border: 1px solid var(--linha); }
.v2-mini-doc i { display: block; height: 6px; border-radius: 3px; background: var(--linha-forte); }
.v2-mini-doc i.curta { width: 60%; }
.v2-doc-titulo { font-size: .72rem; font-weight: 700; color: var(--apagado); }
.v2-doc-selo { justify-self: start; margin-top: .2rem; padding: .1rem .5rem; border-radius: 999px; font-size: .7rem; font-weight: 700;
  color: var(--azul-texto); border: 1px solid color-mix(in srgb, var(--azul-texto) 45%, transparent); }

/* faixa da diferença */
.v2-diferenca { background: radial-gradient(60rem 22rem at 15% 0%, rgba(41, 98, 255, .22), transparent 70%), ${marca.marinho}; }
.v2-diferenca h2 { max-width: 24ch; font-size: clamp(1.8rem, 3.6vw, 2.7rem); }
.v2-principio { padding: 1.4rem; border-radius: var(--raio); background: rgba(16, 39, 82, .55); border: 1px solid var(--linha); }
.v2-principio p { color: var(--apagado); margin: 0; }

/* Report Studio: controles em pílula e folhas em leve perspectiva */
.vitrine .controles { border-radius: 999px; background: var(--destaque); box-shadow: 0 1px 2px var(--linha); }
.vitrine .controles button { border-radius: 999px; }
.vitrine .folhas { perspective: 1400px; }
.vitrine .folhas img:first-child { transform: rotateY(6deg); }
.vitrine .folhas img:last-child { transform: rotateY(-6deg); }

/* chamada final com o mesmo horizonte do hero */
.v2-final-fundo { position: relative; overflow: hidden; isolation: isolate; }
.v2-horizonte-alto { bottom: -70%; animation: none; opacity: .9; }
.v2-final-fundo .final h2 { font-size: clamp(1.9rem, 4vw, 2.8rem); }

@media (max-width: 860px) {
  .v2-painel-pilha { display: none; }
  .v2-bento { grid-template-columns: 1fr; }
  .v2-bento .cartao, .v2-bento .v2-larga, .v2-bento .v2-faixa-cartao { grid-column: auto; }
  .v2-bento .v2-larga { grid-template-columns: 1fr; }
  .v2-bento .v2-faixa-cartao { flex-direction: column; align-items: start; }
  .v2-fontes { gap: .75rem; }
}
@media (prefers-reduced-motion: reduce) {
  .vitrine .folhas img { transform: none !important; }
}

/* ===== animações (rodada 2, 14/10/2026) ===== */
/* fundo "mercado vivo": canvas atrás do hero, sumindo nas bordas */
.v2-mercado { position: absolute; inset: 0; width: 100%; height: 100%; z-index: -1; pointer-events: none;
  -webkit-mask-image: radial-gradient(85% 75% at 50% 45%, #000 35%, transparent 85%);
  mask-image: radial-gradient(85% 75% at 50% 45%, #000 35%, transparent 85%);
  animation: tl-chegar 1600ms ease 200ms both; }
/* aurora: duas manchas de luz que flutuam devagar atrás de tudo */
.v2-aurora { position: absolute; inset: 0; z-index: -2; overflow: hidden; pointer-events: none; }
.v2-aurora span { position: absolute; width: 46vw; height: 46vw; max-width: 720px; max-height: 720px; border-radius: 50%;
  filter: blur(70px); opacity: .45; will-change: transform; }
.v2-aurora span:nth-child(1) { left: -8%; top: -18%; background: radial-gradient(closest-side, ${marca.azul}, transparent);
  animation: v2-flutuar-a 26s ease-in-out infinite alternate; }
.v2-aurora span:nth-child(2) { right: -10%; top: 10%; background: radial-gradient(closest-side, #3b2fd1, transparent); opacity: .3;
  animation: v2-flutuar-b 32s ease-in-out infinite alternate; }
@keyframes v2-flutuar-a { to { transform: translate(18vw, 10vh) scale(1.15); } }
@keyframes v2-flutuar-b { to { transform: translate(-14vw, 14vh) scale(.9); } }
.v2-pausado .v2-aurora span { animation-play-state: paused; }

/* botão de pausa (WCAG 2.2.2): pequeno, no canto do hero */
.v2-pausa { position: absolute; right: clamp(1rem, 4vw, 2rem); bottom: 1rem; z-index: 2; display: inline-flex; align-items: center; gap: .45rem;
  padding: .35rem .7rem; border-radius: 999px; border: 1px solid var(--linha-forte); background: rgba(6, 20, 48, .6);
  color: var(--apagado); font: 600 .78rem "Manrope", sans-serif; cursor: pointer; backdrop-filter: blur(8px); }
.v2-pausa:hover { color: var(--texto); border-color: var(--azul-texto); }
.v2-pausa svg { width: .9rem; height: .9rem; }
.v2-pausa .retomar { display: none; }
.v2-pausado .v2-pausa .pausar { display: none; }
.v2-pausado .v2-pausa .retomar { display: block; }

/* brilho que passa uma vez pelo "Mais inteligência" */
.v2-degrade { background-size: 220% 100%; animation: v2-brilho 2200ms cubic-bezier(.3, .7, .2, 1) 500ms both; }
@keyframes v2-brilho { from { background-position: 100% 0; } to { background-position: 0 0; } }

/* revelar ao rolar */
.v2-anima .v2-revelar { opacity: 0; transform: translateY(18px); filter: blur(6px);
  transition: opacity 650ms cubic-bezier(.2, .7, .2, 1), transform 650ms cubic-bezier(.2, .7, .2, 1), filter 650ms ease; }
.v2-anima .v2-revelar.visivel { opacity: 1; transform: none; filter: none; }
/* o gráfico do cartão Estratégias se desenha quando aparece */
.v2-anima .v2-mini .est { stroke-dasharray: 1; stroke-dashoffset: 1; transition: stroke-dashoffset 1400ms cubic-bezier(.3, .7, .2, 1) 300ms; }
.v2-anima .visivel .v2-mini .est { stroke-dashoffset: 0; }
/* o horizonte da chamada final sobe quando ela aparece; a faixa da diferença acende */
.v2-anima .v2-final-fundo .v2-horizonte { opacity: 0; transform: translateY(80px) scale(.95);
  transition: opacity 1400ms ease, transform 1600ms cubic-bezier(.2, .7, .2, 1); }
.v2-anima .v2-final-fundo.visivel .v2-horizonte { opacity: .9; transform: none; }
.v2-diferenca { background-size: 100% 100%; }
.v2-anima .v2-diferenca { background: ${marca.marinho}; transition: background 1200ms ease; }
.v2-anima .v2-diferenca.visivel { background: radial-gradient(60rem 22rem at 15% 0%, rgba(41, 98, 255, .22), transparent 70%), ${marca.marinho}; }

/* luz que segue o cursor (cartões) */
.v2-bento .cartao, .v2-principio { position: relative; overflow: hidden; isolation: isolate; }
.v2-bento .cartao::after, .v2-principio::after { content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none; opacity: 0;
  background: radial-gradient(22rem circle at var(--mx, 50%) var(--my, 50%), color-mix(in srgb, var(--azul) 16%, transparent), transparent 60%);
  transition: opacity 220ms ease; }
.v2-bento .cartao:hover::after, .v2-principio:hover::after { opacity: 1; }
.v2-principio { transition: border-color 180ms ease, transform 180ms ease; }
.v2-principio:hover { border-color: var(--azul-texto); transform: translateY(-2px); }

/* painel do hero: a inclinação segue o cursor com suavidade */
.v2-painel { transition: transform 300ms cubic-bezier(.2, .7, .2, 1); transform-style: preserve-3d; }

/* pílulas de exemplo: um leve salto ao passar o mouse */
.exemplos a { transition: transform 140ms ease, border-color 140ms ease; }
.exemplos a:hover { transform: translateY(-2px); }

@media (prefers-reduced-motion: reduce) {
  .v2-aurora span { animation: none !important; }
  .v2-pausa { display: none; }
  .v2-degrade { background-position: 0 0; }
}

/* ===== animações (rodada 3, 14/10/2026) ===== */
/* borda viva do painel: um brilho azul gira devagar pela borda (para com a pausa) */
@property --v2-angulo { syntax: "<angle>"; inherits: false; initial-value: 0deg; }
.v2-painel::before { background: conic-gradient(from var(--v2-angulo), transparent 0deg, rgba(110, 149, 255, .9) 40deg,
  transparent 110deg, transparent 200deg, rgba(110, 149, 255, .35) 250deg, transparent 320deg);
  animation: v2-girar 9s linear infinite; }
@keyframes v2-girar { to { --v2-angulo: 360deg; } }
.v2-pausado .v2-painel::before { animation-play-state: paused; }

/* fita de ativos: só nomes, nenhum preço; para ao passar o mouse e com a pausa */
.v2-fita { position: relative; display: flex; align-items: center; gap: 1.25rem; overflow: hidden; padding-block: .9rem;
  border-bottom: 1px solid var(--linha); background: color-mix(in srgb, var(--destaque) 60%, transparent); }
.v2-fita-rotulo { flex: none; padding-left: clamp(1rem, 4vw, 2rem); font-size: .74rem; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: var(--azul-texto); white-space: nowrap; }
.v2-fita-trilho { flex: 1; overflow: hidden;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
  mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent); }
.v2-fita-faixa { display: flex; width: max-content; animation: v2-correr 55s linear infinite; }
.v2-fita-faixa ul { display: flex; gap: .6rem; margin: 0; padding: 0 .6rem 0 0; list-style: none; }
.v2-fita-faixa li { display: inline-flex; align-items: baseline; gap: .45rem; max-width: none; padding: .3rem .75rem; border-radius: 999px;
  border: 1px solid var(--linha); background: var(--destaque); white-space: nowrap; font-size: .86rem; color: var(--apagado); }
.v2-fita-faixa li b { font: 700 .84rem "JetBrains Mono", monospace; color: var(--texto); }
.v2-fita:hover .v2-fita-faixa, .v2-pausado .v2-fita-faixa { animation-play-state: paused; }
@keyframes v2-correr { to { transform: translateX(-50%); } }

/* o número principal: cada dígito sobe de baixo, um depois do outro */
.v2-digito { display: inline-block; overflow: hidden; vertical-align: bottom; line-height: 1.05; }
.v2-digito > span { display: inline-block; animation: v2-subir 620ms cubic-bezier(.2, .8, .2, 1) both; }
@keyframes v2-subir { from { transform: translateY(105%); opacity: 0; } to { transform: none; opacity: 1; } }

/* títulos palavra por palavra */
.v2-anima .v2-titulo-palavras .v2-palavra { display: inline-block; opacity: 0; transform: translateY(.45em); filter: blur(4px);
  transition: opacity 520ms ease, transform 620ms cubic-bezier(.2, .7, .2, 1), filter 520ms ease; }
.v2-anima .v2-titulo-palavras.visivel .v2-palavra { opacity: 1; transform: none; filter: none; }

/* cartão Research: as linhas do documento se escrevem e o selo aparece */
.v2-anima .v2-mini-doc i { transform: scaleX(0); transform-origin: left; transition: transform 700ms cubic-bezier(.3, .7, .2, 1); }
.v2-anima .v2-mini-doc i:nth-of-type(2) { transition-delay: 150ms; }
.v2-anima .v2-mini-doc i:nth-of-type(3) { transition-delay: 300ms; }
.v2-anima .visivel .v2-mini-doc i { transform: none; }
.v2-anima .v2-doc-selo { opacity: 0; transform: scale(.8); transition: opacity 300ms ease 650ms, transform 400ms cubic-bezier(.3, 1.6, .5, 1) 650ms; }
.v2-anima .visivel .v2-doc-selo { opacity: 1; transform: none; }

/* Report Studio: as folhas chegam juntas e se abrem em leque */
.vitrine .folhas img { transition: transform 900ms cubic-bezier(.2, .7, .2, 1), opacity 200ms ease; }
.v2-anima .vitrine:not(.visivel) .folhas img:first-child { transform: translateX(50%) scale(.94); }
.v2-anima .vitrine:not(.visivel) .folhas img:last-child { transform: translateX(-50%) scale(.94); }

/* os três princípios: uma linha azul os liga quando a faixa aparece */
.v2-diferenca .grade { position: relative; }
.v2-diferenca .grade::before { content: ""; position: absolute; left: 0; right: 0; top: -1.1rem; height: 2px; border-radius: 2px;
  background: linear-gradient(90deg, ${marca.azul}, ${escuro.azul_texto} 60%, transparent); transform: scaleX(0); transform-origin: left;
  transition: transform 1400ms cubic-bezier(.3, .7, .2, 1) 300ms; }
.v2-diferenca.visivel .grade::before, :root:not(.v2-anima) .v2-diferenca .grade::before { transform: none; }

/* menu que encolhe ao rolar */
.topo .faixa { transition: min-height 260ms ease, box-shadow 260ms ease, background 260ms ease, max-width 260ms ease; }
.v2-rolou .topo .faixa { min-height: 3.1rem; max-width: calc(var(--largura) - 4rem);
  background: color-mix(in srgb, var(--fundo) 90%, transparent); box-shadow: 0 12px 40px var(--sombra); }

/* botões magnéticos voltam com suavidade */
.botao.primario { transition: translate 220ms cubic-bezier(.2, .7, .2, 1), transform 120ms ease, background 150ms ease; }

@media (max-width: 860px) { .v2-fita-rotulo { display: none; } }
@media (prefers-reduced-motion: reduce) {
  .v2-painel::before { animation: none !important; }
  .v2-fita-trilho { overflow-x: auto; }
  .v2-fita-faixa { animation: none !important; }
  .v2-fita-faixa ul[aria-hidden] { display: none; }
}
/* o hover dos cartões continua valendo depois de revelados */
.v2-anima .v2-revelar.visivel.cartao:hover, .v2-anima .v2-revelar.visivel.v2-principio:hover { transform: translateY(-2px); }
.v2-anima .v2-revelar.visivel.cartao.breve:hover { transform: none; }

/* ===== rodada 4: o visual v2 em todas as páginas (14/10/2026) ===== */
/* topo das páginas: mesmo fundo do hero da inicial, mais baixo */
.v2-heroi-pagina { overflow: hidden; }
.v2-pagina-topo { position: relative; border-top: 0; padding-block: clamp(3.5rem, 9vw, 6.5rem) 1rem; }
.v2-pagina-topo > * { animation: tl-chegar 520ms cubic-bezier(.2, .7, .2, 1) both; }
.v2-pagina-topo > :nth-child(2) { animation-delay: 70ms; }
.v2-pagina-topo > :nth-child(3) { animation-delay: 140ms; }
.v2-pagina-topo > :nth-child(n+4) { animation-delay: 210ms; }
.v2-pagina-topo h1 { font-size: clamp(2.2rem, 5vw, 3.8rem); letter-spacing: -0.04em; max-width: 20ch; }
.v2-pagina-topo .subtitulo { max-width: 60ch; }
.v2-heroi-curto .v2-pagina-topo { padding-block: clamp(3rem, 7vw, 4.5rem) .5rem; }
.v2-heroi-curto .v2-pagina-topo h1 { font-size: clamp(2rem, 4.4vw, 3.1rem); }
.v2-heroi-curto .linha-do-topo { height: clamp(50px, 7vw, 90px); }
.v2-depois-do-topo { border-top: 0; }
.v2-pagina-topo .atalhos .botao { border-radius: 999px; background: rgba(16, 39, 82, .55); border-color: var(--linha-forte);
  color: var(--texto); backdrop-filter: blur(8px); }
.v2-pagina-topo .atalhos .botao:hover { border-color: var(--azul-texto); }

/* cartões e pilares de todas as páginas: superfícies que flutuam (claro) e vidro (escuro) */
.grade .cartao, .pilar { background: var(--destaque); box-shadow: 0 1px 2px var(--linha), 0 14px 34px -18px var(--sombra); }
:root[data-tema="escuro"] .grade .cartao { background: var(--superficie); }
.escura .pilar, .escura .grade .cartao { background: rgba(16, 39, 82, .55); box-shadow: none; }
.grade .cartao.breve, :root[data-tema="escuro"] .grade .cartao.breve { background: transparent; box-shadow: none; }
.grade .cartao, .pilar, .v2-plano { position: relative; overflow: hidden; isolation: isolate; }
.grade .cartao::after, .pilar::after, .v2-plano::after { content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none; opacity: 0;
  background: radial-gradient(22rem circle at var(--mx, 50%) var(--my, 50%), color-mix(in srgb, var(--azul) 16%, transparent), transparent 60%);
  transition: opacity 220ms ease; }
.grade .cartao:hover::after, .pilar:hover::after, .v2-plano:hover::after { opacity: 1; }
.v2-anima .v2-revelar.visivel.pilar:hover { transform: translateY(-2px); }
.pilar { transition: border-color 180ms ease, transform 180ms ease; }
.pilar:hover { border-color: var(--azul-texto); }

/* barra "disponíveis / em breve" dos módulos */
.modulo-topo .contagem { display: grid; gap: .35rem; justify-items: end; }
.v2-barra { display: block; width: 11rem; height: 6px; border-radius: 999px; background: var(--linha); overflow: hidden; }
.v2-barra i { display: block; height: 100%; width: calc(var(--p) * 100%); border-radius: inherit;
  background: linear-gradient(90deg, ${marca.azul}, ${escuro.azul_texto}); }
.v2-anima .modulo-topo.v2-revelar .v2-barra i { transform: scaleX(0); transform-origin: left; transition: transform 1100ms cubic-bezier(.3, .7, .2, 1) 250ms; }
.v2-anima .modulo-topo.visivel .v2-barra i { transform: none; }

/* menu de atalhos que gruda no topo (Produto) */
.v2-subnav { position: fixed; left: 50%; top: 5rem; z-index: 4; display: flex; gap: .25rem; padding: .3rem; border-radius: 999px;
  background: color-mix(in srgb, var(--fundo) 85%, transparent); border: 1px solid var(--linha-forte); backdrop-filter: blur(14px);
  box-shadow: 0 12px 34px var(--sombra); transform: translate(-50%, -20px); opacity: 0; pointer-events: none;
  transition: opacity 220ms ease, transform 260ms cubic-bezier(.2, .7, .2, 1); max-width: calc(100vw - 2rem); overflow-x: auto; }
.v2-subnav.mostrar { opacity: 1; transform: translate(-50%, 0); pointer-events: auto; }
.v2-subnav a { padding: .4rem .85rem; border-radius: 999px; color: var(--apagado); font-weight: 600; font-size: .88rem; text-decoration: none; white-space: nowrap; }
.v2-subnav a:hover { color: var(--texto); }
.v2-subnav a[aria-current] { background: var(--azul); color: #fff; }

/* Como funciona: os três passos ligados por uma linha que se desenha */
.passos { position: relative; gap: 1.25rem; padding-top: 3rem; }
.passos::before { content: ""; position: absolute; left: 1.4rem; right: 1.4rem; top: 1.4rem; height: 2px; border-radius: 2px;
  background: linear-gradient(90deg, ${marca.azul}, ${escuro.azul_texto}); transform-origin: left; }
.v2-anima .passos::before { transform: scaleX(0); transition: transform 1300ms cubic-bezier(.3, .7, .2, 1) 200ms; }
.v2-anima .passos.visivel::before { transform: none; }
.passos li { position: relative; border-left: 0; border-radius: var(--raio); background: var(--destaque); border: 1px solid var(--linha);
  box-shadow: 0 14px 34px -18px var(--sombra); }
:root[data-tema="escuro"] .passos li { background: var(--superficie); }
.passos .numero { position: absolute; top: -2.75rem; left: 1rem; display: grid; place-items: center; width: 2.3rem; height: 2.3rem; margin: 0;
  border-radius: 50%; background: var(--azul); color: #fff; box-shadow: 0 0 0 6px color-mix(in srgb, var(--azul) 18%, transparent); }

/* perguntas frequentes em cartões */
.faq details { border: 1px solid var(--linha); border-radius: var(--raio); padding: 1rem 1.2rem; margin-bottom: .6rem; background: var(--destaque);
  transition: border-color 180ms ease, box-shadow 180ms ease; }
:root[data-tema="escuro"] .faq details { background: var(--superficie); }
.faq details[open] { border-color: color-mix(in srgb, var(--azul) 55%, transparent); box-shadow: 0 14px 34px -20px var(--sombra); }

/* Sobre: linha do tempo que se preenche ao rolar */
.linha-do-tempo::before { background: var(--linha-forte); }
.linha-do-tempo::after { content: ""; position: absolute; left: 7px; top: .5rem; bottom: .5rem; width: 2px;
  background: linear-gradient(180deg, ${marca.azul}, ${escuro.azul_texto}); transform-origin: top; transform: scaleY(var(--progresso, 1)); }
.linha-do-tempo li::before { z-index: 1; transition: background 300ms ease, box-shadow 300ms ease; }
.v2-anima .linha-do-tempo li.visivel::before { background: var(--azul); box-shadow: 0 0 0 6px color-mix(in srgb, var(--azul) 20%, transparent); }
.v2-heroi-sobre .sobre-topo { padding-block: clamp(3.5rem, 9vw, 6rem) 1rem; border-top: 0; }
.v2-heroi-sobre .sobre-topo h1 { font-size: clamp(2.3rem, 5.4vw, 4rem); letter-spacing: -0.04em; }
.v2-heroi-sobre .pilares-sobre li { background: rgba(16, 39, 82, .55); backdrop-filter: blur(8px); }

/* Sobre: Inteligência Integrada em três círculos que se juntam */
.v2-acreditamos { display: grid; grid-template-columns: minmax(0, 22rem) 1fr; gap: 2rem; align-items: center; margin-top: 1.5rem; }
.v2-tres-um { grid-template-columns: 1fr !important; margin-top: 0; }
.v2-venn { margin: 0; }
.v2-venn svg { width: 100%; height: auto; overflow: visible; }
.v2-venn circle { fill: color-mix(in srgb, var(--azul) 14%, transparent); stroke: var(--azul); stroke-width: 1.5;
  transition: transform 1100ms cubic-bezier(.2, .7, .2, 1), fill 600ms ease; mix-blend-mode: multiply; }
:root[data-tema="escuro"] .v2-venn circle { mix-blend-mode: screen; fill: color-mix(in srgb, var(--azul) 22%, transparent); }
.v2-venn text { font: 700 14px "Manrope", sans-serif; fill: var(--apagado); text-anchor: middle; transition: opacity 600ms ease 700ms; }
.v2-venn .centro { font-size: 15px; font-weight: 800; fill: var(--azul-texto); }
.v2-anima .v2-acreditamos:not(.visivel) .c1 { transform: translate(-40px, -18px); }
.v2-anima .v2-acreditamos:not(.visivel) .c2 { transform: translate(40px, -18px); }
.v2-anima .v2-acreditamos:not(.visivel) .c3 { transform: translate(0, 40px); }
.v2-anima .v2-acreditamos:not(.visivel) .centro { opacity: 0; }
.v2-lema { margin-top: 1.5rem; font-weight: 700; letter-spacing: .02em; }

/* Planos: três cartões, o Pro com a borda viva */
.v2-planos { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.1rem; align-items: stretch; }
.v2-plano { display: flex; flex-direction: column; gap: .8rem; padding: 1.6rem; border-radius: 20px; background: var(--destaque);
  border: 1px solid var(--linha); box-shadow: 0 1px 2px var(--linha), 0 18px 40px -22px var(--sombra);
  transition: transform 200ms ease, border-color 200ms ease; }
:root[data-tema="escuro"] .v2-plano { background: var(--superficie); }
.v2-plano:hover { transform: translateY(-3px); border-color: var(--azul-texto); }
.v2-plano header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: .5rem; }
.v2-plano h3 { margin: 0; font-size: 1.5rem; letter-spacing: -0.03em; }
.v2-plano-frase { margin: 0; color: var(--apagado); }
.v2-plano ul { list-style: none; margin: 0 0 .4rem; padding: 0; display: grid; gap: .55rem; flex: 1; }
.v2-plano li { position: relative; padding-left: 1.6rem; max-width: none; }
.v2-plano li::before { content: "✓"; position: absolute; left: 0; top: 0; color: var(--azul-texto); font-weight: 800; }
.v2-plano li b { font-family: "JetBrains Mono", monospace; font-variant-numeric: tabular-nums; }
.v2-plano .botao { width: 100%; }
.v2-desligado { opacity: .55; cursor: not-allowed; }
.v2-plano-destaque { color: var(--texto); background: linear-gradient(180deg, ${escuro.destaque}, ${marca.marinho}) !important; border-color: transparent;
  --texto: ${marca.claro}; --apagado: ${escuro.apagado}; --azul-texto: ${escuro.azul_texto}; --linha: rgba(232, 240, 255, .12);
  box-shadow: 0 30px 70px -20px rgba(10, 31, 68, .55); }
.v2-plano-destaque::before { content: ""; position: absolute; inset: -1px; border-radius: inherit; padding: 1px; pointer-events: none;
  background: conic-gradient(from var(--v2-angulo), transparent 0deg, rgba(110, 149, 255, .95) 40deg, transparent 110deg,
    transparent 200deg, rgba(110, 149, 255, .4) 250deg, transparent 320deg);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
  animation: v2-girar 9s linear infinite; }
.v2-pausado .v2-plano-destaque::before { animation-play-state: paused; }
.v2-mensal { background: radial-gradient(50rem 20rem at 85% 0%, rgba(41, 98, 255, .22), transparent 70%), ${marca.marinho}; }
.v2-promessas { list-style: none; padding: 0; margin: 1.25rem 0 1.5rem; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
.v2-promessas li { display: grid; gap: .3rem; max-width: none; padding: 1.2rem 1.3rem; border-radius: var(--raio);
  background: rgba(16, 39, 82, .55); border: 1px solid var(--linha); border-top: 2px solid var(--azul); }
.v2-promessas b { font-size: 1.1rem; }
.v2-promessas span { color: var(--apagado); font-size: .92rem; }
/* tabela comparativa: coluna Pro em destaque, ✓ e — no lugar de Sim e Não */
.v2-comparativo td:nth-child(4), .v2-comparativo th:nth-child(4) { background: color-mix(in srgb, var(--azul) 7%, transparent); }
.v2-comparativo tbody tr { transition: background 150ms ease; }
.v2-comparativo tbody tr:hover { background: var(--superficie); }
.v2-sim { color: var(--azul-texto); font-weight: 800; }
.v2-nao { color: var(--sutil); }

/* páginas de leitura: sumário lateral e barra de progresso */
.v2-progresso { position: fixed; left: 0; right: 0; top: 0; z-index: 7; height: 3px; transform-origin: left; transform: scaleX(0);
  background: linear-gradient(90deg, ${marca.azul}, ${escuro.azul_texto}); }
.v2-leitura { display: grid; grid-template-columns: 15rem minmax(0, 1fr); gap: clamp(1.5rem, 4vw, 3.5rem); align-items: start; }
.v2-leitura-simples { grid-template-columns: minmax(0, 1fr); }
.v2-leitura .v2-texto { border-top: 0; max-width: 52rem; }
.v2-sumario { position: sticky; top: 5.5rem; padding-block: clamp(2.5rem, 6vw, 4.5rem); }
.v2-sumario-titulo { margin: 0 0 .6rem; font-size: .74rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--azul-texto); }
.v2-sumario ol { list-style: none; margin: 0; padding: 0; border-left: 2px solid var(--linha); }
.v2-sumario li { max-width: none; }
.v2-sumario a { display: block; margin-left: -2px; padding: .35rem .8rem; border-left: 2px solid transparent; color: var(--apagado);
  font-size: .9rem; line-height: 1.35; text-decoration: none; transition: color 150ms ease, border-color 150ms ease; }
.v2-sumario a:hover { color: var(--texto); }
.v2-sumario a[aria-current] { color: var(--azul-texto); border-left-color: var(--azul); font-weight: 700; }
.v2-texto h2, .v2-texto h3 { scroll-margin-top: 6rem; }
.v2-texto article { padding: 1.5rem; border-radius: var(--raio); border: 1px solid var(--linha); background: var(--destaque);
  box-shadow: 0 14px 34px -22px var(--sombra); }
:root[data-tema="escuro"] .v2-texto article { background: var(--superficie); }
.v2-texto article h2 { margin-top: 0; }
.v2-texto article h3 { display: inline-block; padding: .1rem .7rem; border-radius: 999px; font-size: .85rem;
  color: var(--azul-texto); border: 1px solid color-mix(in srgb, var(--azul-texto) 45%, transparent); }

/* 404: o número grande e a linha de preço que despenca */
.v2-heroi-404 .v2-pagina-topo { min-height: calc(100vh - 9rem); display: flex; flex-direction: column; justify-content: center; }
.v2-quatro-zero-quatro { margin: 0; font: 800 clamp(5rem, 18vw, 11rem)/.9 "JetBrains Mono", monospace; letter-spacing: -0.06em;
  background: linear-gradient(180deg, #a9c1ff, ${marca.azul} 75%); -webkit-background-clip: text; background-clip: text; color: transparent; }
.v2-queda { position: absolute; right: 0; bottom: 8%; width: min(46rem, 60%); height: 14rem; z-index: -1; opacity: .8; }
.v2-queda path { fill: none; stroke: var(--queda); stroke-width: 3; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke;
  stroke-dasharray: 1; animation: tl-desenhar 1600ms cubic-bezier(.5, 0, .7, .4) 500ms both; }

/* rodapé: uma linha de luz no topo */
.rodape { position: relative; }
.rodape::before { content: ""; position: absolute; left: 0; right: 0; top: -1px; height: 1px;
  background: linear-gradient(90deg, transparent, ${marca.azul} 30%, ${escuro.azul_texto} 50%, ${marca.azul} 70%, transparent); opacity: .7; }

@media (max-width: 860px) {
  .v2-planos, .v2-promessas, .v2-acreditamos { grid-template-columns: 1fr; }
  .v2-leitura { grid-template-columns: minmax(0, 1fr); }
  .v2-sumario { position: static; padding-bottom: 0; }
  .passos { padding-top: 0; }
  .passos::before { display: none; }
  .passos .numero { position: static; margin-bottom: .6rem; }
  .v2-queda { width: 90%; opacity: .4; }
  .modulo-topo .contagem { justify-items: start; }
}
@media (prefers-reduced-motion: reduce) {
  .v2-plano-destaque::before { animation: none !important; }
}
`;
}
