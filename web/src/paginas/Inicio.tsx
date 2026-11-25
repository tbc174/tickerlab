// Página inicial de um site só (linha 966 da fila, 16/11/2026): tickerlab.com.br passa a ser o único site
// de produto, com o visual do TickerLab Data (escolha do Tiago). Uma proposta, a base com fonte e data, e três
// portas nesta ordem: o conector MCP (o principal desde 16/11), a CLI e a API. O topo tem uma frase, a janela
// de código com a resposta da API (o mesmo pedido pelas três portas) e um único botão de chave. Depois: as
// três portas, a demonstração da conversa, as travas (uma lista só para as três), "como era na data", o que a
// base tem (números do catálogo e da medição, nunca digitados), o que ela liga pelo CNPJ, os cruzamentos e as
// análises abertas. As quatro regras ficam em Dados e em Metodologia; a API documentada, na raiz da própria API.
import { Fragment } from "react";
import type { ReactNode } from "react";
import { BuscaDaBase } from "../site/BuscaDaBase";
import { baseEmNumeros, catalogo, consultasDasPortas, paginasDoApp } from "../conteudo";
import type { CelulaDaPorta } from "../conteudo";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { Cruzamentos } from "../site/Cruzamentos";
import { AvisoDeAcesso, ChamadaFinal } from "../site/comum";
import { Fundo } from "../site/Fundo";
import { LigadoPeloCnpj } from "../site/LigadoPeloCnpj";
import { URL_DA_API, URL_DO_CODIGO, linkDoApp } from "../site/textos";
import { Vitrine } from "../site/Vitrine";

export const DADOS = {
  caminho: "/",
  ferramenta: true,
  titulo: "TickerLab",
  descricao:
    "Dados das empresas brasileiras, da fonte, com data e licença: pelo conector MCP no Claude, pela CLI " +
    "ou pela API, para M&A e análise de investimento.",
};

// a frase do topo, com o pedaço em destaque (o mesmo desenho do TickerLab Data)
export const FRASE_DO_TOPO = "Dados das empresas brasileiras, da fonte, com data e licença.";
const DESTAQUE_DA_FRASE = "da fonte";
const PORTAS_DO_TOPO =
  "Para M&A e análise de investimento. Pergunte no Claude pelo conector, rode a CLI no terminal ou chame " +
  "a API: a mesma base, com o documento de onde saiu cada número e o dia em que ficou público.";
// onde a documentação da API ensina a pedir a chave (site-api/documentacao, seção "comecar"): o único caminho
export const COMO_PEDIR_A_CHAVE = `${URL_DA_API}/documentacao/#comecar`;
const DOCUMENTACAO_DA_API = `${URL_DA_API}/documentacao/`;
const ROTAS_DA_API = `${URL_DA_API}/#catalogo`;
const milhares = (n: number) => n.toLocaleString("pt-BR");

// --- a janela do topo: o mesmo pedido pelas três portas e a resposta que a API devolve ---------------------
// A empresa é a Petrobras (CNPJ de companhia aberta, público). O valor fica como marcador; as datas são as da
// amostra da CVM abaixo, e a data da pergunta sai da mesma constante do pedido (nunca digitada duas vezes).
const CNPJ_DO_EXEMPLO = "33000167000101";
// uma resposta de verdade: a DFP 2024 da Petrobras, entregue à CVM em 26/02/2025 (a amostra dos testes,
// `tests/arquivos/cvm/fundamentos/dfp_cia_aberta_2024.zip`; `tests/test_site.py` confere as datas no arquivo)
const DIA_DO_EXEMPLO = "2025-06-30";
export const RESPOSTA_DO_EXEMPLO = {
  descricao: "Receita de Venda de Bens e/ou Serviços",
  periodo: "2024-12-31",
  publicado: "2025-02-26",
};
/** "2025-06-30" → "30/06/2025". */
const dataBr = (iso: string) => iso.split("-").reverse().join("/");

type Trecho = [classe: "" | "k" | "s" | "n" | "c" | "eu", texto: string];
const PEDIDOS: { porta: string; nome: string; linhas: Trecho[][] }[] = [
  {
    porta: "conector",
    nome: "Conector",
    linhas: [
      [["c", "# no Claude, com o conector do TickerLab"]],
      [["eu", `As contas da Petrobras como estavam públicas em ${dataBr(DIA_DO_EXEMPLO)}.`]],
      [["c", "# a IA chama a ferramenta do conector"]],
      [
        ["k", "demonstracoes"],
        ["", "(cnpj="],
        ["s", `"${CNPJ_DO_EXEMPLO}"`],
        ["", ", como_era_em="],
        ["s", `"${DIA_DO_EXEMPLO}"`],
        ["", ")"],
      ],
    ],
  },
  {
    porta: "cli",
    nome: "CLI",
    linhas: [
      [["c", "# no terminal, ou pelo seu agente de IA"]],
      [
        ["k", "$ "],
        ["", `tickerlab demonstracoes ${CNPJ_DO_EXEMPLO} \\`],
      ],
      [["", `    --como-era ${DIA_DO_EXEMPLO} --json`]],
    ],
  },
  {
    porta: "api",
    nome: "API",
    linhas: [
      [["c", "# do seu sistema, com a chave no cabeçalho"]],
      [["", `curl "${URL_DA_API}/data/v1/companies/${CNPJ_DO_EXEMPLO}/financials?known_at=${DIA_DO_EXEMPLO}" \\`]],
      [
        ["", "  -H "],
        ["s", '"Authorization: Bearer $TICKERLAB_CHAVE"'],
      ],
    ],
  },
];

function Linhas({ linhas }: { linhas: Trecho[][] }) {
  return (
    <>
      {linhas.map((linha, i) => (
        <span key={i} className="janela-linha">
          {linha.map(([classe, texto], j) =>
            classe ? (
              <span key={j} className={classe}>
                {texto}
              </span>
            ) : (
              texto
            ),
          )}
          {"\n"}
        </span>
      ))}
    </>
  );
}

/** A resposta da API para o pedido acima: a forma real, com a fonte e a licença em destaque. */
function RespostaDoTopo() {
  return (
    <pre className="janela-resposta">
      <code>
        {"{\n  "}
        <span className="k">"cnpj"</span>: <span className="s">"{CNPJ_DO_EXEMPLO}"</span>, <span className="k">"known_at"</span>:{" "}
        <span className="s">"{DIA_DO_EXEMPLO}"</span>
        {",\n  "}
        <span className="k">"rows"</span>
        {": [{\n    "}
        <span className="k">"account"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="s">"3.01"</span>, <span className="k">"source"</span>:{" "}
        <span className="s">"cvm-hist-dfp"</span>
        {",\n                 "}
        <span className="k">"published_at"</span>: <span className="s">"{RESPOSTA_DO_EXEMPLO.publicado}"</span>
        {" },\n    "}
        <span className="k">"description"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="s">"{RESPOSTA_DO_EXEMPLO.descricao}"</span>
        {", … },\n    "}
        <span className="k">"document"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="s">"DFP"</span>
        {", … },\n    "}
        <span className="k">"reference_period"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="s">"{RESPOSTA_DO_EXEMPLO.periodo}"</span>
        {", … },\n    "}
        <span className="k">"value"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="n">&lt;valor da fonte&gt;</span>
        {", … }\n  }, …],\n  "}
        <span className="k">"truncated"</span>: <span className="n">false</span>
        {",\n  "}
        <span className="destaque-rastro">
          <span className="k">"sources"</span>
          {": [{\n    "}
          <span className="k">"source"</span>: <span className="s">"cvm-hist-dfp"</span>
          {",\n    "}
          <span className="k">"license"</span>: <span className="s">"ODbL (dados abertos da CVM; citar a fonte)"</span>
          {",\n    "}
          <span className="k">"attribution"</span>: <span className="s">"Fonte: CVM, Portal de Dados Abertos (ODbL)"</span>
          {"\n  }]"}
        </span>
        {"\n}"}
      </code>
    </pre>
  );
}

/**
 * A janela do topo. As abas são botões de rádio (sem JavaScript): cada uma mostra o pedido por uma porta, e a
 * resposta embaixo é a mesma, porque as três portas consultam a mesma API.
 */
function JanelaDoTopo() {
  return (
    <div className="janela guias" role="group" aria-label="O mesmo pedido pelas três portas e a resposta da API">
      {PEDIDOS.map(({ porta }, i) => (
        <input
          key={porta}
          className="guia-escolha"
          type="radio"
          name="janela-porta"
          id={`janela-${porta}`}
          data-ordem={i}
          defaultChecked={i === 0}
        />
      ))}
      <div className="janela-topo">
        {PEDIDOS.map(({ porta, nome }, i) => (
          <label key={porta} className="guia-rotulo" htmlFor={`janela-${porta}`} data-ordem={i}>
            {nome}
          </label>
        ))}
        <span className="status">200 OK</span>
      </div>
      {PEDIDOS.map(({ porta, linhas }, i) => (
        <pre key={porta} className="janela-pedido guia-painel" data-porta={porta} data-ordem={i}>
          <code>
            <Linhas linhas={linhas} />
          </code>
        </pre>
      ))}
      <RespostaDoTopo />
      <p className="janela-nota">
        <span>
          <b>source, published_at, license</b>: de onde saiu, quando ficou público, sob qual licença.
        </span>
        <span>
          Uma linha da resposta real: a DFP 2024 da Petrobras, entregue à CVM em 26/02/2025. O valor aparece como marcador.
        </span>
      </p>
    </div>
  );
}

const PROVAS_DO_TOPO = ["Fonte e data em cada número", "Como era na data em toda consulta", "Sem CPF nem contato de pessoa"];

function Heroi() {
  const [antes, depois] = FRASE_DO_TOPO.split(DESTAQUE_DA_FRASE);
  return (
    <Fundo>
      <section className="heroi faixa heroi-janela" aria-labelledby="titulo-heroi">
        <div className="heroi-texto">
          <p className="pilula-do-beta">
            <span className="ponto" aria-hidden="true" />
            Beta fechado · sem cobrança
          </p>
          <h1 id="titulo-heroi">
            {antes}
            <span className="v2-degrade">{DESTAQUE_DA_FRASE}</span>
            {depois}
          </h1>
          <p className="subtitulo">{PORTAS_DO_TOPO}</p>
          <div className="acoes">
            <a className="botao primario" href={COMO_PEDIR_A_CHAVE} rel="noopener">
              Pedir uma chave
            </a>
            <a className="botao secundario" href="#portas">
              Ver as três portas
            </a>
          </div>
          <ul className="provas-do-topo">
            {PROVAS_DO_TOPO.map((prova) => (
              <li key={prova}>{prova}</li>
            ))}
          </ul>
          <AvisoDeAcesso />
        </div>
        <JanelaDoTopo />
      </section>
    </Fundo>
  );
}

// --- as três portas, uma base -------------------------------------------------------------------------------
// Texto aprovado pelo Tiago em 24/11/2026 (PR 4 da frente 2). Os três cartões, a lista do que dá para pedir (da
// lista única das portas, conector_remoto/consultas_das_portas.py, via web/conteudo/consultas.json; um teste
// confere a página gerada) e os passos para começar. As âncoras antigas (#conector, #comandos, #api) levam ao
// cartão de cada porta.
const GUIA_DO_ANALISTA = `${URL_DO_CODIGO}/blob/main/docs/guia-do-analista-conector.md`;
const GUIA_DA_CLI = `${URL_DO_CODIGO}/blob/main/docs/cli.md`;

// (âncora, nome, selo, para quem, a linha de exemplo, o link e para onde ele leva)
const PORTAS: [string, string, string, ReactNode, string, string, string][] = [
  [
    "conector",
    "Conector MCP",
    "Principal",
    <>
      No Claude e no ChatGPT, sem instalar nada: você pergunta em português e a IA consulta a base. O MCP é o
      padrão aberto que liga uma IA a uma fonte de dados; o conector traz fluxos prontos de triagem, alvos,
      compradores, comparáveis e dossiê.
    </>,
    "analise_completa · buscar_empresas",
    "O guia do analista",
    GUIA_DO_ANALISTA,
  ],
  [
    "comandos",
    "CLI",
    "Terminal",
    <>
      No terminal ou pelo seu agente de IA: um comando por pergunta, em JSON ou direto para o Excel (
      <code>--planilha</code>). O pacote leva as instruções do agente: os comandos e o que ele não pode fazer.
    </>,
    "tickerlab analise <cnpj>",
    "Os comandos",
    GUIA_DA_CLI,
  ],
  [
    "api",
    "API",
    "TickerLab Data",
    <>
      No seu sistema: JSON, a chave no cabeçalho, a licença da fonte em cada resposta e lotes de CNPJs num pedido
      só; as rotas de consulta aceitam <code>known_at</code>, para pedir a base como era na data.
    </>,
    "GET /data/v1/companies/{cnpj}/analysis",
    "A documentação da API",
    DOCUMENTACAO_DA_API,
  ],
];

const NOMES_DAS_PORTAS: ["conector" | "cli" | "api", string][] = [
  ["conector", "Conector"],
  ["cli", "CLI"],
  ["api", "API"],
];

/** O texto com os trechos entre crases em código (a frase curta da porta que não tem a consulta). */
function ComCodigo({ texto }: { texto: string }) {
  return <>{texto.split("`").map((trecho, i) => (i % 2 === 1 ? <code key={i}>{trecho}</code> : trecho))}</>;
}

/** O nome da consulta numa porta, em código, ou a frase curta quando a porta não a tem. */
function NaPorta({ celula }: { celula: CelulaDaPorta }) {
  if (celula.nomes) {
    return (
      <>
        {celula.nomes.map((nome, i) => (
          <span key={nome}>
            {i > 0 && ", "}
            <code>{nome}</code>
          </span>
        ))}
      </>
    );
  }
  return <ComCodigo texto={celula.frase ?? ""} />;
}

function ConsultasDasPortas() {
  return (
    <>
      <h3 className="consultas-titulo">O que dá para pedir, e o nome em cada porta</h3>
      <ul className="consultas-grade">
        {consultasDasPortas.map((consulta) => (
          <li key={consulta.chave} className="consulta">
            <h4>{consulta.nome}</h4>
            <p>{consulta.resumo}</p>
            <dl>
              {NOMES_DAS_PORTAS.map(([porta, nome]) => (
                <Fragment key={porta}>
                  <dt>{nome}</dt>
                  <dd>
                    <NaPorta celula={consulta[porta]} />
                  </dd>
                </Fragment>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}

const PASSOS_PARA_COMECAR: [string, ReactNode][] = [
  [
    "Peça a chave.",
    <>
      Uma por pessoa, entregue por quem administra o TickerLab na organização; a mesma vale nas três portas. O
      acesso está em beta fechado, sem cobrança:{" "}
      <a href={COMO_PEDIR_A_CHAVE} rel="noopener">
        como pedir
      </a>
      .
    </>,
  ],
  [
    "Ligue a porta.",
    <>
      No Claude, um conector personalizado com o endereço que vem junto com a chave (no ChatGPT, em Apps e
      conectores); no terminal, a CLI instala com o <code>pipx</code> e <code>tickerlab login</code> guarda a
      chave num arquivo que só você lê; no seu sistema, a chave vai no cabeçalho.
    </>,
  ],
  [
    "A chave fica fora do chat.",
    <>
      No conector, você a cola numa página do TickerLab, e o acesso vence sozinho e para quando a chave é
      revogada. Para o agente do PC, <code>tickerlab instrucoes</code> imprime o texto que ensina os comandos e
      as travas.
    </>,
  ],
];

function TresPortas() {
  return (
    <section className="faixa secao portas" id="portas" aria-labelledby="titulo-portas">
      <p className="olho">Três portas, uma base</p>
      <h2 id="titulo-portas">Escolha por onde perguntar; a resposta é a mesma</h2>
      <p className="subtitulo">
        O conector e a CLI só repassam o que a API serve: a mesma chave, as mesmas regras e a fonte e a data em
        cada número.
      </p>
      <div className="portas-grade">
        {PORTAS.map(([ancora, nome, selo, texto, exemplo, link, destino], i) => (
          <article key={ancora} id={ancora} className={`porta${i === 0 ? " principal" : ""}`}>
            <p className="porta-topo">
              <span className="porta-numero">{String(i + 1).padStart(2, "0")}</span>
              <span className="porta-selo">{selo}</span>
            </p>
            <h3>{nome}</h3>
            <p>{texto}</p>
            <code className="porta-exemplo">{exemplo}</code>
            <a className="seta" href={destino} rel="noopener">
              {link}
            </a>
          </article>
        ))}
      </div>
      <ConsultasDasPortas />
      <h3 className="consultas-titulo">Como começar</h3>
      <ol className="v2-passos-da-cli passos-em-linha">
        {PASSOS_PARA_COMECAR.map(([nome, texto]) => (
          <li key={nome}>
            <strong>{nome}</strong>
            <span>{texto}</span>
          </li>
        ))}
      </ol>
      <p className="atalhos">
        <a className="botao secundario" href={DOCUMENTACAO_DA_API} rel="noopener">
          A documentação da API
        </a>
        <a className="botao secundario" href={ROTAS_DA_API} rel="noopener">
          Todas as rotas
        </a>
        <a className="botao secundario" href={GUIA_DO_ANALISTA} rel="noopener">
          O guia do analista
        </a>
      </p>
    </section>
  );
}

// As travas das três portas, numa lista só (antes cada porta repetia as suas): as instruções da CLI
// (cli/tickerlab/instrucoes/AGENTS.md), as do conector e a API, que só serve pessoa física à organização com a
// permissão `pessoa_no_conector` (política de privacidade, versão 19).
const TRAVAS: [string, string][] = [
  ["Fonte e data em cada número", "As instruções da CLI e do conector pedem à IA que cite de onde veio e quando ficou público, e liste à parte o que faltou."],
  ["Nenhum número inventado", "As instruções pedem que a IA diga o que a base não devolveu, em vez de completar."],
  ["Pessoa física só com permissão", "Sem a permissão de ver pessoas, desligada por padrão, a API não serve sócio pessoa física, MEI nem empresário individual; com ela, só o nome do sócio ou do titular, a qualificação e a data de entrada, nunca CPF, menor de idade, endereço ou contato. O conector confere cada resposta e recusa a que trouxer campo fora disso."],
  ["A chave não vai ao chat", "No conector ela é colada numa página do TickerLab; na CLI, fica num arquivo que só você lê. Revogada, o acesso para na chamada seguinte."],
  ["Só leitura, as mesmas regras", "Nenhuma ferramenta escreve nem envia nada. Os comandos de leitura da CLI têm ferramenta no conector, com o mesmo pedido à API, e um teste falha se um lado ficar para trás."],
  ["Nada é recomendação de investimento", "As instruções pedem que a IA descreva, compare e calcule; a decisão é sua."],
];

function Travas() {
  return (
    <section className="faixa secao v2-travas-das-portas" id="travas" aria-labelledby="titulo-travas">
      <p className="olho">Travas</p>
      <h2 id="titulo-travas">As mesmas travas nas três portas</h2>
      <dl className="v2-travas travas-em-grade">
        {TRAVAS.map(([titulo, texto]) => (
          <div key={titulo}>
            <dt>{titulo}</dt>
            <dd>{texto}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// A demonstração da conversa (linha 903, PR E): pergunta e resposta fixas, escritas aqui. Nenhum modelo de IA
// roda no site público. As empresas são inventadas e ditas inventadas; a ferramenta e os filtros citados são
// os que o conector registra (há teste). O botão "Entrar para perguntar" só aparece quando a tela existe.
const EMPRESAS_DA_DEMONSTRACAO: [string, string, string, string][] = [
  ["Exemplo Alfa Embalagens Ltda.", "Joinville", "1998", "Demais"],
  ["Exemplo Beta Plásticos Ltda.", "Blumenau", "2004", "Demais"],
  ["Exemplo Gama Embalagens S.A.", "Criciúma", "2009", "Pequeno porte"],
];
const PERGUNTAR = paginasDoApp.find((p) => p.chave === "perguntar");

function DemonstracaoDaConversa() {
  return (
    <section className="faixa secao v2-demonstracao" id="demonstracao" aria-labelledby="titulo-demonstracao">
      <p className="olho">Demonstração</p>
      <h2 id="titulo-demonstracao">A pergunta em português, a resposta com a fonte</h2>
      <p className="subtitulo">
        Uma conversa gravada, para mostrar o formato da resposta. As empresas abaixo são inventadas, e
        nenhuma IA roda nesta página.
      </p>
      <div className="v2-conversa" role="group" aria-label="Conversa de demonstração">
        <p className="v2-fala v2-fala-pergunta">
          Fabricantes de embalagens plásticas em Santa Catarina, abertas antes de 2011.
        </p>
        <div className="v2-fala v2-fala-resposta">
          <p>Três empresas ativas neste exemplo. Em cada linha, o cadastro da Receita:</p>
          <div className="v2-conversa-tabela">
            <table>
              <thead>
                <tr>
                  <th scope="col">Empresa (inventada)</th>
                  <th scope="col">Município</th>
                  <th scope="col">Abertura</th>
                  <th scope="col">Porte na Receita</th>
                </tr>
              </thead>
              <tbody>
                {EMPRESAS_DA_DEMONSTRACAO.map(([nome, municipio, abertura, porte]) => (
                  <tr key={nome}>
                    <th scope="row">{nome}</th>
                    <td>{municipio}</td>
                    <td>{abertura}</td>
                    <td>{porte}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="v2-conversa-notas">
            <div>
              <dt>Fonte</dt>
              <dd>Receita Federal, cadastro de CNPJ. A resposta de verdade traz a data do retrato usado.</dd>
            </div>
            <div>
              <dt>Como cheguei aqui</dt>
              <dd>
                <code>buscar_empresas</code> com CNAE 2222-6, UF SC, situação ativa e abertura antes de
                01/01/2011.
              </dd>
            </div>
            <div>
              <dt>O que a base não tem</dt>
              <dd>Faturamento de empresa fechada. O porte é o declarado à Receita.</dd>
            </div>
          </dl>
        </div>
        <p className="v2-fala v2-fala-pergunta">Qual o faturamento da primeira?</p>
        <div className="v2-fala v2-fala-resposta">
          <p>
            A base não tem faturamento de empresa fechada. Da primeira, dá para abrir a ficha: o cadastro e a
            conferência nas bases oficiais, cada uma com a fonte e a data.
          </p>
        </div>
      </div>
      <p className="v2-conversa-rodape">
        A conversa usa as mesmas ferramentas do conector e da CLI, só de leitura. Pessoa física não entra nesta
        conversa: o nome de sócio só sai para a organização com a permissão de ver pessoas, nunca o CPF. Confira
        a fonte antes de usar.
      </p>
      <p className="atalhos">
        {PERGUNTAR ? (
          <a className="botao primario" href={linkDoApp(PERGUNTAR.url)}>
            Entrar para perguntar
          </a>
        ) : (
          <>
            <a className="botao primario" href="#conector">
              Perguntar pelo conector
            </a>
            <a className="botao secundario" href={linkDoApp()}>
              Entrar no app
            </a>
          </>
        )}
      </p>
    </section>
  );
}

// --- como era na data: três instantes, três respostas (as datas do exemplo do TickerLab Data) ---------------
// (id, rótulo curto, nome, o que mudou, a resposta: documento, período, publicado em, vale até)
const INSTANTES: [string, string, string, string, Vigencia][] = [
  [
    "2024-03-31",
    "mar 2024",
    "março de 2024",
    "Antes da DFP 2024: o último anual público é o de 2023, e o de 2024 ainda não existe.",
    ["DFP", "2023-12-31", "2024-03-07", RESPOSTA_DO_EXEMPLO.publicado],
  ],
  [
    "2024-09-30",
    "set 2024",
    "setembro de 2024",
    "Durante o ano: o mais novo é o ITR do 2º trimestre; o anual de 2023 segue valendo.",
    ["ITR", "2024-06-30", "2024-08-08", "2024-11-07"],
  ],
  [
    "2025-04-30",
    "abr 2025",
    "abril de 2025",
    "Depois da DFP 2024: o valor anual do exercício de 2024 já está público.",
    ["DFP", RESPOSTA_DO_EXEMPLO.periodo, RESPOSTA_DO_EXEMPLO.publicado, null],
  ],
];

type Vigencia = [documento: string, periodo: string, publicado: string, valeAte: string | null];

function RespostaDoInstante({ dia, resposta, ordem }: { dia: string; resposta: Vigencia; ordem: number }) {
  const [documento, periodo, publicado, valeAte] = resposta;
  return (
    <pre className="janela-resposta guia-painel" data-instante={dia} data-ordem={ordem}>
      <code>
        <span className="c">{`# GET …/financials?known_at=${dia}`}</span>
        {"\n{\n  "}
        <span className="k">"document"</span>: <span className="s">"{documento}"</span>, <span className="k">"reference_period"</span>:{" "}
        <span className="s">"{periodo}"</span>
        {",\n  "}
        <span className="k">"revision"</span>: <span className="n">1</span>
        {",\n  "}
        <span className="k">"published_at"</span>: <span className="s">"{publicado}"</span>, <span className="k">"valid_until"</span>:{" "}
        {valeAte ? <span className="s">"{valeAte}"</span> : <span className="n">null</span>}
        {",\n  "}
        <span className="k">"value"</span>: <span className="n">&lt;valor da fonte&gt;</span>
        {"\n}"}
      </code>
    </pre>
  );
}

function ComoEraNaData() {
  return (
    <div className="escura como-era">
      <section className="faixa secao" id="como-era" aria-labelledby="titulo-como-era">
        <p className="olho">Como era na data</p>
        <h2 id="titulo-como-era">Peça o número como ele era naquela data</h2>
        <p className="subtitulo">
          Empresas reapresentam balanços. Aqui, a mesma pergunta com uma data devolve o que estava público naquele
          dia: documento, versão e valor vigentes. Na API é <code>known_at</code>, na CLI <code>--como-era</code>{" "}
          e no conector <code>como_era_em</code>.
        </p>
        <div className="demo-data guias" role="group" aria-labelledby="titulo-dos-instantes">
          {INSTANTES.map(([dia], i) => (
            <input
              key={dia}
              className="guia-escolha"
              data-ordem={i}
              type="radio"
              name="instante"
              id={`instante-${dia}`}
              defaultChecked={i === INSTANTES.length - 1}
            />
          ))}
          <div className="demo-data-texto">
            <p className="instantes-titulo" id="titulo-dos-instantes">
              Escolha a data
            </p>
            <div className="instantes">
              {INSTANTES.map(([dia, curto], i) => (
                <label key={dia} className="guia-rotulo" htmlFor={`instante-${dia}`} data-ordem={i}>
                  {curto}
                </label>
              ))}
            </div>
            {INSTANTES.map(([dia, , nome, explica], i) => (
              <p key={dia} className="data-escolhida guia-painel" data-instante={dia} data-ordem={i}>
                {nome}
                <small>{explica}</small>
              </p>
            ))}
            <ul className="fatos">
              <li>
                <b>published_at</b> é o dia da entrega à CVM. O valor vale a partir dele, inclusive.
              </li>
              <li>
                <b>valid_until</b> é o dia em que outra versão tomou o lugar. Vazio: vale até hoje.
              </li>
              <li>Cortar o futuro não muda o passado: o princípio tem teste automático na base.</li>
            </ul>
          </div>
          <div className="janela">
            {INSTANTES.map(([dia, , , , resposta], i) => (
              <RespostaDoInstante key={dia} dia={dia} resposta={resposta} ordem={i} />
            ))}
            <p className="janela-nota">
              <span>
                Mesma pergunta, três respostas: a base guarda cada versão com o dia em que ficou pública. Forma
                real; as datas e as versões do exemplo são ilustrativas.
              </span>
            </p>
          </div>
        </div>
      </section>
    </div>
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
          <span className="ticker">
            {`Tabelas e fontes em ${totais.tabelas_conferidas_em_curto} · companhias em ${medido_em_curto}`}
          </span>
        </header>
        <dl className="v2-base-numeros">
          <div>
            <dt>{`tabelas, cada uma com contrato (conferidas em ${totais.tabelas_conferidas_em_curto})`}</dt>
            <dd className="v2-numero">{milhares(totais.tabelas)}</dd>
            <dd>
              <ComoFoiCalculado>
                <p>
                  Contamos as tabelas do catálogo de contratos da base que já têm arquivo conferido
                  no acervo. Cada contrato diz a fonte, a licença, as datas e a frequência de
                  atualização; tabela nova só entra na conta depois de montada e conferida.
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

/** A base que as três portas consultam: os números medidos e a busca aberta, numa faixa só. */
function BasePorTras() {
  return (
    <div className="v2-base-fundo">
      <section className="faixa secao v2-base-faixa" aria-labelledby="titulo-base-por-tras">
        <div>
          <p className="olho">A base por trás</p>
          <h2 id="titulo-base-por-tras">Toda resposta sai de uma fonte pública, com a data</h2>
          <p className="subtitulo">
            O conector, a CLI e a API consultam a base que coletamos dos órgãos públicos. Experimente sem
            chave: busque uma companhia aberta e veja a fonte ao lado de cada número.
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

export function Inicio() {
  return (
    <>
      <Heroi />
      <TresPortas />
      <DemonstracaoDaConversa />
      <Travas />
      <ComoEraNaData />
      <BasePorTras />
      <LigadoPeloCnpj />
      <Cruzamentos />
      <Vitrine />
      <ChamadaFinal
        titulo="Comece pela chave"
        subtitulo={
          "Uma chave abre as três portas. O acesso está em beta fechado, sem cobrança; a documentação é " +
          "aberta e diz como pedir a chave da sua organização."
        }
      >
        <div className="acoes">
          <a className="botao primario" href={DOCUMENTACAO_DA_API} rel="noopener">
            Ler a documentação
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
