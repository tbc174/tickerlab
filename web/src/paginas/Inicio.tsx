// Página inicial, versão A (por assunto), escolhida em 13/10/2026: herói com busca, as seis frentes,
// o Report Studio e a chamada final. Era `landing()` de scripts/gerar_site.py.
import { site } from "../conteudo";
import { Bruto } from "../site/Bruto";
import { ChamadaFinal, MODULOS_DO_PRODUTO, contagem } from "../site/comum";
import {
  ASSINATURA,
  BETA_FECHADO,
  TICKER_DO_EXEMPLO,
  URL_DO_APP,
  linkDoApp,
} from "../site/textos";

export const DADOS = {
  caminho: "/",
  titulo: "TickerLab",
  descricao:
    "Pesquise ativos da B3 e dos EUA, entenda retorno e risco com cada número explicado " +
    "e gere relatórios em PDF. Nada é recomendação de investimento.",
};

const ESTILOS = site.estilos_do_relatorio;

// A linha do topo: ilustração no estilo das artes do manual (linhas e pontos sugerem perspectivas e
// conexões), não dados de mercado. Fica numa faixa própria, abaixo do conteúdo do topo.
const LARGURA_DA_LINHA = 1200;
const ALTURA_DA_LINHA = 160;
const PONTOS_DE_APOIO =
  "0,120 140,108 260,116 400,82 520,94 660,64 800,74 960,50 1140,60 1200,56";
const PONTOS_DA_LINHA = "0,140 150,128 280,96 410,112 540,74 680,90 820,58 980,70 1140,36";
const FIM_DA_LINHA = [1140, 36];

const porcento = (fracao: number) => `${(fracao * 100).toFixed(1)}%`;

function LinhaDoHeroi() {
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

function AvisoDeAcesso() {
  if (!BETA_FECHADO) return null;
  return (
    <p className="selo-beta">
      <span>Beta fechado</span> O app está em fase de testes: por enquanto, só contas
      convidadas entram com o Google.
    </p>
  );
}

function Heroi() {
  return (
    <div className="escura topo-da-pagina">
      <section className="heroi faixa" aria-labelledby="titulo-heroi">
        <div className="heroi-texto">
          <p className="olho">Inteligência financeira · B3 e EUA</p>
          <h1 id="titulo-heroi">{ASSINATURA}</h1>
          <p className="subtitulo">
            Pesquise ativos, entenda retorno, risco e os documentos oficiais das empresas, teste
            estratégias no passado e transforme o estudo em relatórios, com cada número
            explicado em português.
          </p>
          <form
            className="busca"
            action={`${URL_DO_APP}/visao-geral`}
            method="get"
            role="search"
            data-busca=""
            data-app={URL_DO_APP}
          >
            <label htmlFor="busca-ticker">Busque um ativo</label>
            <div className="campo">
              <input
                id="busca-ticker"
                name="ticker"
                type="text"
                autoComplete="off"
                placeholder="PETR4, Petrobras, AAPL, Ibovespa…"
                role="combobox"
                aria-autocomplete="list"
                aria-expanded="false"
                aria-controls="sugestoes"
              />
              <button className="botao primario" type="submit">
                Analisar
              </button>
            </div>
            <ul id="sugestoes" role="listbox" hidden />
          </form>
          <p className="exemplos">
            <span>Experimente:</span>{" "}
            {site.exemplos.map((e) => (
              <a
                key={e.simbolo}
                className="ticker"
                href={linkDoApp("visao-geral", { ticker: e.simbolo })}
              >
                {e.rotulo}
              </a>
            ))}
          </p>
          <div className="acoes">
            <a className="botao secundario" href={`/relatorio/exemplo-${TICKER_DO_EXEMPLO}.pdf`}>
              Ver um relatório de exemplo (PDF)
            </a>
          </div>
          <AvisoDeAcesso />
        </div>
        <div className="heroi-visual" aria-hidden="true">
          {/* HTML pronto: com <img> do React, ele põe sozinho um <link rel="preload"> no <head> */}
          <Bruto
            html={`<img src="/relatorio/${ESTILOS[0].chave}-2.webp" width="560" height="792" alt="">`}
          />
        </div>
      </section>
      <LinhaDoHeroi />
    </div>
  );
}

/** O Report Studio: imagens do PDF de verdade, trocando estilo e página (o site.js troca). */
function Vitrine() {
  const primeiro = ESTILOS[0].chave;
  return (
    <div className="vitrine" data-vitrine="">
      <div className="controles" role="group" aria-label="Estilo do relatório">
        {ESTILOS.map((e, i) => (
          <button
            key={e.chave}
            type="button"
            data-estilo={e.chave}
            aria-pressed={i === 0 ? "true" : "false"}
          >
            {e.nome}
          </button>
        ))}
      </div>
      <div className="folhas">
        <img
          src={`/relatorio/${primeiro}-1.webp`}
          width={560}
          height={792}
          loading="lazy"
          alt={`Capa do relatório de exemplo de ${TICKER_DO_EXEMPLO}`}
          data-pagina="1"
        />
        <img
          src={`/relatorio/${primeiro}-2.webp`}
          width={560}
          height={792}
          loading="lazy"
          alt="Segunda página do relatório de exemplo, com o resumo executivo e os números-chave"
          data-pagina="2"
        />
      </div>
      <p className="legenda">
        Imagens do PDF real gerado pelo app, com dados de exemplo guardados no projeto. Só as
        cores mudam entre os estilos: os números são os mesmos.
      </p>
    </div>
  );
}

export function Inicio() {
  return (
    <>
      <Heroi />
      <section className="faixa secao" aria-labelledby="titulo-frentes">
        <p className="olho">O que você leva</p>
        <h2 id="titulo-frentes">Seis frentes, uma plataforma</h2>
        <div className="grade tres">
          {MODULOS_DO_PRODUTO.map((m) => (
            <article key={m.chave} className="cartao">
              <p className="olho">{m.objetivo}</p>
              <h3>{m.nome}</h3>
              <p>{m.frase}</p>
              <p className="contagem">{contagem(m)}</p>
              <a className="seta" href={`/produto.html#${m.chave}`}>
                Ver o que tem
              </a>
            </article>
          ))}
        </div>
        <p>
          <a className="seta" href="/produto.html">
            Tudo o que o TickerLab faz, e o que vem por aí
          </a>
        </p>
      </section>
      <section id="relatorios" className="faixa secao" aria-labelledby="titulo-estudio">
        <p className="olho">Report Studio</p>
        <h2 id="titulo-estudio">Sua pesquisa merece mais que uma tela</h2>
        <p className="subtitulo">
          Modelo Executivo ou Pesquisa completa, seções na ordem que você quiser, três estilos e
          a prévia do PDF de verdade antes de baixar. Toda versão tem resumo, metodologia e os
          limites da análise.
        </p>
        <Vitrine />
      </section>
      <ChamadaFinal />
    </>
  );
}
