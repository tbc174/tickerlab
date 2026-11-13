// A página inicial do posicionamento v3 (ADR 0127, linha 774): a assinatura da CLI e do conector de M&A e análise de
// investimento, o terminal só com comandos que existem, o que dá para pedir, o agente e as travas, o que
// a base tem (números do catálogo e da medição, nunca digitados), o que ela liga pelo CNPJ, os
// cruzamentos, as quatro regras, as cinco vagas da vitrine e a chamada para pedir a chave.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { baseEmNumeros, catalogo, fatosDaBase, paginasDoApp, vitrine } from "../../src/conteudo";
import { renderizar } from "../../src/entry-server";
import { css } from "../../src/estilo";
import { DADOS } from "../../src/paginas/Inicio";
import { ASSINATURA, REGRAS_DA_BASE, URL_DA_API, linkDoApp } from "../../src/site/textos";

const html = renderizar("index.html");
const semTags = (texto: string) => texto.replace(/<[^>]+>/g, "");
// o texto como o React escreve no HTML
const esc = (texto: string) =>
  texto.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("'", "&#x27;");
/** O pedaço do HTML que começa em `inicio` e vai até o primeiro `fim` depois dele. */
function trecho(inicio: string, fim: string): string {
  const de = html.indexOf(inicio);
  expect(de, `não achei ${inicio}`).toBeGreaterThanOrEqual(0);
  return html.slice(de, html.indexOf(fim, de + inicio.length) + fim.length);
}
const principal = () => trecho("<main", "</main>");
const milhares = (n: number) => n.toLocaleString("pt-BR");

// frase que parece recomendação, previsão ou comparação por abrangência (plano, seção 7)
const PROIBIDAS = [
  /recomend/i,
  /vai subir/i,
  /oportunidade/i,
  /mais dados que/i,
  /maior base/i,
  /Bloomberg|FactSet|Refinitiv|Economatica|brapi|Status ?Invest/i,
];
// o aviso obrigatório é a única "recomendação" que pode aparecer
const AVISOS = /(Nada aqui|nada) é recomendação de investimento\.?/gi;
// a documentação da API diz como pedir a chave
const COMO_PEDIR_A_CHAVE = `${URL_DA_API}/documentacao/#comecar`;
const RAIZ = join(process.cwd(), "..");

describe("página inicial da CLI e do conector de M&A e análise de investimento", () => {
  it("o título é a assinatura, o subtítulo fala do agente e a coleta auditável continua à vista", () => {
    expect(semTags(trecho('<h1 id="titulo-heroi">', "</h1>"))).toBe(esc(ASSINATURA));
    expect(ASSINATURA).toMatch(/CLI e o conector de M&A e análise de investimento/);
    expect(semTags(principal())).toContain("o seu agente de IA roda a tickerlab");
    expect(principal()).toContain(
      "Coleta segura e auditável das fontes públicas brasileiras: cada número com data, fonte e " +
        "caminho até o original.",
    );
  });

  it("os botões do herói levam a como pedir a chave e aos comandos", () => {
    const heroi = trecho('<section class="heroi faixa"', "</section>");
    expect(heroi).toContain(`href="${COMO_PEDIR_A_CHAVE}" rel="noopener">Pedir uma chave</a>`);
    expect(heroi).toContain('href="#comandos">Ver os comandos</a>');
    expect(html).toContain('id="comandos"');
    // a seção da documentação que ensina a pedir a chave existe
    const documentacao = readFileSync(join(RAIZ, "site-api", "documentacao", "index.html"), "utf8");
    expect(documentacao).toContain('id="comecar"');
  });

  it("o terminal e os cartões só mostram comandos e opções que a CLI tem", () => {
    const cli = readFileSync(join(RAIZ, "cli", "tickerlab", "comandos.py"), "utf8");
    const terminal = trecho('<figure class="v2-painel v2-terminal"', "</figure>");
    const cartoes = trecho('<section class="faixa secao v2-comandos"', "</section>");
    const linhas = [...semTags(terminal).matchAll(/tickerlab [^\n#]+/g)].map((m) => m[0]);
    expect(linhas.length).toBeGreaterThanOrEqual(4);
    const citados = [...linhas, ...[...cartoes.matchAll(/<code>([^<]+)<\/code>/g)].map((m) => m[1])];
    expect(citados.length).toBeGreaterThanOrEqual(10);
    for (const citado of citados) {
      const comando = citado.match(/^tickerlab ([a-z]+)/)?.[1];
      if (comando) expect(cli, citado).toMatch(new RegExp(`^def ${comando}\\(`, "m"));
      for (const opcao of citado.match(/--[a-z-]+/g) ?? []) expect(cli, citado).toContain(`"${opcao}"`);
    }
    // nenhuma saída inventada: o terminal não traz CNPJ de empresa nem valor em reais
    expect(semTags(terminal)).not.toMatch(/R\$|\d{2}\.\d{3}\.\d{3}/);
  });

  it("o agente: os três passos, as instruções e as travas, com a de pessoa física", () => {
    const secao = trecho('<section class="faixa secao v2-agente"', "</section>");
    const texto = semTags(secao);
    expect(secao.split("<li>").length - 1).toBe(3);
    expect(secao).toContain("<code>tickerlab instrucoes</code>");
    expect(secao).toContain("<code>tickerlab login</code>");
    expect(texto).toContain("beta fechado, sem cobrança");
    for (const trava of [
      "Fonte e data em cada número",
      "Nenhum número inventado",
      "Nada é recomendação de investimento",
      "Sem dado de pessoa física",
      "A chave é segredo",
    ])
      expect(texto, trava).toContain(trava);
  });

  it("o conector MCP tem o mesmo peso da CLI: no herói, num botão e numa seção própria", () => {
    // Tiago, 13/11/2026 (linha 901): o MCP é produto principal junto com a CLI
    const heroi = trecho('<section class="heroi faixa"', "</section>");
    expect(semTags(heroi)).toContain("ou o Claude consulta o conector");
    expect(heroi).toContain('href="#conector">Usar no Claude</a>');
    expect(DADOS.descricao).toMatch(/CLI e conector MCP/);
    const secao = trecho('<section class="faixa secao v2-comandos v2-conector"', "</section>");
    const texto = semTags(secao);
    expect(secao).toContain('id="conector"');
    expect(texto).toContain("No Claude e no ChatGPT");
    expect(secao.split("<li>").length - 1).toBe(3);
    for (const trava of ["Só leitura", "As mesmas regras da CLI", "Sem dado de pessoa física", "A chave não vai ao chat"])
      expect(texto, trava).toContain(trava);
    // o endereço do conector vem com a chave: nenhuma parte da página o publica
    expect(html).not.toMatch(/mcp\.tickerlab|https?:\/\/[^\s"]*\/mcp/);
  });

  it("os cartões do conector só citam ferramentas e prompts que o conector registra", () => {
    const ferramentas = readFileSync(join(RAIZ, "conector_remoto", "ferramentas.py"), "utf8");
    const prompts = readFileSync(join(RAIZ, "conector_remoto", "prompts.py"), "utf8");
    const secao = trecho('<section class="faixa secao v2-comandos v2-conector"', "</section>");
    const citados = [...secao.matchAll(/<code>([^<]+)<\/code>/g)].flatMap((m) => m[1].split(" · "));
    expect(citados.length).toBeGreaterThanOrEqual(10);
    for (const nome of citados) {
      if (nome === "prompts do conector") expect(prompts).toContain("def registrar_prompts(");
      else expect(ferramentas, nome).toMatch(new RegExp(`async def ${nome}\\(`));
    }
  });

  it("a demonstração da conversa vem depois do conector, dita gravada, com fonte e sem pessoa nem promessa", () => {
    // linha 903, PR E: texto fixo, nenhuma chamada a modelo no site público
    const secao = trecho('<section class="faixa secao v2-demonstracao"', "</section>");
    const texto = semTags(secao);
    expect(html.indexOf('id="conector"')).toBeLessThan(html.indexOf('id="demonstracao"'));
    expect(html.indexOf('id="demonstracao"')).toBeLessThan(html.indexOf('id="titulo-da-base"'));
    for (const dito of ["Demonstração", "conversa gravada", "inventadas", "nenhuma IA roda nesta página"])
      expect(texto, dito).toContain(dito);
    for (const parte of ["Fonte", "Como cheguei aqui", "O que a base não tem", "Receita Federal"])
      expect(texto, parte).toContain(parte);
    // toda empresa da tabela é dita de exemplo
    const empresas = [...secao.matchAll(/<th scope="row">([^<]+)<\/th>/g)].map((m) => m[1]);
    expect(empresas.length).toBeGreaterThanOrEqual(3);
    for (const nome of empresas) expect(nome).toMatch(/^Exemplo /);
    expect(secao).not.toMatch(/\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}/); // nem CNPJ nem CPF
    expect(texto).not.toMatch(/R\$|recomend|oportunidade|mais dados que|rentabilidade|retorno/i);
    expect(secao).not.toMatch(/<script|<form|<input|fetch\(/);
  });

  it("a demonstração só cita ferramenta e filtro que o conector registra", () => {
    const ferramentas = readFileSync(join(RAIZ, "conector_remoto", "ferramentas.py"), "utf8");
    const secao = trecho('<section class="faixa secao v2-demonstracao"', "</section>");
    const citadas = [...secao.matchAll(/<code>([^<]+)<\/code>/g)].map((m) => m[1]);
    expect(citadas).toEqual(["buscar_empresas"]);
    expect(ferramentas).toMatch(/async def buscar_empresas\(/);
    for (const filtro of ["cnae:", "uf:", "situacao_cadastral:", "aberta_antes_de:"]) expect(ferramentas, filtro).toContain(filtro);
  });

  it("o botão da demonstração: Entrar para perguntar só quando a tela Perguntar existe", () => {
    const secao = trecho('<section class="faixa secao v2-demonstracao"', "</section>");
    const perguntar = paginasDoApp.find((p) => p.chave === "perguntar");
    if (perguntar) {
      expect(secao).toContain(`href="${linkDoApp(perguntar.url)}">Entrar para perguntar</a>`);
    } else {
      expect(secao).not.toContain("Entrar para perguntar");
      expect(secao).toContain('href="#conector">Perguntar pelo conector</a>');
      expect(secao).toContain(`href="${linkDoApp()}">Entrar no app</a>`);
    }
  });

  it("a descrição da página fala com quem analisa e cabe no Google", () => {
    expect(DADOS.descricao.length).toBeLessThanOrEqual(160);
    expect(DADOS.descricao).toMatch(/fonte/);
    expect(html).toContain(`<meta name="description" content="${esc(DADOS.descricao)}"`);
  });

  it("o que a base tem: tabelas, ligadas pelo CNPJ, fontes e companhias vindos do catálogo e da medição", () => {
    const painel = trecho('<article class="v2-painel v2-painel-base"', "</article>");
    const texto = semTags(painel);
    expect(texto).toContain("O que a base tem");
    for (const numero of [
      catalogo.totais.tabelas,
      catalogo.ligado_pelo_cnpj.tabelas,
      catalogo.totais.fontes,
      baseEmNumeros.numeros.empresas,
    ])
      expect(painel).toContain(`<dd class="v2-numero">${milhares(numero)}</dd>`);
    for (const rotulo of ["tabelas", "ligadas pelo CNPJ", "fontes públicas", "companhias abertas"])
      expect(texto).toContain(rotulo);
    expect(texto).toContain(`Medido em ${baseEmNumeros.medido_em_curto}`);
    // cada número com a conta recolhida, que abre sem JavaScript
    expect(painel.match(/<details class="como-foi-calculado">/g)).toHaveLength(4);
    expect(painel).not.toMatch(/<details[^>]*\sopen/);
  });

  it("o painel da base também aparece no celular", () => {
    expect(css()).not.toContain(".v2-painel-pilha { display: none; }");
  });

  it("o estudo do dia, as novidades e a lista de fontes saíram da inicial (ficam nas páginas delas)", () => {
    for (const peca of ["v2-estudo", "v2-pilula", "v2-ultimas", "v2-fontes-da-base", "v2-no-app"])
      expect(html, peca).not.toContain(peca);
    expect(semTags(principal())).not.toContain("Estudo do dia");
    expect(css()).not.toContain(".v2-estudo");
    expect(renderizar("relatorios.html")).toContain("Estudo do dia");
  });

  it("as cinco vagas: as prontas em cima com link, as em breve embaixo, sem link", () => {
    const secao = trecho('<section class="faixa secao v2-vitrine"', "</section>");
    const cartoes = secao.split('<article class="cartao v2-vaga').slice(1);
    expect(cartoes).toHaveLength(vitrine.length);
    expect(vitrine.map((v) => v.chave)).toEqual(["setor", "ficha", "cnpj", "ma", "cruzamentos"]);
    const naTela = [
      ...vitrine.filter((v) => v.estado === "pronta"),
      ...vitrine.filter((v) => v.estado !== "pronta"),
    ];
    naTela.forEach((vaga, i) => {
      const cartao = cartoes[i];
      expect(semTags(cartao), vaga.chave).toContain(esc(vaga.titulo));
      expect(semTags(cartao), vaga.chave).toContain(esc(vaga.para_que_serve));
      if (vaga.estado === "pronta") {
        expect(cartao, vaga.chave).toContain(`href="${vaga.link}"`);
      } else {
        expect(cartao, vaga.chave).toContain('<span class="selo breve">Em breve</span>');
        expect(cartao, vaga.chave).not.toContain("href=");
      }
    });
  });

  it("ligado pelo CNPJ: o total e um cartão por tema, com os órgãos e a contagem do catálogo", () => {
    const secao = trecho('<section class="faixa secao v2-ligado-pelo-cnpj" id="ligado-pelo-cnpj"', "</section>");
    const { tabelas, orgaos, temas } = catalogo.ligado_pelo_cnpj;
    expect(semTags(secao)).toContain(`${tabelas} das ${catalogo.totais.tabelas} tabelas se ligam pelo CNPJ`);
    expect(semTags(secao)).toContain(`o que ${orgaos} órgãos públicos publicam`);
    const cartoes = secao.split('<article class="cartao v2-tema-cnpj"').slice(1);
    expect(cartoes).toHaveLength(temas.length);
    temas.forEach((tema, i) => {
      const texto = semTags(cartoes[i]);
      expect(texto, tema.chave).toContain(esc(tema.titulo));
      expect(texto, tema.chave).toContain(esc(tema.texto));
      for (const orgao of tema.orgaos) expect(cartoes[i], tema.chave).toContain(`<li>${esc(orgao)}</li>`);
      expect(texto, tema.chave).toContain(`${tema.tabelas} tabelas`);
    });
    expect(semTags(secao)).toContain("nome de pessoa física não aparece");
    expect(secao).toContain('href="/dados.html#');
    // a ordem da página: a CLI, a base, o que ela liga, os cruzamentos e, por último, a vitrine
    const ordem = [
      "v2-comandos",
      "v2-agente",
      "v2-base-faixa",
      "v2-ligado-pelo-cnpj",
      "v2-cruzamentos",
      "v2-regras",
      "v2-vitrine",
      "v2-janelas",
    ];
    const lugares = ordem.map((classe) => html.indexOf(`class="faixa secao ${classe}"`));
    lugares[lugares.length - 1] = html.indexOf('class="faixa v2-janelas"');
    expect(lugares.every((lugar) => lugar > 0)).toBe(true);
    expect([...lugares].sort((a, b) => a - b)).toEqual(lugares);
  });

  it("os cruzamentos: cada fato com o número, a fonte e a conta recolhida, sem nome de empresa", () => {
    const secao = trecho('<section class="faixa secao v2-cruzamentos" id="cruzamentos"', "</section>");
    expect(semTags(secao)).toContain(`medidas em ${fatosDaBase.medido_em_curto}`);
    const cartoes = secao.split('<article class="cartao v2-fato"').slice(1);
    expect(fatosDaBase.fatos.map((f) => f.chave)).toEqual([
      "lucros",
      "auditor",
      "atraso",
      "remuneracao",
      "dividendo",
      "parecer",
    ]);
    expect(cartoes).toHaveLength(fatosDaBase.fatos.length);
    fatosDaBase.fatos.forEach((fato, i) => {
      const texto = semTags(cartoes[i]);
      expect(texto, fato.chave).toContain(fato.numero);
      expect(texto, fato.chave).toContain(esc(fato.texto));
      expect(texto, fato.chave).toContain(`Fonte: ${esc(fato.fonte)}`);
      expect(cartoes[i], fato.chave).toContain("<summary>Como foi calculado</summary>");
      expect(texto, fato.chave).toContain(esc(fato.como_foi_calculado));
    });
    // a vaga "cruzamentos" da vitrine leva até aqui
    expect(vitrine.find((v) => v.chave === "cruzamentos")?.link).toBe("/#cruzamentos");
  });

  it("as quatro regras da base, cada uma recolhida", () => {
    const secao = trecho('<section class="faixa secao v2-regras"', "</section>");
    expect(semTags(secao)).toContain("Por que confiar num número daqui");
    for (const [titulo, texto] of REGRAS_DA_BASE) {
      expect(secao, titulo).toContain(`<summary>${esc(titulo)}</summary>`);
      expect(semTags(secao), titulo).toContain(texto);
    }
  });

  it("sem terminal: a mesma base pelo app, pela API e pelos relatórios", () => {
    const secao = trecho('<section class="faixa v2-janelas"', "</section>");
    expect(secao).toContain('href="https://app.tickerlab.com.br/"');
    expect(secao).toContain(`href="${URL_DA_API}"`);
    expect(secao).toContain('href="/relatorios.html"');
  });

  it("a chamada final leva a pedir a chave e diz que o beta é fechado e sem cobrança", () => {
    const final = trecho('<section class="faixa secao final"', "</section>");
    expect(final).toContain(`href="${COMO_PEDIR_A_CHAVE}"`);
    expect(final).toContain(">Abrir o app</a>");
    expect(semTags(final)).toContain("beta fechado, sem cobrança");
  });

  it("sem fita de cotações, sem busca de ativos e sem o painel de PETR4", () => {
    for (const peca of ["v2-fita", "data-busca=", "v2-grafico", "exemplo-PETR4", "Por que o TickerLab"])
      expect(html, peca).not.toContain(peca);
  });

  it("diz que nada é recomendação e não usa frase proibida", () => {
    const texto = semTags(principal());
    expect(texto).toContain("Nada aqui é recomendação de investimento");
    const semAviso = texto.replace(AVISOS, "");
    for (const proibida of PROIBIDAS) expect(proibida.test(semAviso), String(proibida)).toBe(false);
  });
});
