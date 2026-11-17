// Página inicial de um site só (linha 966 da fila, 16/11/2026): tickerlab.com.br passa a ser o único site
// de produto, com o visual do TickerLab Data (escolha do Tiago). Uma proposta, a base com fonte e data, e três
// portas nesta ordem: o conector MCP (o principal desde 16/11), a CLI e a API. O topo tem uma frase, a janela
// de código com a resposta da API (o mesmo pedido pelas três portas) e um único botão de chave. Depois: as
// três portas, a demonstração da conversa, as travas (uma lista só para as três), "como era na data", o que a
// base tem (números do catálogo e da medição, nunca digitados), o que ela liga pelo CNPJ, os cruzamentos e as
// análises abertas. As quatro regras ficam em Dados e em Metodologia; a API documentada, na raiz da própria API.
import type { ReactNode } from "react";
import { BuscaDaBase } from "../site/BuscaDaBase";
import { baseEmNumeros, catalogo, paginasDoApp } from "../conteudo";
import { ComoFoiCalculado } from "../site/ComoFoiCalculado";
import { Cruzamentos } from "../site/Cruzamentos";
import { AvisoDeAcesso, ChamadaFinal } from "../site/comum";
import { Fundo } from "../site/Fundo";
import { LigadoPeloCnpj } from "../site/LigadoPeloCnpj";
import { URL_DA_API, linkDoApp } from "../site/textos";
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
// A empresa é a Petrobras (CNPJ de companhia aberta, público). O valor fica como marcador e as datas são as do
// exemplo do TickerLab Data: a forma é a real, o número não é inventado.
const CNPJ_DO_EXEMPLO = "33000167000101";
const DIA_DO_EXEMPLO = "2024-09-30";

type Trecho = [classe: "" | "k" | "s" | "n" | "c" | "eu", texto: string];
const PEDIDOS: { porta: string; nome: string; linhas: Trecho[][] }[] = [
  {
    porta: "conector",
    nome: "Conector",
    linhas: [
      [["c", "# no Claude, com o conector do TickerLab"]],
      [["eu", "As contas da Petrobras como estavam públicas em 30/09/2024."]],
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
        <span className="k">"published_at"</span>: <span className="s">"2024-03-07"</span>
        {" },\n    "}
        <span className="k">"description"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="s">"Receita de Venda de Bens e/ou Serviços"</span>
        {", … },\n    "}
        <span className="k">"document"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="s">"DFP"</span>
        {", … },\n    "}
        <span className="k">"reference_period"</span>: {"{ "}
        <span className="k">"value"</span>: <span className="s">"2023-12-31"</span>
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
        <span>Exemplo de forma: o valor aparece como marcador e as datas são ilustrativas.</span>
      </p>
    </div>
  );
}

const PROVAS_DO_TOPO = ["Fonte e data em cada número", "Como era na data em toda consulta", "Sem dado de pessoa física"];

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

// --- as três portas ------------------------------------------------------------------------------------------
// (porta, nome, selo, para quem, a linha de exemplo, o link para a seção dela)
const PORTAS: [string, string, string, string, string, string][] = [
  [
    "conector",
    "Conector MCP",
    "Principal",
    "No Claude e no ChatGPT, sem instalar nada: você pergunta em português e a IA consulta a base.",
    "ficha_da_empresa · buscar_empresas",
    "Como ligar",
  ],
  [
    "comandos",
    "CLI",
    "Terminal",
    "No terminal ou pelo seu agente de IA: um comando por pergunta, em JSON ou direto para o Excel.",
    "tickerlab empresa <cnpj>",
    "Os comandos",
  ],
  [
    "api",
    "API",
    "TickerLab Data",
    "No seu sistema: JSON, a chave no cabeçalho e lotes de CNPJs num pedido só.",
    "GET /data/v1/companies/{cnpj}",
    "As rotas",
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
        {PORTAS.map(([ancora, nome, selo, texto, exemplo, link], i) => (
          <article key={ancora} className={`porta${i === 0 ? " principal" : ""}`}>
            <p className="porta-topo">
              <span className="porta-numero">{String(i + 1).padStart(2, "0")}</span>
              <span className="porta-selo">{selo}</span>
            </p>
            <h3>{nome}</h3>
            <p>{texto}</p>
            <code className="porta-exemplo">{exemplo}</code>
            <a className="seta" href={`#${ancora}`}>
              {link}
            </a>
          </article>
        ))}
      </div>
    </section>
  );
}

// O conector MCP (conector_remoto/, docs/guia-do-analista-conector.md): as perguntas e as ferramentas que
// as respondem. Só nomes de ferramenta que existem; o teste do conector confere contra o registro.
const PERGUNTAS_DO_CONECTOR: [string, string, string][] = [
  [
    "Triagem antes da reunião",
    "ficha_da_empresa · eventos · vinculos",
    "O cadastro, o que aconteceu com a empresa e as participações que a base tiver, cada ponto com a fonte e a data.",
  ],
  [
    "Alvos num setor e numa UF",
    "buscar_empresas",
    "Empresas pela atividade, UF, porte e idade, página por página. Só a empresa: sem sócio, contato nem endereço.",
  ],
  [
    "Quem já se mexeu no setor",
    "compradores_do_setor",
    "Empresas, FIPs e companhias abertas que entraram no setor como sócias: movimento passado, não intenção de compra.",
  ],
  [
    "Comparáveis e demonstrações",
    "comparaveis · demonstracoes",
    "Os pares da companhia aberta na CVM, com a mediana, e as demonstrações como estavam públicas na data pedida.",
  ],
  [
    "Setor e fundo",
    "setores · setor · fundo",
    "As séries de mercado do setor, a concentração e a fatia de cada empresa, e o cadastro, as taxas e a carteira de um fundo.",
  ],
  [
    "Fluxos prontos",
    "prompts do conector",
    "Triagem, alvos, compradores, comparáveis e dossiê: você escolhe o fluxo no Claude e preenche o CNPJ ou o setor.",
  ],
];

const PASSOS_DO_CONECTOR: [string, ReactNode][] = [
  [
    "Peça a chave",
    <>
      Cada pessoa tem a sua, entregue por quem administra o TickerLab na organização. O acesso está em
      beta fechado, sem cobrança:{" "}
      <a href={COMO_PEDIR_A_CHAVE} rel="noopener">
        como pedir
      </a>
      .
    </>,
  ],
  [
    "Adicione o conector",
    <>
      No Claude, em Configurações, um conector personalizado com o endereço que quem administra passa junto com a chave. No
      ChatGPT, o mesmo conector, em Apps e conectores.
    </>,
  ],
  [
    "Ligue com a sua chave",
    <>
      Abre uma página do TickerLab; você cola a chave ali, não no chat. O assistente recebe um acesso
      que vence sozinho e para quando a chave é revogada.
    </>,
  ],
];

/** Uma porta em detalhe: o que dá para pedir (cartões com o nome real) e os três passos para começar. */
function DetalheDaPorta({
  id,
  classe,
  olho,
  titulo,
  subtitulo,
  cartoes,
  passos,
  children,
}: {
  id: string;
  classe: string;
  olho: string;
  titulo: string;
  subtitulo: ReactNode;
  cartoes: [string, string, string][];
  passos: [string, ReactNode][];
  children?: ReactNode;
}) {
  return (
    <section className={`faixa secao v2-comandos ${classe}`} id={id} aria-labelledby={`titulo-${id}`}>
      <p className="olho">{olho}</p>
      <h2 id={`titulo-${id}`}>{titulo}</h2>
      <p className="subtitulo">{subtitulo}</p>
      <div className="grade tres">
        {cartoes.map(([nome, codigo, texto]) => (
          <article key={nome} className="cartao v2-comando">
            <h3>{nome}</h3>
            <p className="v2-comando-linha">
              <code>{codigo}</code>
            </p>
            <p>{texto}</p>
          </article>
        ))}
      </div>
      <ol className="v2-passos-da-cli passos-em-linha">
        {passos.map(([nome, texto]) => (
          <li key={nome}>
            <strong>{nome}</strong>
            <span>{texto}</span>
          </li>
        ))}
      </ol>
      {children}
    </section>
  );
}

function Conector() {
  return (
    <DetalheDaPorta
      id="conector"
      classe="v2-conector"
      olho="Porta 1 · Conector MCP"
      titulo="No Claude e no ChatGPT, sem terminal"
      subtitulo={
        "O MCP é o padrão aberto que liga uma IA a uma fonte de dados. Com o conector, você pergunta em " +
        "português, na conversa, e a IA consulta a base, sem instalar nada."
      }
      cartoes={PERGUNTAS_DO_CONECTOR}
      passos={PASSOS_DO_CONECTOR}
    />
  );
}

// A CLI (docs/cli.md e as instruções do agente em cli/tickerlab/instrucoes/AGENTS.md): um cartão por comando.
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

const PASSOS_DA_CLI: [string, ReactNode][] = [
  [
    "Peça a chave",
    <>
      É a mesma chave do conector: uma por pessoa, criada pela organização. O acesso está em beta fechado, sem cobrança:{" "}
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
      <code>tickerlab instrucoes</code> imprime o texto que ensina os comandos e as travas ao
      Claude Code, ao Codex e a outros agentes; guarde-o no arquivo de instruções do seu agente.
    </>,
  ],
];

function Cli() {
  return (
    <DetalheDaPorta
      id="comandos"
      classe="v2-cli"
      olho="Porta 2 · CLI"
      titulo="Do CNPJ à planilha, um comando por pergunta"
      subtitulo={
        "A mesma resposta para você, no terminal, e para o seu agente de IA, em JSON. O pacote leva as " +
        "instruções do agente: os comandos e o que ele não pode fazer."
      }
      cartoes={COMANDOS}
      passos={PASSOS_DA_CLI}
    />
  );
}

// A API (site-api/documentacao): quatro rotas de exemplo; a lista inteira fica na raiz da própria API. O teste
// confere que cada rota citada está na documentação.
const ROTAS: [string, string, string, string[]][] = [
  [
    "GET /data/v1/companies/{cnpj}/financials",
    "Demonstrações como eram na data",
    "DFP e ITR da CVM, conta a conta, com o documento, a versão e o dia em que ficaram públicas.",
    ["ODbL · CVM", "known_at"],
  ],
  [
    "GET /data/v1/companies/{cnpj}/profile",
    "Perfil da empresa",
    "O cadastro na Receita e, da companhia aberta, cada DFP e ITR devida à CVM, com o prazo e o dia da entrega.",
    ["ODbL · CVM", "CC BY · Receita", "known_at"],
  ],
  [
    "GET /data/v1/buyers",
    "Compradores do setor",
    "Quem entrou como sócio de empresas do setor: movimento passado, não intenção de compra. Só pessoa jurídica.",
    ["ODbL · CVM", "CC BY · Receita", "known_at"],
  ],
  [
    "POST /data/v1/companies/batch",
    "Lotes de até 100 CNPJs",
    "A situação cadastral de até 100 CNPJs num pedido só. Fundos e crédito também têm rota de lote.",
    ["CC BY · Receita", "known_at"],
  ],
];

function Api() {
  return (
    <section className="faixa secao v2-api" id="api" aria-labelledby="titulo-api">
      <p className="olho">Porta 3 · API</p>
      <h2 id="titulo-api">TickerLab Data, a API: para o seu sistema</h2>
      <p className="subtitulo">
        JSON, a chave no cabeçalho e a licença da fonte em cada resposta. Uma rota por pergunta; as de consulta aceitam{" "}
        <code>known_at</code>, para pedir a base como era na data.
      </p>
      <div className="rotas">
        {ROTAS.map(([rota, titulo, texto, selos]) => {
          const [metodo, caminho] = rota.split(" ");
          return (
            <article key={rota} className="rota">
              <span className="metodo">
                <b>{metodo}</b> {caminho}
              </span>
              <h3>{titulo}</h3>
              <p>{texto}</p>
              <p className="fontes">
                {selos.map((selo) => (
                  <span key={selo} className={selo.startsWith("ODbL") ? "odbl" : undefined}>
                    {selo}
                  </span>
                ))}
              </p>
            </article>
          );
        })}
      </div>
      <p className="atalhos">
        <a className="botao secundario" href={DOCUMENTACAO_DA_API} rel="noopener">
          A documentação da API
        </a>
        <a className="botao secundario" href={ROTAS_DA_API} rel="noopener">
          Todas as rotas
        </a>
      </p>
    </section>
  );
}

// As travas das três portas, numa lista só (antes cada porta repetia as suas): as instruções da CLI
// (cli/tickerlab/instrucoes/AGENTS.md), as do conector e a API, que não serve pessoa física.
const TRAVAS: [string, string][] = [
  ["Fonte e data em cada número", "As instruções da CLI e do conector pedem à IA que cite de onde veio e quando ficou público, e liste à parte o que faltou."],
  ["Nenhum número inventado", "As instruções pedem que a IA diga o que a base não devolveu, em vez de completar."],
  ["Sem dado de pessoa física", "A API não serve sócio pessoa física, CPF, MEI nem empresário individual, e o conector confere cada resposta e recusa a que trouxer campo de pessoa."],
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
        A conversa usa as mesmas ferramentas do conector e da CLI, só de leitura. Pessoa física não entra na
        resposta. Confira a fonte antes de usar.
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
    ["DFP", "2023-12-31", "2024-03-07", "2025-02-27"],
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
    ["DFP", "2024-12-31", "2025-02-27", null],
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
          <span className="ticker">Medido em {medido_em_curto}</span>
        </header>
        <dl className="v2-base-numeros">
          <div>
            <dt>tabelas, cada uma com contrato</dt>
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
      <Conector />
      <DemonstracaoDaConversa />
      <Cli />
      <Api />
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
