// Página inicial v2 (ADR 0065), a partir do protótipo aprovado em 14/10/2026: hero escuro com a
// busca e o painel do relatório de exemplo, a fita de ativos, as fontes dos dados, o "Por que o
// TickerLab" e a chamada final (o bento das frentes e o Report Studio foram para a página Ferramentas). Os números do painel vêm do
// Python (exemplo.json), os mesmos do PDF de exemplo: nunca escritos à mão.
import { type NumeroDoPainel, amostraRelatorio, exemplo, marca, site } from "../conteudo";
import { AvisoDeAcesso, ChamadaFinal } from "../site/comum";
import { Fundo } from "../site/Fundo";
import { DADOS as RELATORIO_DE_EXEMPLO } from "./RelatorioExemplo";
import {
  ASSINATURA,
  FONTES_DOS_DADOS,
  FRASE_DA_DIFERENCA,
  PRINCIPIOS,
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

const PDF_DE_EXEMPLO = `/relatorio/exemplo-${exemplo.ticker}.pdf`;
// o pedaço da assinatura em destaque no título
const DESTAQUE_DO_TITULO = "auditáveis";

/** "2021-10-11" → "11/10/2021" (sem Date: nada de fuso mudando o dia). */
const dataBr = (iso: string) => iso.split("-").reverse().join("/");
const corDoSinal = (valor: number) => (valor > 0 ? "alta" : valor < 0 ? "queda" : "");

/** "▲ +545,8%" com a seta escondida do leitor de tela (o sinal já diz se subiu ou caiu). */
function Variacao({ numero }: { numero: NumeroDoPainel }) {
  const [seta, ...resto] = numero.texto.split(" ");
  return (
    <>
      <span aria-hidden="true">{seta}</span>
      {` ${resto.join(" ")}`}
    </>
  );
}

// o desenho do painel: a série em base 100 numa caixa de 320 × 96, com folga em cima e embaixo
const LARGURA_DO_GRAFICO = 320;
const ALTURA_DO_GRAFICO = 96;
const FOLGA_DO_GRAFICO = 4;

function pontosDoGrafico(serie: number[]): string {
  const menor = Math.min(...serie);
  const faixa = Math.max(...serie) - menor || 1;
  const util = ALTURA_DO_GRAFICO - 2 * FOLGA_DO_GRAFICO;
  return serie
    .map((valor, i) => {
      const x = (i * LARGURA_DO_GRAFICO) / (serie.length - 1);
      const y = FOLGA_DO_GRAFICO + ((menor + faixa - valor) / faixa) * util;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function GraficoDoPainel() {
  const pontos = pontosDoGrafico(exemplo.serie);
  const base = `${LARGURA_DO_GRAFICO},${ALTURA_DO_GRAFICO}`;
  return (
    <svg
      className="v2-grafico"
      viewBox={`0 0 ${LARGURA_DO_GRAFICO} ${ALTURA_DO_GRAFICO}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Preço de fechamento de ${exemplo.codigo} no período, em base 100`}
    >
      <defs>
        <linearGradient id="v2-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={marca.azul} stopOpacity=".45" />
          <stop offset="1" stopColor={marca.azul} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon className="area" points={`0,${ALTURA_DO_GRAFICO} ${pontos} ${base}`} />
      <polyline className="linha" pathLength={1} points={pontos} />
    </svg>
  );
}

/** O número principal (Ledger): o retorno total do relatório de exemplo, o desenho e três métricas. */
function PainelDoExemplo() {
  const periodo = `${dataBr(exemplo.inicio)} a ${dataBr(exemplo.fim)}`;
  return (
    <div className="v2-painel-pilha">
      <article
        className="v2-painel"
        aria-label={`Números-chave do relatório de exemplo de ${exemplo.codigo}`}
      >
        <header className="v2-painel-topo">
          <span className="v2-etiqueta">Relatório de exemplo</span>
          <span className="ticker">{exemplo.codigo}</span>
        </header>
        <p className="v2-rotulo">Retorno total · {periodo}</p>
        <p className={`v2-numero ${corDoSinal(exemplo.retorno_total.valor)}`}>
          <Variacao numero={exemplo.retorno_total} />
        </p>
        <p className="v2-apoio">
          <span className={corDoSinal(exemplo.retorno_ao_ano.valor)}>
            <Variacao numero={exemplo.retorno_ao_ano} />
          </span>{" "}
          ao ano
        </p>
        <GraficoDoPainel />
        <dl className="v2-metricas">
          <div>
            <dt>Maior queda</dt>
            {/* a maior queda nunca é positiva: a seta é sempre para baixo */}
            <dd className="queda">
              <span aria-hidden="true">▼</span>
              {` ${exemplo.maior_queda.texto}`}
            </dd>
          </div>
          <div>
            <dt>Volatilidade</dt>
            <dd>{exemplo.volatilidade.texto} a.a.</dd>
          </div>
          <div>
            <dt>Sharpe</dt>
            <dd>{exemplo.sharpe.texto}</dd>
          </div>
        </dl>
        <footer className="v2-painel-rodape">
          <span>Cada número explicado em português</span>
          <a className="seta" href={PDF_DE_EXEMPLO}>
            Abrir o PDF
          </a>
        </footer>
      </article>
      <aside className="v2-flutuante" aria-label="Ficha Foi sorte?">
        <span className="v2-etiqueta v2-etiqueta-ambar">Foi sorte?</span>
        <p>
          Um bom resultado no passado pode ser acaso. A ficha mostra se ele resiste quando
          tiramos a sorte da conta.
        </p>
      </aside>
      <p className="v2-nota">
        Dados de exemplo do relatório (Yahoo Finance, até {dataBr(exemplo.fim)}). Não é
        recomendação de investimento.
      </p>
    </div>
  );
}

function Busca() {
  return (
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
  );
}

function Heroi() {
  const [antes, depois] = ASSINATURA.split(DESTAQUE_DO_TITULO);
  return (
    <Fundo>
      <section className="heroi faixa" aria-labelledby="titulo-heroi">
        <div className="heroi-texto">
          <a className="v2-pilula" href="/produto.html#estrategias">
            <span className="v2-ponto" aria-hidden="true" />
            Novo · ficha “Foi sorte?”
            <span className="v2-pilula-seta" aria-hidden="true">
              →
            </span>
          </a>
          <h1 id="titulo-heroi">
            {antes}
            <span className="v2-degrade">{DESTAQUE_DO_TITULO}</span>
            {depois}
          </h1>
          <p className="subtitulo">
            Pesquise empresas, entenda resultado, risco e os documentos oficiais, e transforme o
            estudo em relatórios, com cada número explicado em português e ligado à fonte.
          </p>
          <Busca />
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
          {/* no celular o painel não aparece: o PDF de exemplo fica a um toque por aqui */}
          <div className="acoes v2-so-no-celular">
            <a className="botao secundario" href={PDF_DE_EXEMPLO}>
              Ver um relatório de exemplo (PDF)
            </a>
          </div>
          <AvisoDeAcesso />
        </div>
        <PainelDoExemplo />
      </section>
    </Fundo>
  );
}

/** Só códigos e nomes, nenhum preço; a segunda volta existe para a fita emendar sem pulo. */
function FitaDeAtivos() {
  return (
    <section className="v2-fita" aria-label="Alguns dos ativos da busca">
      <p className="v2-fita-rotulo">
        {site.total_de_ativos.toLocaleString("pt-BR")} ativos na busca
      </p>
      <div className="v2-fita-trilho">
        <div className="v2-fita-faixa">
          {[false, true].map((repeticao) => (
            <ul key={String(repeticao)} aria-hidden={repeticao ? "true" : undefined}>
              {site.fita.map((ativo) => (
                <li key={ativo.simbolo}>
                  <b>{ativo.codigo}</b>
                  {ativo.nome}
                </li>
              ))}
            </ul>
          ))}
        </div>
      </div>
    </section>
  );
}

function FontesDosDados() {
  return (
    <section className="faixa v2-fontes" aria-label="De onde vêm os dados">
      <p className="olho">De onde vêm os dados</p>
      <ul>
        {FONTES_DOS_DADOS.map(([nome, oQueVem]) => (
          <li key={nome}>
            <strong>{nome}</strong>
            <span>{oQueVem}</span>
          </li>
        ))}
      </ul>
      <a className="seta" href="/metodologia.html">
        Fontes e metodologia
      </a>{" "}
      <a className="seta" href={RELATORIO_DE_EXEMPLO.caminho}>
        O que a base cruza: {amostraRelatorio.empresa}
      </a>
    </section>
  );
}

function PorQueOTickerLab() {
  const [comeco, destaque] = FRASE_DA_DIFERENCA;
  return (
    <div className="escura v2-diferenca">
      <section className="faixa secao" aria-labelledby="titulo-diferenca">
        <p className="olho">Por que o TickerLab</p>
        <h2 id="titulo-diferenca">
          {comeco} <span className="v2-degrade">{destaque}</span>
        </h2>
        <div className="grade tres">
          {PRINCIPIOS.map(([titulo, texto], i) => (
            <article key={titulo} className="v2-principio">
              <span className="numero">{String(i + 1).padStart(2, "0")}</span>
              <h3>{titulo}</h3>
              <p>{texto}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

export function Inicio() {
  return (
    <>
      <Heroi />
      <FitaDeAtivos />
      <FontesDosDados />
      <PorQueOTickerLab />
      <ChamadaFinal />
    </>
  );
}
