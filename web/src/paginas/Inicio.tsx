// Página inicial do posicionamento v3 (ADR 0127, linha 774 da fila): a TickerLab é uma CLI de M&A e
// análise de investimento para o analista e o agente de IA dele. A ordem da página é a do que nos
// propomos a fazer: a assinatura com a CLI à vista, o que dá para pedir, como o agente a usa, a base
// por trás (números do catálogo e da medição, nunca digitados), o que ela liga pelo CNPJ, os
// cruzamentos, as quatro regras e, por último, as outras janelas da mesma base (as análises abertas,
// o app e a API). O estudo do dia, as novidades e a lista de fontes saíram da inicial: continuam em
// Relatórios, Novidades e Dados.
import type { ReactNode } from "react";
import { BuscaDaBase } from "../site/BuscaDaBase";
import { baseEmNumeros, catalogo } from "../conteudo";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { Cruzamentos } from "../site/Cruzamentos";
import { AvisoDeAcesso, ChamadaFinal } from "../site/comum";
import { Fundo } from "../site/Fundo";
import { LigadoPeloCnpj } from "../site/LigadoPeloCnpj";
import { ASSINATURA, REGRAS_DA_BASE, URL_DA_API, linkDoApp } from "../site/textos";
import { Vitrine } from "../site/Vitrine";

export const DADOS = {
  caminho: "/",
  ferramenta: true,
  titulo: "TickerLab",
  descricao:
    "CLI de M&A e análise de investimento para o analista e o agente de IA dele: cada número de " +
    "fonte pública brasileira, com data, fonte e caminho até o original.",
};

// o pedaço da assinatura em destaque no título
const DESTAQUE_DO_TITULO = "M&A e análise de investimento";
const SUBTITULO =
  "Você pede; o seu agente de IA roda a tickerlab e devolve a análise com a fonte e a data de " +
  "cada número.";
// o ativo continua o mesmo da ADR 0099: a coleta auditável
const O_QUE_HA_POR_TRAS =
  "Coleta segura e auditável das fontes públicas brasileiras: cada número com data, fonte e " +
  "caminho até o original.";
// onde a documentação da API ensina a pedir a chave (site-api/documentacao, seção "comecar")
const COMO_PEDIR_A_CHAVE = `${URL_DA_API}/documentacao/#comecar`;
const milhares = (n: number) => n.toLocaleString("pt-BR");

// O terminal do herói: só comandos que existem (docs/cli.md), sem saída inventada.
const LINHAS_DO_TERMINAL: [string, string][] = [
  ["empresas de um setor numa UF, direto para o Excel", "tickerlab prospectar --cnae 4711 --uf PE --planilha alvos.xlsx"],
  ["a ficha de uma empresa pelo CNPJ", "tickerlab empresa <cnpj>"],
  ["as demonstrações como estavam públicas naquele dia", "tickerlab demonstracoes <cnpj> --como-era 2024-12-31"],
  ["o setor, no formato que o agente lê", "tickerlab setor eletricas --json"],
];

// O que dá para pedir: um cartão por comando, com o que ele devolve (docs/cli.md e as instruções do
// agente em cli/tickerlab/instrucoes/AGENTS.md).
const COMANDOS: [string, string, string][] = [
  [
    "Triagem de uma empresa",
    "tickerlab empresa <cnpj>",
    "O cadastro na Receita Federal e, da companhia aberta, cada demonstração devida à CVM, com o prazo, a data da entrega e os dias de atraso.",
  ],
  [
    "Prospecção por setor",
    "tickerlab prospectar --cnae … --uf …",
    "Empresas pela atividade, UF, município, porte, situação e idade. Só a empresa: sem sócio, contato nem endereço.",
  ],
  [
    "Demonstrações como eram",
    "tickerlab demonstracoes <cnpj> --como-era AAAA-MM-DD",
    "As demonstrações financeiras como estavam públicas na data pedida, sem enxergar o que só saiu depois.",
  ],
  [
    "Ficha do setor",
    "tickerlab setor <chave>",
    "As séries da agência reguladora do setor, com a concentração e a fatia de cada companhia, e as notas de método.",
  ],
  [
    "Fundo pelo CNPJ",
    "tickerlab fundo <cnpj>",
    "O cadastro e as taxas do fundo e a carteira que ele declarou à CVM.",
  ],
  [
    "Direto para o Excel",
    "--planilha alvos.xlsx",
    "A resposta vira planilha: uma aba por tabela, com a fonte e a data de publicação em cada linha.",
  ],
];

// As travas que as instruções do agente trazem (cli/tickerlab/instrucoes/AGENTS.md, "Travas").
const TRAVAS_DO_AGENTE: [string, string][] = [
  ["Fonte e data em cada número", "O agente cita de onde veio e quando ficou público."],
  ["Nenhum número inventado", "O que a CLI não devolveu, o agente diz que não achou."],
  ["Nada é recomendação de investimento", "O agente descreve, compara e calcula; a decisão é sua."],
  ["Sem dado de pessoa física", "A API não serve sócio pessoa física, CPF, MEI nem empresário individual."],
  ["A chave é segredo", "Ela nunca passa pelo chat nem pelo histórico do terminal."],
];

const PASSOS_PARA_COMECAR: [string, ReactNode][] = [
  [
    "Peça a chave",
    <>
      A chave é da organização. O acesso está em beta fechado, sem cobrança:{" "}
      <a href={COMO_PEDIR_A_CHAVE} rel="noopener">
        como pedir
      </a>
      .
    </>,
  ],
  [
    "Instale e entre",
    <>
      A CLI instala com o <code>pipx</code>, sem o Git, e <code>tickerlab login</code> guarda a
      chave num arquivo que só você lê.
    </>,
  ],
  [
    "Entregue as instruções ao agente",
    <>
      <code>tickerlab instrucoes</code> escreve o arquivo que ensina os comandos e as travas ao
      Claude Code, ao Codex e a outros agentes.
    </>,
  ],
];

/** O terminal do herói: os comandos, um por linha, cada um com o que pede. */
function Terminal() {
  return (
    <div className="v2-painel-pilha">
      <figure className="v2-painel v2-terminal" aria-labelledby="titulo-do-terminal">
        <figcaption className="v2-painel-topo">
          <span className="v2-etiqueta" id="titulo-do-terminal">
            No terminal ou pelo agente
          </span>
          <span className="ticker">tickerlab</span>
        </figcaption>
        <pre className="v2-terminal-linhas">
          {LINHAS_DO_TERMINAL.map(([comentario, comando]) => (
            <code key={comando}>
              <span className="v2-terminal-comentario">{`# ${comentario}\n`}</span>
              <span className="v2-terminal-cifrao" aria-hidden="true">
                ${" "}
              </span>
              {`${comando}\n`}
            </code>
          ))}
        </pre>
        <footer className="v2-painel-rodape">
          <span>Cada resposta com fonte, data e licença</span>
          <a className="seta" href="#comandos">
            Os comandos
          </a>
        </footer>
      </figure>
    </div>
  );
}

function Heroi() {
  const [antes, depois] = ASSINATURA.split(DESTAQUE_DO_TITULO);
  return (
    <Fundo>
      <section className="heroi faixa" aria-labelledby="titulo-heroi">
        <div className="heroi-texto">
          <h1 id="titulo-heroi">
            {antes}
            <span className="v2-degrade">{DESTAQUE_DO_TITULO}</span>
            {depois}
          </h1>
          <p className="subtitulo">{SUBTITULO}</p>
          <p className="v2-para-quem">{O_QUE_HA_POR_TRAS}</p>
          <div className="acoes">
            <a className="botao primario" href={COMO_PEDIR_A_CHAVE} rel="noopener">
              Pedir uma chave
            </a>
            <a className="botao secundario" href="#comandos">
              Ver os comandos
            </a>
          </div>
          <AvisoDeAcesso />
        </div>
        <Terminal />
      </section>
    </Fundo>
  );
}

function Comandos() {
  return (
    <section className="faixa secao v2-comandos" id="comandos" aria-labelledby="titulo-comandos">
      <p className="olho">O que dá para pedir</p>
      <h2 id="titulo-comandos">Do CNPJ à planilha, um comando por pergunta</h2>
      <p className="subtitulo">
        A CLI só repassa o que a API de dados serve: a mesma resposta para você, no terminal, e
        para o agente, em JSON.
      </p>
      <div className="grade tres">
        {COMANDOS.map(([titulo, comando, texto]) => (
          <article key={titulo} className="cartao v2-comando">
            <h3>{titulo}</h3>
            <p className="v2-comando-linha">
              <code>{comando}</code>
            </p>
            <p>{texto}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function ParaOAgente() {
  return (
    <section className="faixa secao v2-agente" aria-labelledby="titulo-agente">
      <p className="olho">Para o seu agente de IA</p>
      <h2 id="titulo-agente">O agente roda a CLI; as travas vão junto</h2>
      <p className="subtitulo">
        O pacote leva as instruções do agente. Elas ensinam os comandos e o que ele não pode fazer.
      </p>
      <div className="v2-agente-colunas">
        <ol className="v2-passos-da-cli">
          {PASSOS_PARA_COMECAR.map(([titulo, texto]) => (
            <li key={titulo}>
              <strong>{titulo}</strong>
              <span>{texto}</span>
            </li>
          ))}
        </ol>
        <dl className="v2-travas">
          {TRAVAS_DO_AGENTE.map(([titulo, texto]) => (
            <div key={titulo}>
              <dt>{titulo}</dt>
              <dd>{texto}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

/** Os quatro números da base, cada um com a conta recolhida ao lado. */
function PainelDaBase() {
  const { totais, ligado_pelo_cnpj: ligado } = catalogo;
  const { numeros, medido_em_curto } = baseEmNumeros;
  return (
    <div className="v2-painel-pilha">
      <article className="v2-painel v2-painel-base" aria-labelledby="titulo-da-base">
        <header className="v2-painel-topo">
          <span className="v2-etiqueta" id="titulo-da-base">
            O que a base tem
          </span>
          <span className="ticker">Medido em {medido_em_curto}</span>
        </header>
        <dl className="v2-base-numeros">
          <div>
            <dt>tabelas, cada uma com contrato</dt>
            <dd className="v2-numero">{milhares(totais.tabelas)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  Contamos as tabelas do catálogo de contratos da base. Cada contrato diz a fonte,
                  a licença, as datas e a frequência de atualização; tabela nova entra na conta
                  sozinha.
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
          <div>
            <dt>tabelas ligadas pelo CNPJ</dt>
            <dd className="v2-numero">{milhares(ligado.tabelas)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  {`Contamos as tabelas do catálogo com uma coluna de CNPJ (ou da raiz dele), mais as da rede que liga empresas, fundos e tickers. Vêm de ${ligado.orgaos} órgãos públicos.`}
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
          <div>
            <dt>fontes públicas, cada uma com a sua licença</dt>
            <dd className="v2-numero">{milhares(totais.fontes)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  {`Uma fonte é um órgão ou publicação com a licença que ela mesma publica. ${totais.fontes_em_consulta} delas ainda não responderam por escrito sobre uso comercial: até a resposta, tratamos o dado delas como não comercial.`}
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
          <div>
            <dt>companhias abertas com demonstrações</dt>
            <dd className="v2-numero">{milhares(numeros.empresas)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  {`CNPJs distintos com ao menos uma demonstração financeira guardada, contados na base em ${medido_em_curto}. São ${milhares(numeros.linhas_de_demonstracoes)} linhas, cada uma com o dia em que o valor ficou público.`}
                </p>
              </ComoFoiCalculado>
            </dd>
          </div>
        </dl>
        <footer className="v2-painel-rodape">
          <span>Cada tabela com fonte, licença e data</span>
          <a className="seta" href="/dados.html">
            A base inteira
          </a>
        </footer>
      </article>
    </div>
  );
}

/** A base que a CLI consulta: os números medidos e a busca aberta, numa faixa escura só. */
function BasePorTras() {
  return (
    <div className="escura v2-base-fundo">
      <section className="faixa secao v2-base-faixa" aria-labelledby="titulo-base-por-tras">
        <div>
          <p className="olho">A base por trás</p>
          <h2 id="titulo-base-por-tras">Toda resposta sai de uma fonte pública, com a data</h2>
          <p className="subtitulo">
            A CLI consulta a base que coletamos dos órgãos públicos. Experimente sem chave: busque
            uma companhia aberta e veja a fonte ao lado de cada número.
          </p>
          <div data-busca-base>
            <BuscaDaBase />
          </div>
        </div>
        <PainelDaBase />
      </section>
    </div>
  );
}

function RegrasDaBase() {
  return (
    <section className="faixa secao v2-regras" aria-labelledby="titulo-regras">
      <p className="olho">Método</p>
      <h2 id="titulo-regras">Por que confiar num número daqui</h2>
      <p className="subtitulo">
        Quatro regras valem para toda tabela da base. Abra cada uma para ler como funciona.
      </p>
      <div className="grade v2-regras-lista">
        {REGRAS_DA_BASE.map(([titulo, texto]) => (
          <ComoFoiCalculado key={titulo} resumo={titulo}>
            <p>{texto}</p>
          </ComoFoiCalculado>
        ))}
      </div>
    </section>
  );
}

/** As outras janelas da mesma base, para quem não usa terminal (ADR 0127, item 2). */
function OutrasJanelas() {
  return (
    <section className="faixa v2-janelas" aria-labelledby="titulo-janelas">
      <h2 id="titulo-janelas" className="olho">
        Sem terminal
      </h2>
      <p>
        A mesma base abre pelo <a href={linkDoApp()}>app</a>, com a sua conta, e pela{" "}
        <a href={URL_DA_API} rel="noopener">
          TickerLab Data
        </a>
        , a API de dados, para o seu sistema. Os <a href="/relatorios.html">relatórios</a> de
        exemplo mostram o que sai dela.
      </p>
    </section>
  );
}

export function Inicio() {
  return (
    <>
      <Heroi />
      <Comandos />
      <ParaOAgente />
      <BasePorTras />
      <LigadoPeloCnpj />
      <Cruzamentos />
      <RegrasDaBase />
      <Vitrine />
      <OutrasJanelas />
      <ChamadaFinal
        titulo="Comece pela chave"
        subtitulo={
          "O acesso à CLI e à API está em beta fechado, sem cobrança. A documentação é aberta e " +
          "diz como pedir a chave da sua organização."
        }
      >
        <div className="acoes">
          <a className="botao primario" href={COMO_PEDIR_A_CHAVE} rel="noopener">
            Pedir uma chave
          </a>
          <a className="botao secundario" href={linkDoApp()}>
            Abrir o app
          </a>
        </div>
        <p className="v2-aviso-final">
          Os dados vêm de fontes públicas e podem ter atraso ou erros. Nada aqui é recomendação de
          investimento.
        </p>
      </ChamadaFinal>
    </>
  );
}
