// O CSS do site público (e do app em React, que usa o mesmo). As cores vêm de src/marca.py (pelo
// conteudo/marca.json); o resto é fixo. O visual v2 (ADR 0065) vem depois, em estilo-v2.ts, e as
// ferramentas grátis por último, em estilo-ferramentas.ts.
import { marca } from "./conteudo";
import { cssFerramentas } from "./estilo-ferramentas";
import { cssV2 } from "./estilo-v2";

export const CABECALHO = "/* gerado por web/src/estilo.ts a partir de src/marca.py — não editar à mão */";

// LF sempre (o Git no Windows pode tirar o arquivo com CRLF): o mesmo CSS e o mesmo hash em todo lugar
const semCrlf = (texto: string) => texto.replace(/\r\n/g, "\n");

function variaveis(tema: string[][]): string {
  return tema.map(([nome, valor]) => `--${nome}: ${valor};`).join(" ");
}

export function css(): string {
  return semCrlf(`${CABECALHO}
@font-face { font-family: "Manrope"; src: url("/fontes/Manrope-VariableFont_wght.ttf") format("truetype"); font-weight: 200 800; font-display: swap; }
@font-face { font-family: "JetBrains Mono"; src: url("/fontes/JetBrainsMono-VariableFont_wght.ttf") format("truetype"); font-weight: 100 800; font-display: swap; }
:root {
  ${variaveis(marca.site_claro)}
  --largura: 72rem; --raio: 14px;
  color-scheme: light;
}
:root[data-tema="escuro"] { ${variaveis(marca.site_escuro)} color-scheme: dark; }
.escura { ${variaveis(marca.site_faixa_marinha)} color-scheme: dark; background: var(--fundo); color: var(--texto); }
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--fundo); color: var(--texto);
  font: 400 1rem/1.6 "Manrope", system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased; }
img { max-width: 100%; height: auto; display: block; }
a { color: var(--azul-texto); text-underline-offset: 3px; }
h1, h2, h3 { line-height: 1.12; letter-spacing: -0.03em; text-wrap: balance; margin: 0 0 .6em; }
h1 { font-size: clamp(2.1rem, 5vw, 3.4rem); font-weight: 800; }
h2 { font-size: clamp(1.6rem, 3.2vw, 2.3rem); font-weight: 800; }
h3 { font-size: 1.12rem; font-weight: 700; letter-spacing: -0.01em; }
p, li { max-width: 68ch; }
code, .ticker { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: .92em; }
:focus-visible { outline: 2px solid var(--azul-texto); outline-offset: 3px; border-radius: 6px; }
.pular { position: absolute; left: -999px; top: .5rem; background: var(--azul); color: #fff; padding: .5rem 1rem; border-radius: 8px; z-index: 10; }
.pular:focus { left: 1rem; }
.faixa { width: 100%; max-width: var(--largura); margin-inline: auto; padding-inline: clamp(1rem, 4vw, 2rem); }
.olho { margin: 0 0 .5rem; font-size: .74rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--azul-texto); }
.subtitulo { font-size: 1.12rem; color: var(--apagado); }
.apagado { color: var(--apagado); }
/* topo */
.topo { position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--fundo) 88%, transparent);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--linha); }
.topo .faixa { display: flex; align-items: center; gap: 1rem 1.5rem; min-height: 4rem; }
.topo nav { display: flex; gap: 1.25rem; margin-left: auto; flex-wrap: wrap; }
.topo nav a { color: var(--apagado); text-decoration: none; font-weight: 600; font-size: .95rem; }
.topo nav a:hover, .topo nav a[aria-current] { color: var(--texto); }
.marca { display: inline-flex; align-items: center; gap: .55rem; color: var(--texto); text-decoration: none;
  font-weight: 800; font-size: 1.15rem; letter-spacing: -0.02em; }
.marca svg { width: 28px; height: 28px; color: var(--simbolo-topo); }
.marca b { color: var(--lab); font-weight: 800; }
/* botão do tema: só aparece com JavaScript (sem ele, o botão não faria nada) */
.tema { display: none; align-items: center; justify-content: center; width: 2.4rem; height: 2.4rem; padding: 0;
  border-radius: 10px; border: 1px solid var(--linha-forte); background: transparent; color: var(--texto); cursor: pointer; }
.com-js .tema { display: inline-flex; }
.tema:hover { border-color: var(--azul); }
.tema svg { width: 1.15rem; height: 1.15rem; }
/* o botão mostra o ícone da escolha atual (claro, escuro ou automático) */
.tema svg.claro, .tema svg.escuro, .tema svg.auto { display: none; }
[data-escolha="claro"] .tema svg.claro, [data-escolha="escuro"] .tema svg.escuro,
[data-escolha="auto"] .tema svg.auto { display: block; }
.tema-menu { position: relative; }
.tema-opcoes { position: absolute; right: 0; top: calc(100% + .45rem); z-index: 6; min-width: 17rem; padding: .35rem;
  background: var(--destaque); border: 1px solid var(--linha-forte); border-radius: 12px; box-shadow: 0 16px 40px var(--sombra);
  transform-origin: top right; transition: opacity 160ms ease, transform 160ms ease; }
@starting-style { .tema-opcoes { opacity: 0; transform: scale(.98) translateY(-4px); } }
.tema-opcoes button { display: flex; align-items: center; gap: .65rem; width: 100%; padding: .55rem .7rem; border: 0;
  border-radius: 8px; background: transparent; color: var(--texto); font: 600 .95rem "Manrope", sans-serif;
  text-align: left; cursor: pointer; }
.tema-opcoes button:hover, .tema-opcoes button:focus-visible { background: var(--superficie); }
.tema-opcoes svg { width: 1.1rem; height: 1.1rem; flex: none; color: var(--apagado); }
.tema-opcoes span { display: grid; }
.tema-opcoes small { color: var(--apagado); font-weight: 500; font-size: .8rem; }
.tema-opcoes [aria-checked="true"] { color: var(--azul-texto); }
.tema-opcoes [aria-checked="true"] svg { color: var(--azul-texto); }
.tema-opcoes [aria-checked="true"]::after { content: "✓"; margin-left: auto; font-weight: 800; }
/* botões */
.botao { display: inline-flex; align-items: center; justify-content: center; gap: .4rem; border-radius: 10px;
  padding: .75rem 1.2rem; font: 700 1rem "Manrope", sans-serif; text-decoration: none; cursor: pointer;
  border: 1px solid transparent; transition: transform 120ms ease, background 150ms ease, border-color 150ms ease; }
.botao:active { transform: scale(.98); }
.botao.primario { background: var(--azul); color: #fff; }
.botao.primario:hover { background: #3d71ff; }
.botao.secundario { background: var(--superficie); color: var(--texto); border-color: var(--linha-forte); }
.botao.secundario:hover { border-color: var(--azul); }
.botao.pequeno { padding: .5rem .9rem; font-size: .92rem; }
.seta { font-weight: 700; text-decoration: none; }
.seta::after { content: " →"; display: inline-block; transition: transform 160ms ease; }
.seta:hover::after, .cartao:hover .seta::after { transform: translateX(3px); }
/* herói */
.heroi { display: grid; grid-template-columns: 1.15fr .85fr; gap: clamp(2rem, 5vw, 4rem); align-items: center;
  padding-block: clamp(3rem, 8vw, 6rem); }
/* com z-index: o movimento.js põe translate na coluna (paralaxe), o que já a torna um contexto de
   empilhamento; sem z-index ela ficaria atrás da linha decorativa e do painel, e a busca junto.
   Acima do botão de pausa (2), que a lista de sugestões aberta alcança no celular */
.heroi-texto { min-width: 0; position: relative; z-index: 3; }
.heroi-visual img { border-radius: 10px; border: 1px solid var(--linha-forte);
  box-shadow: 0 30px 80px var(--sombra); transform: rotate(1.5deg); }
/* acima dos irmãos do herói: as sugestões (z-index 4 aqui dentro) não podem ficar atrás do "Experimente" */
.busca { position: relative; z-index: 2; margin: 1.75rem 0 .75rem; }
.busca label { display: block; font-weight: 700; font-size: .9rem; margin-bottom: .4rem; color: var(--apagado); }
.busca .campo { display: flex; gap: .5rem; }
.busca input { flex: 1; min-width: 0; padding: .8rem 1rem .8rem 2.6rem; border-radius: 10px; font: 500 1rem "Manrope", sans-serif;
  background: var(--superficie) url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23a9b5c7'%3E%3Cpath d='M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z'/%3E%3C/svg%3E") no-repeat .8rem center / 1.2rem;
  color: var(--texto); border: 1px solid var(--linha-forte); }
.busca input { transition: border-color 160ms ease, box-shadow 160ms ease; }
.busca input:focus { border-color: var(--azul); outline: none; box-shadow: 0 0 0 3px color-mix(in srgb, var(--azul) 35%, transparent); }
#sugestoes { position: absolute; left: 0; right: 0; top: 100%; margin: .35rem 0 0; padding: .35rem; list-style: none; z-index: 4;
  background: var(--destaque); border: 1px solid var(--linha-forte); border-radius: 10px; box-shadow: 0 16px 40px var(--sombra); }
#sugestoes li { max-width: none; padding: .55rem .7rem; border-radius: 8px; cursor: pointer; display: flex; gap: .6rem; align-items: baseline; }
#sugestoes li[aria-selected="true"], #sugestoes li:hover { background: var(--superficie); }
#sugestoes .codigo { font-family: "JetBrains Mono", monospace; font-weight: 700; color: var(--azul-texto); min-width: 6.5rem; }
#sugestoes .nome { color: var(--texto); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
#sugestoes .tipo { color: var(--sutil); font-size: .85rem; white-space: nowrap; }
.exemplos { display: flex; flex-wrap: wrap; gap: .45rem; align-items: center; color: var(--apagado); font-size: .92rem; }
.exemplos a { padding: .2rem .55rem; border-radius: 999px; background: var(--superficie); border: 1px solid var(--linha);
  color: var(--texto); text-decoration: none; }
.exemplos a:hover { border-color: var(--azul); }
.acoes { display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 1.5rem; }
.selo-beta { margin-top: 1.25rem; color: var(--apagado); font-size: .92rem; }
.selo-beta span { display: inline-block; margin-right: .4rem; padding: .1rem .5rem; border-radius: 999px; font-weight: 700;
  font-size: .78rem; color: var(--atencao); border: 1px solid color-mix(in srgb, var(--atencao) 45%, transparent); }
/* seções */
.secao { padding-block: clamp(2.5rem, 6vw, 4.5rem); border-top: 1px solid var(--linha); }
.estreita { max-width: 52rem; border-top: 0; }
/* faixas de largura total; a seção logo depois de uma faixa não precisa de linha em cima */
.escura > .secao, .escura + .secao { border-top: 0; }
.grade { display: grid; gap: 1rem; margin-top: 1.5rem; }
.grade.tres { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.grade.quatro { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.cartao, .pilar { background: var(--superficie); border: 1px solid var(--linha); border-radius: var(--raio); padding: 1.4rem;
  transition: border-color 180ms ease, transform 180ms ease; }
.cartao:hover { border-color: var(--azul); transform: translateY(-2px); }
.cartao p, .pilar p { color: var(--apagado); margin: 0 0 1rem; }
.pilar p { margin: 0; font-size: .95rem; }
.passos { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; counter-reset: passo; }
.passos li { padding: 1.4rem; border-left: 2px solid var(--azul); background: var(--superficie); border-radius: 0 var(--raio) var(--raio) 0; }
.passos p { color: var(--apagado); margin: 0; }
.numero { display: inline-block; font-family: "JetBrains Mono", monospace; color: var(--azul-texto); font-weight: 700; margin-bottom: .4rem; }
/* módulos: o selo diz o que já está no app e o que está em construção */
.selo { display: inline-block; padding: .08rem .5rem; border-radius: 999px; font-size: .72rem; font-weight: 700;
  letter-spacing: .02em; white-space: nowrap; }
.selo.disponivel { color: var(--azul-texto); border: 1px solid color-mix(in srgb, var(--azul-texto) 45%, transparent); }
.selo.breve { color: var(--atencao); border: 1px solid color-mix(in srgb, var(--atencao) 45%, transparent); }
.cartao h3 { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem .5rem; }
.cartao.breve { background: transparent; border-style: dashed; }
.cartao.breve:hover { border-color: var(--linha); transform: none; }
.modulo-topo { display: flex; justify-content: space-between; align-items: end; gap: 0 1rem; flex-wrap: wrap; }
.contagem { color: var(--apagado); font-size: .92rem; }
/* Sobre */
.sobre-topo h1 { max-width: 18ch; }
.sobre-colunas { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem 2.5rem; margin-top: 1rem; }
.sobre-colunas p { margin: 0; }
.pilares-sobre { list-style: none; padding: 0; margin: 2rem 0 0; display: flex; flex-wrap: wrap; gap: .6rem; }
.pilares-sobre li { padding: .4rem .9rem; border: 1px solid var(--linha-forte); border-radius: 999px; font-weight: 700; }
.assinatura-sobre { margin-top: 2rem; color: var(--apagado); }
.assinatura-sobre strong { display: block; color: var(--texto); font-size: 1.15rem; }
.linha-do-tempo { list-style: none; padding: 0; margin: 2rem 0 0; position: relative; }
.linha-do-tempo::before { content: ""; position: absolute; left: 7px; top: .5rem; bottom: .5rem; width: 2px; background: var(--azul); }
.linha-do-tempo li { position: relative; padding: 0 0 1.75rem 2.5rem; max-width: 46rem; }
.linha-do-tempo li::before { content: ""; position: absolute; left: 0; top: .35rem; width: 16px; height: 16px; border-radius: 50%;
  background: var(--fundo); border: 3px solid var(--azul); }
.linha-do-tempo li:last-child::before { background: var(--azul); }
.linha-do-tempo h3 { margin: 0 0 .3rem; }
.linha-do-tempo p { margin: 0; color: var(--apagado); }
@media (max-width: 860px) { .sobre-colunas { grid-template-columns: 1fr; } }
.cabecalho { border-top: 0; padding-bottom: 1rem; }
.atalhos { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1.25rem; }
/* vitrine do Report Studio */
.vitrine .controles { display: inline-flex; flex-wrap: wrap; gap: .25rem; padding: .25rem; margin: 1rem 0 1.25rem;
  background: var(--superficie); border: 1px solid var(--linha); border-radius: 12px; }
.vitrine .controles button { font: 600 .92rem "Manrope", sans-serif; color: var(--apagado); background: transparent;
  border: 0; border-radius: 9px; padding: .5rem .9rem; cursor: pointer; }
.vitrine .controles button[aria-pressed="true"] { background: var(--azul); color: #fff; }
.vitrine .folhas { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.25rem; max-width: 56rem; }
.vitrine img { border-radius: 8px; border: 1px solid var(--linha-forte); box-shadow: 0 18px 50px var(--sombra);
  transition: opacity 200ms ease; }
.vitrine img.trocando { opacity: .35; }
.legenda { color: var(--sutil); font-size: .88rem; margin-top: 1rem; }
/* tabelas */
.tabela { overflow-x: auto; margin: 1.5rem 0; border: 1px solid var(--linha); border-radius: var(--raio); }
table { border-collapse: collapse; width: 100%; font-size: .95rem; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: .75rem 1rem; border-bottom: 1px solid var(--linha); vertical-align: top; }
thead th { background: var(--superficie); color: var(--apagado); font-size: .82rem; letter-spacing: .04em; text-transform: uppercase; }
tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
table.planos td { text-align: center; }
table.planos thead th:not(:first-child) { text-align: center; color: var(--texto); font-size: .95rem; text-transform: none; letter-spacing: 0; }
/* perguntas */
.faq details { border-bottom: 1px solid var(--linha); padding: 1rem 0; max-width: 52rem; }
.faq summary { cursor: pointer; font-weight: 700; font-size: 1.05rem; list-style: none; }
.faq summary::-webkit-details-marker { display: none; }
.faq summary::after { content: "+"; float: right; color: var(--azul-texto); font-weight: 800;
  transition: transform 220ms ease; }
.faq details[open] summary::after { transform: rotate(45deg); }
/* a resposta abre com a altura animada (navegadores sem suporte só abrem, sem animar) */
.faq details::details-content { block-size: 0; overflow-y: clip;
  transition: block-size 240ms ease, content-visibility 240ms allow-discrete; }
.faq details[open]::details-content { block-size: auto; }
.faq p { color: var(--apagado); margin: .6rem 0 0; }
.final { text-align: center; }
.final p { margin-inline: auto; }
/* textos longos (termos, privacidade, metodologia) */
.texto-longo h2 { font-size: 1.4rem; margin-top: 2.2rem; }
.texto-longo h3 { margin-top: 1.6rem; }
.texto-longo li { margin-bottom: .45rem; }
.texto-longo li, .texto-longo p { color: color-mix(in srgb, var(--texto) 88%, var(--apagado)); }
/* rodapé */
.rodape { padding-block: 2.5rem; border-top: 1px solid var(--linha); }
.rodape .faixa { display: grid; grid-template-columns: 1fr 2fr; gap: 1.5rem 2rem; }
.rodape nav { display: flex; flex-wrap: wrap; gap: .5rem 1.4rem; align-content: start; }
.rodape nav a { color: var(--apagado); text-decoration: none; }
.rodape nav a:hover { color: var(--texto); }
.rodape .aviso { grid-column: 1 / -1; color: var(--sutil); font-size: .86rem; max-width: none; margin: 0; }
/* --- movimento (blueprint, seção 09): curto, com função, uma vez; o que roda sem parar fica só no
   fundo do visual v2, sempre com botão de pausa (ADR 0065) ------------------------------------ */
:root { interpolate-size: allow-keywords; }
/* troca de página: o conteúdo cruza suavemente e o topo fica parado */
@view-transition { navigation: auto; }
.topo { view-transition-name: topo; }
::view-transition-old(root), ::view-transition-new(root) { animation-duration: 220ms; }
/* as sugestões da busca surgem do campo */
#sugestoes { transition: opacity 160ms ease, transform 160ms ease; }
@starting-style { #sugestoes { opacity: 0; transform: translateY(-4px); } }
/* o momento da página inicial: a linha se desenha, o ponto aparece, o texto e o relatório chegam */
/* sem overflow no topo: o que vaza é só o fundo, cortado em .v2-camadas; a lista da busca pode descer
   do herói e, com z-index, passar por cima do que vem depois (a fita de ativos é posicionada) */
.topo-da-pagina { z-index: 1; }
.topo-da-pagina > .heroi { padding-bottom: 1rem; }
.linha-do-topo { position: relative; height: clamp(80px, 11vw, 150px); }
.linha-heroi { position: absolute; inset: 0; width: 100%; height: 100%;
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 45%); mask-image: linear-gradient(90deg, transparent 0%, #000 45%); }
.linha-heroi polyline, .linha-heroi path { fill: none; stroke-linejoin: round; stroke-linecap: round; vector-effect: non-scaling-stroke; }
.linha-heroi .apoio { stroke: var(--texto); stroke-width: 2; opacity: .2; }
.linha-heroi .principal { stroke: var(--azul); stroke-width: 4; stroke-dasharray: 1; stroke-dashoffset: 0;
  animation: tl-desenhar 1100ms cubic-bezier(.3, .7, .2, 1) 150ms both; }
.ponto-heroi { position: absolute; width: 12px; height: 12px; margin: -6px 0 0 -6px; border-radius: 50%;
  background: var(--texto); animation: tl-ponto 260ms ease-out 1200ms both; }
/* "backwards", não "both": com "both" o transform da chegada fica para sempre, cada filho vira um
   contexto de empilhamento e as sugestões da busca ficam atrás do que vem depois */
.heroi-texto > * { animation: tl-chegar 420ms cubic-bezier(.2, .7, .2, 1) backwards; }
.heroi-texto > :nth-child(2) { animation-delay: 60ms; }
.heroi-texto > :nth-child(3) { animation-delay: 120ms; }
.heroi-texto > :nth-child(n+4) { animation-delay: 180ms; }
.heroi-visual img { animation: tl-folha 700ms cubic-bezier(.2, .7, .2, 1) 200ms both; }
@keyframes tl-desenhar { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
@keyframes tl-ponto { from { opacity: 0; transform: scale(.4); } to { opacity: 1; transform: none; } }
@keyframes tl-chegar { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes tl-folha { from { opacity: 0; transform: translateY(24px) rotate(4deg); } to { opacity: 1; transform: rotate(1.5deg); } }
/* celular */
@media (max-width: 860px) {
  .heroi { grid-template-columns: 1fr; }
  .heroi-visual { display: none; }
  .grade.tres, .grade.quatro, .passos { grid-template-columns: 1fr; }
  .topo nav { display: none; }
  .rodape .faixa { grid-template-columns: 1fr; }
  .vitrine .folhas { grid-template-columns: 1fr 1fr; gap: .6rem; }
}
@media (max-width: 520px) {
  .busca .campo { flex-direction: column; }
  #sugestoes .tipo { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after, *::details-content { transition: none !important; animation: none !important;
    scroll-behavior: auto !important; }
  @view-transition { navigation: none; }
}
${cssV2()}${cssFerramentas()}`);
}
