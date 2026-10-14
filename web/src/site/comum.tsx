// Peças que aparecem em mais de uma página do site.
import type { CSSProperties } from "react";
import type { Funcionalidade, Modulo } from "../conteudo";
import { modulos } from "../conteudo";
import { BETA_FECHADO, TICKER_DO_EXEMPLO, linkDoApp } from "./textos";

// os seis módulos da página Produto; o Aprender tem página própria
export const MODULOS_DO_PRODUTO: Modulo[] = modulos.slice(0, 6);

export function moduloPelaChave(chave: string): Modulo {
  const modulo = modulos.find((m) => m.chave === chave);
  if (!modulo) throw new Error(`Módulo desconhecido: ${chave}`);
  return modulo;
}

export function disponiveis(modulo: Modulo): number {
  return modulo.funcionalidades.filter((f) => f.disponivel).length;
}

/** "4 disponíveis · 2 em breve" (no singular quando é uma só). */
export function contagem(modulo: Modulo): string {
  const prontas = disponiveis(modulo);
  const emBreve = modulo.funcionalidades.length - prontas;
  const partes: string[] = [];
  if (prontas) partes.push(`${prontas} ${prontas === 1 ? "disponível" : "disponíveis"}`);
  if (emBreve) partes.push(`${emBreve} em breve`);
  return partes.join(" · ");
}

function Selo({ funcionalidade }: { funcionalidade: Funcionalidade }) {
  return funcionalidade.disponivel ? (
    <span className="selo disponivel">Disponível</span>
  ) : (
    <span className="selo breve">Em breve</span>
  );
}

/** Cartão com o selo; só o que já existe leva ao app ou à ferramenta do site (o resto não tem link). */
function CartaoDaFuncionalidade({ f }: { f: Funcionalidade }) {
  if (!f.disponivel) {
    return (
      <article className="cartao breve">
        <h3>
          {f.nome} <Selo funcionalidade={f} />
        </h3>
        <p>{f.descricao}</p>
      </article>
    );
  }
  const parametros: Record<string, string> = f.ticker ? { ticker: f.ticker } : {};
  return (
    <article className="cartao">
      <h3>
        {f.nome} <Selo funcionalidade={f} />
      </h3>
      <p>{f.descricao}</p>
      {f.pagina_do_site ? (
        <a className="seta" href={`/${f.pagina_do_site}`}>
          Abrir a ferramenta
        </a>
      ) : (
        <a className="seta" href={linkDoApp(f.pagina_do_app ?? "", parametros)}>
          Abrir no app
        </a>
      )}
    </article>
  );
}

/** A fração do módulo que já está no app, desenhada (o número fica no texto ao lado). */
function BarraDoModulo({ modulo }: { modulo: Modulo }) {
  const fracao = disponiveis(modulo) / modulo.funcionalidades.length;
  return (
    <span className="v2-barra" aria-hidden="true">
      <i style={{ "--p": fracao.toFixed(3) } as CSSProperties} />
    </span>
  );
}

export function SecaoDoModulo({ modulo }: { modulo: Modulo }) {
  const titulo = `titulo-${modulo.chave}`;
  return (
    <section className="faixa secao" id={modulo.chave} aria-labelledby={titulo}>
      <div className="modulo-topo">
        <div>
          <p className="olho">{modulo.objetivo}</p>
          <h2 id={titulo}>{modulo.nome}</h2>
        </div>
        <p className="contagem">
          {contagem(modulo)}
          <BarraDoModulo modulo={modulo} />
        </p>
      </div>
      <p className="subtitulo">{modulo.frase}</p>
      <div className="grade tres">
        {modulo.funcionalidades.map((f) => (
          <CartaoDaFuncionalidade key={f.nome} f={f} />
        ))}
      </div>
    </section>
  );
}

export function ListaDeCartoes({
  itens,
  classe = "cartao",
}: {
  itens: [string, string][];
  classe?: string;
}) {
  return (
    <>
      {itens.map(([titulo, descricao]) => (
        <article key={titulo} className={classe}>
          <h3>{titulo}</h3>
          <p>{descricao}</p>
        </article>
      ))}
    </>
  );
}

export function AvisoDeAcesso() {
  if (!BETA_FECHADO) return null;
  return (
    <p className="selo-beta">
      <span>Beta fechado</span> O app está em fase de testes: por enquanto, só contas
      convidadas entram com o Google.
    </p>
  );
}

// A linha do topo: ilustração no estilo das artes do manual (linhas e pontos sugerem perspectivas e
// conexões), não dados de mercado. Fica numa faixa própria, abaixo do conteúdo do topo.
const LARGURA_DA_LINHA = 1200;
const ALTURA_DA_LINHA = 160;
const PONTOS_DE_APOIO =
  "0,120 140,108 260,116 400,82 520,94 660,64 800,74 960,50 1140,60 1200,56";
const PONTOS_DA_LINHA = "0,140 150,128 280,96 410,112 540,74 680,90 820,58 980,70 1140,36";
const FIM_DA_LINHA = [1140, 36];

const porcento = (fracao: number) => `${(fracao * 100).toFixed(1)}%`;

export function LinhaDoHeroi() {
  return (
    <div className="linha-do-topo" aria-hidden="true">
      <svg
        className="linha-heroi"
        viewBox={`0 0 ${LARGURA_DA_LINHA} ${ALTURA_DA_LINHA}`}
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
      >
        <polyline className="apoio" points={PONTOS_DE_APOIO} />
        <path
          className="principal"
          pathLength={1}
          d={`M${PONTOS_DA_LINHA.replaceAll(" ", " L")}`}
        />
      </svg>
      {/* o ponto fica fora do SVG (que estica na horizontal) para continuar redondo */}
      <span
        className="ponto-heroi"
        style={{
          left: porcento(FIM_DA_LINHA[0] / LARGURA_DA_LINHA),
          top: porcento(FIM_DA_LINHA[1] / ALTURA_DA_LINHA),
        }}
      />
    </div>
  );
}

export function ChamadaFinal() {
  return (
    <div className="escura v2-final-fundo">
      {/* o horizonte azul do topo, que sobe quando a chamada aparece (movimento.js) */}
      <div className="v2-horizonte v2-horizonte-alto" aria-hidden="true" />
      <section className="faixa secao final" aria-labelledby="titulo-final">
        <h2 id="titulo-final">Comece pela sua primeira análise</h2>
        <p className="subtitulo">
          O tutorial do app guia você em 2 minutos, com dados de verdade.
        </p>
        <a
          className="botao primario"
          href={linkDoApp("visao-geral", { ticker: TICKER_DO_EXEMPLO })}
        >
          Experimentar com PETR4
        </a>
      </section>
    </div>
  );
}
