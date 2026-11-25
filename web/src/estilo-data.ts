// O visual do TickerLab Data na página inicial (linha 966 da fila, "um site só", 16/11/2026): o topo com a
// janela de código, as três portas, as rotas da API, as travas e "como era na data". Veio de
// site-api/estatico/api.css; as cores da janela vêm de src/marca.py (JANELA_DE_CODIGO), o resto das variáveis
// da marca. Entra depois do v2 em estilo.ts.
import { marca } from "./conteudo";

const janela = marca.janela_de_codigo;
const MONO = `"JetBrains Mono", ui-monospace, monospace`;
// quantas abas um grupo pode ter (as do topo são 3, as de "como era na data" também)
const ABAS_POR_GRUPO = 6;

/** Abas sem JavaScript: o rádio marcado mostra o painel e acende o rótulo de mesma ordem. */
function cssDasAbas(): string {
  const regras: string[] = [];
  for (let i = 0; i < ABAS_POR_GRUPO; i++) {
    const marcado = `.guias > .guia-escolha[data-ordem="${i}"]:checked`;
    regras.push(
      `${marcado} ~ .guia-painel[data-ordem="${i}"], ${marcado} ~ * .guia-painel[data-ordem="${i}"] { display: block; }`,
      `${marcado} ~ * .guia-rotulo[data-ordem="${i}"] { background: var(--azul); border-color: var(--azul); color: #fff; }`,
      `.guias > .guia-escolha[data-ordem="${i}"]:focus-visible ~ * .guia-rotulo[data-ordem="${i}"] { outline: 2px solid var(--azul-texto); outline-offset: 2px; }`,
    );
  }
  return `.guia-escolha { position: absolute; opacity: 0; width: 1px; height: 1px; pointer-events: none; }
.guias .guia-painel { display: none; }
.guia-rotulo { cursor: pointer; }
${regras.join("\n")}`;
}

export function cssData(): string {
  return `/* --- visual do TickerLab Data (um site só) ------------------------------------------------ */
.heroi.heroi-janela { grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); align-items: center; }
.heroi-janela h1 { font-size: clamp(2rem, 4.4vw, 3.4rem); max-width: 16ch; }
.heroi-janela .subtitulo { max-width: 52ch; }
.pilula-do-beta { display: inline-flex; align-items: center; gap: .5rem; margin: 0 0 1.1rem; padding: .3rem .8rem;
  border: 1px solid var(--linha-forte); border-radius: 999px; font-size: .82rem; font-weight: 600; color: var(--apagado); }
.pilula-do-beta .ponto { width: .5rem; height: .5rem; border-radius: 50%; background: var(--alta); }
.provas-do-topo { display: flex; flex-wrap: wrap; gap: .4rem 1.2rem; margin: 1.4rem 0 0; padding: 0; list-style: none;
  font-size: .9rem; color: var(--apagado); }
.provas-do-topo li::before { content: "✓ "; color: var(--alta); font-weight: 700; }

/* a janela de código: escura nos dois temas, como um terminal */
.janela { position: relative; min-width: 0; background: ${janela.fundo}; color: ${janela.texto};
  border: 1px solid var(--linha-forte); border-radius: 16px; box-shadow: 0 24px 60px rgba(0, 0, 0, .28);
  overflow: hidden; animation: tl-chegar 520ms cubic-bezier(.2, .7, .2, 1) 120ms backwards; }
.janela-topo { display: flex; align-items: center; gap: .35rem; padding: .55rem .6rem;
  border-bottom: 1px solid rgba(232, 240, 255, .1); }
.janela-topo .guia-rotulo { padding: .3rem .75rem; border: 1px solid transparent; border-radius: 8px;
  font: 600 .8rem/1.4 ${MONO}; color: ${janela.chave}; }
.janela-topo .guia-rotulo:hover { color: ${janela.texto}; }
.janela-topo .status { margin-left: auto; font: 600 .75rem/1 ${MONO}; color: var(--alta); }
.janela pre { margin: 0; padding: 1rem 1.1rem; overflow-x: auto; font: 400 .78rem/1.65 ${MONO};
  font-variant-ligatures: none; font-variant-numeric: tabular-nums; color: ${janela.texto}; }
.janela pre code { font: inherit; }
.janela-pedido { border-bottom: 1px dashed rgba(232, 240, 255, .14); }
/* o pedido quebra a linha (cabe no celular); a resposta JSON mantém o recuo e rola de lado */
.janela-pedido { white-space: pre-wrap; overflow-wrap: anywhere; }
.janela .k { color: ${janela.chave}; }
.janela .s { color: ${janela.literal}; }
.janela .n { color: ${janela.numero}; }
.janela .c { color: ${janela.comentario}; font-style: italic; }
.janela .eu { color: #fff; font-weight: 600; }
.janela .destaque-rastro { display: inline-block; margin-left: -.5rem; padding: .1rem .5rem; background: ${janela.rastro};
  border-left: 2px solid var(--azul); border-radius: 0 6px 6px 0; }
.janela-nota { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .3rem 1rem; margin: 0; max-width: none;
  padding: .6rem 1.1rem .8rem; border-top: 1px solid rgba(232, 240, 255, .1); font-size: .76rem; color: ${janela.comentario}; }
.janela-nota b { color: ${janela.texto}; font-weight: 600; }
${cssDasAbas()}

/* as três portas */
.portas-grade { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin-top: 1.6rem; }
.porta { display: flex; flex-direction: column; gap: .5rem; padding: 1.4rem; background: var(--superficie);
  border: 1px solid var(--linha); border-radius: var(--raio); }
.porta.principal { border-color: var(--azul); box-shadow: 0 0 0 1px var(--azul) inset; }
.porta h3 { margin: 0; font-size: 1.3rem; }
.porta p { margin: 0; color: var(--apagado); }
.porta-topo { display: flex; justify-content: space-between; align-items: center; }
.porta-numero { font: 700 .82rem/1 ${MONO}; color: var(--sutil); }
.porta-selo { padding: .2rem .6rem; border-radius: 999px; font-size: .74rem; font-weight: 700;
  background: var(--destaque); color: var(--azul-texto); }
.porta.principal .porta-selo { background: var(--azul); color: #fff; }
.porta .porta-exemplo { display: block; margin-top: auto; padding: .55rem .7rem; border-radius: 8px; background: ${janela.fundo};
  color: ${janela.texto}; font-size: .78rem; overflow-wrap: anywhere; }
.porta .seta { font-weight: 700; }

/* o que dá para pedir, e o nome em cada porta (a lista única das portas) e os passos para começar */
.consultas-titulo { margin: 2.6rem 0 0; font-size: 1.2rem; }
.consultas-grade { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; margin: 1rem 0 0; padding: 0;
  list-style: none; }
.consulta { padding: 1rem 1.15rem; background: var(--superficie); border: 1px solid var(--linha); border-radius: var(--raio); }
.consulta h4 { margin: 0 0 .3rem; font-size: 1rem; }
.consulta > p { margin: 0 0 .75rem; color: var(--apagado); font-size: .9rem; line-height: 1.5; }
/* o resumo da lista única começa em minúscula (nos documentos ele vem depois de "Nome:"); aqui abre a frase */
.consulta > p::first-letter { text-transform: uppercase; }
.consulta dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: .3rem .9rem; margin: 0; font-size: .8rem; }
.consulta dt { color: var(--sutil); font-weight: 600; }
.consulta dd { margin: 0; color: var(--apagado); overflow-wrap: anywhere; }
.consulta dd code { color: var(--azul-texto); font-weight: 600; }
.passos-em-linha { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 1.6rem; }
/* o passo mais alto estica os outros: o título e o texto ficam no topo, sem vão entre eles */
.passos-em-linha li { align-content: start; }

/* as rotas da API */
.v2-api .rotas { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin-top: 1.6rem; }
.v2-api .rota { padding: 1.2rem 1.3rem; background: var(--superficie); border: 1px solid var(--linha); border-radius: var(--raio); }
.v2-api .rota h3 { margin: .6rem 0 .3rem; }
.v2-api .rota p { margin: 0; color: var(--apagado); }
.v2-api .metodo { font: 500 .8rem/1.4 ${MONO}; color: var(--apagado); overflow-wrap: anywhere; }
.v2-api .metodo b { color: var(--alta); font-weight: 700; }
.v2-api .fontes { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .8rem !important; }
.v2-api .fontes span { padding: .15rem .55rem; border: 1px solid var(--linha-forte); border-radius: 999px;
  font: 500 .72rem/1.5 ${MONO}; color: var(--apagado); }
.v2-api .fontes .odbl { color: var(--azul-texto); border-color: color-mix(in srgb, var(--azul) 45%, transparent); }

/* as travas, numa grade */
.travas-em-grade { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.2rem 2rem; padding-left: 0; border-left: 0;
  margin-top: 1.4rem; }
.travas-em-grade > div { padding-left: 1rem; border-left: 2px solid var(--azul); }

/* como era na data */
.como-era { background: radial-gradient(60rem 30rem at 15% 0%, color-mix(in srgb, var(--azul) 22%, transparent), transparent 65%), var(--fundo); }
.demo-data { position: relative; display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 2rem;
  align-items: start; margin-top: 1.6rem; }
.instantes-titulo { margin: 0 0 .6rem; font-size: .8rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--apagado); }
.instantes { display: flex; flex-wrap: wrap; gap: .5rem; }
.instantes .guia-rotulo { padding: .45rem .9rem; border: 1px solid var(--linha-forte); border-radius: 999px;
  font: 600 .85rem/1.3 ${MONO}; color: var(--texto); }
.data-escolhida { margin: 1.2rem 0 0; font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; }
.data-escolhida small { display: block; margin-top: .35rem; font-size: 1rem; font-weight: 400; letter-spacing: 0; color: var(--apagado); }
.como-era .fatos { margin: 1.2rem 0 0; padding-left: 1.1rem; color: var(--apagado); font-size: .95rem; }
.como-era .fatos b { font-family: ${MONO}; font-weight: 600; color: var(--texto); }

@media (max-width: 960px) {
  .heroi.heroi-janela, .demo-data { grid-template-columns: minmax(0, 1fr); }
  .portas-grade, .travas-em-grade, .passos-em-linha, .consultas-grade { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 680px) {
  .v2-api .rotas { grid-template-columns: minmax(0, 1fr); }
  .janela pre { font-size: .72rem; padding: .85rem .9rem; }
}
`;
}
