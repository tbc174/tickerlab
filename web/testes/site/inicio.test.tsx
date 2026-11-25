// A página inicial de um site só (linha 966, 16/11/2026): uma frase no topo, a janela de código com a resposta
// da API e um único botão de chave; as três portas (conector MCP, CLI e API), cada uma só com nomes que existem;
// as travas numa lista só; "como era na data"; o que a base tem (números do catálogo e da medição, nunca
// digitados), o que ela liga pelo CNPJ, os cruzamentos, as vagas da vitrine e a chamada para pedir a chave.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { baseEmNumeros, catalogo, consultasDasPortas, fatosDaBase, paginasDoApp, vitrine } from "../../src/conteudo";
import { renderizar } from "../../src/entry-server";
import { css } from "../../src/estilo";
import { COMO_PEDIR_A_CHAVE, DADOS, FRASE_DO_TOPO, RESPOSTA_DO_EXEMPLO } from "../../src/paginas/Inicio";
import { REGRAS_DA_BASE, URL_DA_API, URL_DO_CODIGO, linkDoApp } from "../../src/site/textos";

const html = renderizar("index.html");
const semTags = (texto: string) => texto.replace(/<[^>]+>/g, "");
// o texto como o React escreve no HTML
const esc = (texto: string) =>
  texto.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("'", "&#x27;");
// o HTML de volta a texto (as aspas e os sinais que o React escapa)
const desesc = (texto: string) =>
  texto
    .replaceAll("&quot;", '"')
    .replaceAll("&#x27;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
/** O pedaço do HTML que começa em `inicio` e vai até o primeiro `fim` depois dele. */
function trecho(inicio: string, fim: string): string {
  const de = html.indexOf(inicio);
  expect(de, `não achei ${inicio}`).toBeGreaterThanOrEqual(0);
  return html.slice(de, html.indexOf(fim, de + inicio.length) + fim.length);
}
const principal = () => trecho("<main", "</main>");
const heroi = () => trecho('<section class="heroi faixa heroi-janela"', "</section>");
const milhares = (n: number) => n.toLocaleString("pt-BR");
const vezes = (texto: string, pedaco: string) => texto.split(pedaco).length - 1;

// frase que parece recomendação, previsão, preço ou comparação por abrangência (plano, seção 7, e linha 966)
const PROIBIDAS = [
  /recomend/i,
  /vai subir/i,
  /oportunidade/i,
  /mais dados que/i,
  /maior base/i,
  // preço (a conta de um cruzamento pode citar um valor em reais; preço da chave, nunca)
  /R\$ ?0\b|preço(?!s de remédios)|por mês|\/mês/i,
  /grátis|gratuito/i,
  /faixa estimada|faturamento estimado/i,
  /Bloomberg|FactSet|Refinitiv|Economatica|brapi|Status ?Invest/i,
];
// o aviso obrigatório é a única "recomendação" que pode aparecer
const AVISOS = /(Nada aqui|nada) é recomendação de investimento\.?/gi;
const RAIZ = join(process.cwd(), "..");
const ler = (...partes: string[]) => readFileSync(join(RAIZ, ...partes), "utf8");
const CLI = ler("cli", "tickerlab", "comandos.py");
const FERRAMENTAS = ler("conector_remoto", "ferramentas.py");
const DOCUMENTACAO = ler("site-api", "documentacao", "index.html");
// as ferramentas do analista (crédito, o que mudou, comparar, de onde vem) e as da onda 2 (acompanhar, registros, compras) ficam noutros
// arquivos do conector
const TODAS_AS_FERRAMENTAS =
  FERRAMENTAS + ler("conector_remoto", "ferramentas_do_analista.py") + ler("conector_remoto", "acompanhar.py") + ler("conector_remoto", "registros.py") + ler("conector_remoto", "compras.py");
// rotas que existem na API (o teste da lista única confere no roteador) mas a página de documentação ainda não lista:
// linha 1026 da fila; quando a documentação as listar, este teste falha e a rota sai daqui
const ROTAS_AINDA_SEM_DOCUMENTACAO = [
  "GET /companies/{cnpj}/analysis",
  "GET /research/news",
  "GET /companies/{cnpj}/registrations",
  "GET /companies/{cnpj}/public-procurement",
];

/** Confere um comando citado (`tickerlab x --opcao …`): o comando e cada opção existem na CLI. */
function comandoExiste(citado: string) {
  // o comando de duas palavras (`de-onde-vem`) é a função com `_` (o click troca `_` por `-` no nome)
  const comando = citado.match(/^\$? ?tickerlab ([a-z]+(?:-[a-z]+)*)/)?.[1];
  if (comando) expect(CLI, citado).toMatch(new RegExp(`^def ${comando.replaceAll("-", "_")}\\(`, "m"));
  for (const opcao of citado.match(/--[a-z-]+/g) ?? []) expect(CLI, citado).toContain(`"${opcao}"`);
}
/** Confere uma rota citada (`GET /data/v1/…`): está na tabela de rotas da documentação da API, salvo as que a
 * documentação ainda não lista (e então confere que de fato não lista, para a exceção sair quando ela listar). */
function rotaDocumentada(rota: string) {
  const [metodo, caminho] = rota.split(" ");
  const curta = `${metodo} ${caminho.replace("/data/v1", "")}`;
  if (ROTAS_AINDA_SEM_DOCUMENTACAO.includes(curta)) expect(DOCUMENTACAO, rota).not.toContain(`<code>${curta}</code>`);
  else expect(DOCUMENTACAO, rota).toContain(`<code>${curta}</code>`);
}

describe("página inicial de um site só: uma proposta e três portas", () => {
  it("o título é a frase do topo, com 'da fonte' em destaque", () => {
    const titulo = trecho('<h1 id="titulo-heroi">', "</h1>");
    expect(semTags(titulo)).toBe(FRASE_DO_TOPO);
    expect(titulo).toContain('<span class="v2-degrade">da fonte</span>');
    expect(vezes(html, "<h1")).toBe(1);
  });

  it("o topo tem um único botão de chave, que leva à documentação, e outro para as três portas", () => {
    expect(vezes(heroi(), `href="${COMO_PEDIR_A_CHAVE}"`)).toBe(1);
    expect(heroi()).toContain(`href="${COMO_PEDIR_A_CHAVE}" rel="noopener">Pedir uma chave</a>`);
    expect(heroi()).toContain('href="#portas">Ver as três portas</a>');
    expect(COMO_PEDIR_A_CHAVE).toBe(`${URL_DA_API}/documentacao/#comecar`);
    expect(DOCUMENTACAO).toContain('id="comecar"');
    // o beta é dito no topo, sem preço
    expect(semTags(heroi())).toContain("Beta fechado · sem cobrança");
  });

  it("a janela do topo: o mesmo pedido pelas três portas, na ordem, e o conector aberto de início", () => {
    const janela = trecho('<div class="janela guias"', '<p class="janela-nota">');
    const rotulos = [...janela.matchAll(/<label class="guia-rotulo"[^>]*>([^<]+)<\/label>/g)].map((m) => m[1]);
    expect(rotulos).toEqual(["Conector", "CLI", "API"]);
    const marcados = [...janela.matchAll(/<input[^>]*name="janela-porta"[^>]*>/g)].map((m) => m[0]);
    expect(marcados).toHaveLength(3);
    expect(marcados.map((m) => m.includes("checked"))).toEqual([true, false, false]);
    const pedidos = [...janela.matchAll(/<pre class="janela-pedido guia-painel" data-porta="([a-z]+)"[^>]*>([\s\S]*?)<\/pre>/g)];
    expect(pedidos.map((m) => m[1])).toEqual(["conector", "cli", "api"]);
    const [conector, cli, api] = pedidos.map((m) => desesc(semTags(m[2])));
    // a pergunta de quem escreve e a chamada da ferramenta falam do mesmo dia (senão a resposta olharia o futuro)
    const diaDaChamada = conector.match(/como_era_em="(\d{4})-(\d{2})-(\d{2})"/);
    const diaDaFrase = conector.match(/públicas em (\d{2})\/(\d{2})\/(\d{4})\./);
    expect(diaDaChamada && diaDaFrase).toBeTruthy();
    expect([diaDaFrase?.[3], diaDaFrase?.[2], diaDaFrase?.[1]]).toEqual(diaDaChamada?.slice(1));
    // as três portas pedem o mesmo dia
    for (const pedido of [cli, api]) expect(pedido).toContain(diaDaChamada?.slice(1).join("-"));
    // o conector chama uma ferramenta que existe, com o parâmetro de data que ela aceita
    const ferramenta = conector.match(/^([a-z_]+)\(cnpj=/m)?.[1] ?? "";
    expect(FERRAMENTAS).toMatch(new RegExp(`async def ${ferramenta}\\(\\s*cnpj: Cnpj,\\s*como_era_em`));
    // a CLI roda um comando que existe, com opções que existem
    comandoExiste(cli.replace(/\\\n\s*/g, "").match(/\$ (tickerlab [^\n]+)/)?.[1] ?? "");
    // a API chama uma rota documentada, com a chave no cabeçalho por variável (nunca uma chave escrita)
    const rota = api.match(/curl "https?:\/\/[^/]+(\/data\/v1\/[^?"]+)/)?.[1] ?? "";
    rotaDocumentada(`GET ${rota.replace("33000167000101", "{cnpj}")}`);
    expect(api).toContain("Bearer $TICKERLAB_CHAVE");
  });

  it("a resposta da janela traz fonte, licença e data, sem número inventado", () => {
    const resposta = desesc(semTags(trecho('<pre class="janela-resposta">', "</pre>")));
    for (const campo of ['"sources"', '"license"', '"attribution"', '"published_at"', '"known_at"'])
      expect(resposta, campo).toContain(campo);
    expect(resposta).toContain('"value": <valor da fonte>');
    expect(resposta).not.toMatch(/R\$|"value": -?\d/);
    // uma resposta de verdade (a amostra da CVM dos testes; `tests/test_site.py` confere as datas no arquivo)
    const nota = semTags(trecho('<div class="janela guias"', "</div></section>"));
    expect(nota).toContain("Uma linha da resposta real: a DFP 2024 da Petrobras, entregue à CVM em 26/02/2025");
    expect(nota).not.toMatch(/ilustrativ/i);
    expect(resposta).toContain(`"published_at": "${RESPOSTA_DO_EXEMPLO.publicado}"`);
    expect(resposta).toContain(`"value": "${RESPOSTA_DO_EXEMPLO.periodo}"`);
    // a data pedida vem depois da entrega: senão a resposta não traria a linha
    const pedida = resposta.match(/"known_at": "([\d-]+)"/)?.[1] ?? "";
    expect(pedida >= RESPOSTA_DO_EXEMPLO.publicado).toBe(true);
  });

  it("um único pedido de chave na página inteira, e o destino existe na documentação", () => {
    const botoes = [...principal().matchAll(/<a class="botao[^"]*" href="([^"]+)"[^>]*>([^<]+)<\/a>/g)];
    expect(botoes.filter(([, href]) => href === COMO_PEDIR_A_CHAVE)).toHaveLength(1);
    expect(vezes(semTags(html), "Pedir uma chave")).toBe(1);
    // os passos de cada porta só explicam ("como pedir"), sem outro botão
    expect(DOCUMENTACAO).toContain('id="comecar"');
  });

  // PR 4 da frente 2 (texto aprovado pelo Tiago em 24/11/2026): uma seção só, com os cartões, a lista da lista
  // única das portas e os passos para começar
  const portas = () => trecho('<section class="faixa secao portas" id="portas"', "</section>");

  it("as três portas: o conector é a principal, depois a CLI e a API, cada cartão com a âncora antiga e o seu guia", () => {
    const cartoes = portas().split('<article id="').slice(1);
    expect(cartoes.map((c) => c.slice(0, c.indexOf('"')))).toEqual(["conector", "comandos", "api"]);
    for (const ancora of ["conector", "comandos", "api"]) expect(vezes(html, `id="${ancora}"`), ancora).toBe(1);
    expect(cartoes.map((c) => semTags(c.match(/<h3>([^<]+)<\/h3>/)?.[1] ?? ""))).toEqual(["Conector MCP", "CLI", "API"]);
    expect(cartoes.map((c) => c.includes('class="porta principal"'))).toEqual([true, false, false]);
    const links = cartoes.map((c) => c.match(/class="seta" href="([^"]+)"/)?.[1] ?? "");
    expect(links).toEqual([
      `${URL_DO_CODIGO}/blob/main/docs/guia-do-analista-conector.md`,
      `${URL_DO_CODIGO}/blob/main/docs/cli.md`,
      `${URL_DA_API}/documentacao/`,
    ]);
    // os guias citados existem no repositório público
    for (const guia of ["guia-do-analista-conector.md", "cli.md"]) expect(ler("docs", guia).length, guia).toBeGreaterThan(0);
    const exemplos = cartoes.map((c) => desesc(c.match(/<code class="porta-exemplo">([^<]+)<\/code>/)?.[1] ?? ""));
    expect(exemplos[0]).toBe("analise_completa · buscar_empresas");
    for (const nome of exemplos[0].split(" · ")) expect(FERRAMENTAS, nome).toMatch(new RegExp(`async def ${nome}\\(`));
    comandoExiste(exemplos[1]);
    rotaDocumentada(exemplos[2]);
  });

  it("a lista do que dá para pedir vem da lista única: cada nome existe na sua porta", () => {
    const lista = trecho('<ul class="consultas-grade">', "</ul>");
    const cartoes = lista.split('<li class="consulta">').slice(1);
    expect(cartoes).toHaveLength(consultasDasPortas.length);
    expect(cartoes.map((c) => desesc(c.match(/<h4>([^<]+)<\/h4>/)?.[1] ?? ""))).toEqual(
      consultasDasPortas.map((c) => c.nome),
    );
    const nomesDaPorta = (porta: "conector" | "cli" | "api") => consultasDasPortas.flatMap((c) => c[porta].nomes ?? []);
    expect(nomesDaPorta("conector")).toContain("analise_completa");
    for (const nome of nomesDaPorta("conector")) expect(TODAS_AS_FERRAMENTAS, nome).toMatch(new RegExp(`async def ${nome}\\(`));
    for (const comando of nomesDaPorta("cli")) comandoExiste(comando);
    for (const rota of nomesDaPorta("api")) rotaDocumentada(rota);
    // nada de pessoa física: nem a consulta, nem a ferramenta, nem a rota
    expect(semTags(portas())).not.toMatch(/Sócios e donos|socios_e_donos|\/people|CPF/);
  });

  it("como começar: três passos que só citam comandos da CLI, o beta sem cobrança e nenhum endereço publicado", () => {
    const passos = trecho('<ol class="v2-passos-da-cli passos-em-linha">', "</ol>");
    expect(vezes(passos, "<li>")).toBe(3);
    const citados = [...passos.matchAll(/<code>([^<]+)<\/code>/g)].map((m) => desesc(m[1]));
    expect(citados).toEqual(["pipx", "tickerlab login", "tickerlab instrucoes"]);
    for (const citado of citados) comandoExiste(citado);
    expect(semTags(passos)).toContain("beta fechado, sem cobrança");
    expect(passos).toContain(`href="${COMO_PEDIR_A_CHAVE}"`);
    // o endereço do conector vem com a chave: nenhuma parte da página o publica
    expect(html).not.toMatch(/mcp\.tickerlab|https?:\/\/[^\s"]*\/mcp/);
  });

  it("os botões das portas levam à documentação, a todas as rotas e ao guia do analista", () => {
    const atalhos = trecho('<p class="atalhos">', "</p>");
    expect(atalhos).toContain(`href="${URL_DA_API}/documentacao/"`);
    expect(atalhos).toContain(`href="${URL_DA_API}/#catalogo"`);
    expect(atalhos).toContain(`href="${URL_DO_CODIGO}/blob/main/docs/guia-do-analista-conector.md"`);
    expect(ler("site-api", "index.html")).toContain('id="catalogo"');
  });

  it("as seções antigas de cada porta saíram (agora é uma seção só)", () => {
    for (const antiga of ["Porta 1 · Conector MCP", "Porta 2 · CLI", "Porta 3 · API", "v2-conector", "v2-cli"])
      expect(html, antiga).not.toContain(antiga);
  });

  it("a descrição da página diz as três portas e cabe no Google", () => {
    expect(DADOS.descricao.length).toBeLessThanOrEqual(160);
    expect(DADOS.descricao).toMatch(/fonte/);
    for (const porta of ["conector MCP", "CLI", "API"]) expect(DADOS.descricao, porta).toContain(porta);
    expect(html).toContain(`<meta name="description" content="${esc(DADOS.descricao)}"`);
  });

  it("as travas das três portas numa lista só, com a de pessoa física e a da chave", () => {
    const secao = trecho('<section class="faixa secao v2-travas-das-portas"', "</section>");
    const titulos = [...secao.matchAll(/<dt>([^<]+)<\/dt>/g)].map((m) => m[1]);
    expect(titulos).toEqual([
      "Fonte e data em cada número",
      "Nenhum número inventado",
      "Pessoa física só com permissão",
      "A chave não vai ao chat",
      "Só leitura, as mesmas regras",
      "Nada é recomendação de investimento",
    ]);
    // política de privacidade, versão 19: pessoa física só para a organização com a permissão, e nunca o resto
    expect(semTags(secao)).toContain("Sem a permissão de ver pessoas, desligada por padrão");
    expect(semTags(secao)).toContain("nunca CPF, menor de idade, endereço ou contato");
    expect(semTags(heroi())).toContain("Sem CPF nem contato de pessoa");
    expect(semTags(html)).not.toContain("Sem dado de pessoa física");
  });

  it("como era na data: três datas, a mais nova aberta, e cada resposta valendo no dia escolhido", () => {
    const secao = trecho('<section class="faixa secao" id="como-era"', "</section>");
    for (const nome of ["known_at", "--como-era", "como_era_em"]) expect(secao, nome).toContain(`<code>${nome}</code>`);
    const escolhas = [...secao.matchAll(/<input[^>]*name="instante"[^>]*>/g)].map((m) => m[0]);
    expect(escolhas.map((m) => m.includes("checked"))).toEqual([false, false, true]);
    const respostas = [...secao.matchAll(/<pre class="janela-resposta guia-painel" data-instante="([\d-]+)"[^>]*>([\s\S]*?)<\/pre>/g)];
    expect(respostas).toHaveLength(3);
    for (const [, dia, corpo] of respostas) {
      const texto = desesc(semTags(corpo));
      const publicado = texto.match(/"published_at": "([\d-]+)"/)?.[1] ?? "";
      const valeAte = texto.match(/"valid_until": (?:"([\d-]+)"|null)/)?.[1];
      // a versão mostrada já era pública no dia e ainda não tinha sido trocada
      expect(publicado <= dia, dia).toBe(true);
      if (valeAte) expect(dia < valeAte, dia).toBe(true);
      expect(texto, dia).toContain(`known_at=${dia}`);
      expect(texto, dia).toContain('"value": <valor da fonte>');
    }
    // a DFP 2024 é a mesma da janela do topo: a mesma data real de entrega (a da amostra da CVM)
    const dfp2024 = respostas.map(([, , corpo]) => desesc(semTags(corpo))).filter((t) => t.includes('"2024-12-31"'));
    expect(dfp2024).toHaveLength(1);
    expect(dfp2024[0]).toContain(`"published_at": "${RESPOSTA_DO_EXEMPLO.publicado}"`);
    expect(desesc(semTags(respostas[0][2]))).toContain(`"valid_until": "${RESPOSTA_DO_EXEMPLO.publicado}"`);
  });

  it("a demonstração da conversa vem depois das portas, dita gravada, com fonte e sem pessoa nem promessa", () => {
    // linha 903, PR E: texto fixo, nenhuma chamada a modelo no site público
    const secao = trecho('<section class="faixa secao v2-demonstracao"', "</section>");
    const texto = semTags(secao);
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
    // política de privacidade, versão 19: o rodapé não diz que pessoa física nunca sai
    expect(semTags(html)).toContain("Pessoa física não entra nesta conversa: o nome de sócio só sai para a organização");
    expect(semTags(html)).not.toContain("Pessoa física não entra na resposta.");
    expect(secao).not.toMatch(/<script|<form|<input|fetch\(/);
  });

  it("a demonstração só cita ferramenta e filtro que o conector registra", () => {
    const secao = trecho('<section class="faixa secao v2-demonstracao"', "</section>");
    const citadas = [...secao.matchAll(/<code>([^<]+)<\/code>/g)].map((m) => m[1]);
    expect(citadas).toEqual(["buscar_empresas"]);
    expect(FERRAMENTAS).toMatch(/async def buscar_empresas\(/);
    for (const filtro of ["cnae:", "uf:", "situacao_cadastral:", "aberta_antes_de:"]) expect(FERRAMENTAS, filtro).toContain(filtro);
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

  it("a ordem da página: topo, portas (com o cartão de cada uma), a demonstração, travas, como era na data, a base e a vitrine", () => {
    const ordem = [
      'id="titulo-heroi"',
      'id="portas"',
      'id="conector"',
      'id="comandos"',
      'id="api"',
      'id="demonstracao"',
      'id="travas"',
      'id="como-era"',
      'id="titulo-da-base"',
      'id="ligado-pelo-cnpj"',
      'id="cruzamentos"',
      'class="faixa secao v2-vitrine"',
      'class="faixa secao final"',
    ];
    const lugares = ordem.map((marca) => html.indexOf(marca));
    for (const [i, lugar] of lugares.entries()) expect(lugar, ordem[i]).toBeGreaterThan(0);
    expect([...lugares].sort((a, b) => a - b)).toEqual(lugares);
  });

  it("o que repetia saiu: o terminal antigo, a seção do agente, as regras e as outras janelas", () => {
    for (const peca of ["v2-terminal", "v2-agente", "v2-regras", "v2-janelas", "Ver os comandos", "Usar no Claude"])
      expect(html, peca).not.toContain(peca);
    // as quatro regras continuam em Dados
    const dados = renderizar("dados.html");
    for (const [titulo] of REGRAS_DA_BASE) expect(dados, titulo).toContain(`<h3>${esc(titulo)}</h3>`);
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
    // duas datas: a da lista de tabelas montadas (tabelas e fontes) e a da fotografia das companhias
    expect(texto).toContain(
      `Tabelas e fontes em ${catalogo.totais.tabelas_conferidas_em_curto} · companhias em ${baseEmNumeros.medido_em_curto}`,
    );
    // cada número com a conta recolhida, que abre sem JavaScript
    expect(painel.match(/<details class="como-foi-calculado">/g)).toHaveLength(4);
    expect(painel).not.toMatch(/<details[^>]*\sopen/);
  });

  it("o painel da base também aparece no celular", () => {
    expect(css()).not.toContain(".v2-painel-pilha { display: none; }");
  });

  it("as abas da janela e de 'como era na data' funcionam sem JavaScript, pelo CSS", () => {
    const estilo = css();
    expect(estilo).toContain(".guias .guia-painel { display: none; }");
    for (let i = 0; i < 3; i++)
      expect(estilo).toContain(`.guias > .guia-escolha[data-ordem="${i}"]:checked ~ .guia-painel[data-ordem="${i}"]`);
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
      expect(texto, tema.chave).toContain(tema.tabelas === 1 ? "1 tabela" : `${tema.tabelas} tabelas`);
    });
    // política de privacidade, versão 19: na tela, pessoa física só para a organização com a permissão
    expect(semTags(secao)).toContain("Nome de pessoa física só aparece para a organização");
    expect(semTags(secao)).toContain("com a permissão de ver pessoas na tela, desligada por padrão, e nunca o CPF");
    expect(semTags(html)).not.toContain("nome de pessoa física não aparece");
    expect(secao).toContain('href="/dados.html#');
  });

  it("os cruzamentos: as fechadas por pergunta, as abertas por último, cada fato com o número, a fonte e a conta", () => {
    const secao = trecho('<section class="faixa secao v2-cruzamentos" id="cruzamentos"', "</section>");
    expect(semTags(secao)).toContain(esc(fatosDaBase.subtitulo));
    expect(fatosDaBase.subtitulo).toContain(`medidas em ${fatosDaBase.medido_em_curto}`);
    const chaves = fatosDaBase.grupos.map((g) => g.chave);
    const ordem = ["crescendo", "se_mexeu", "diligencia", "antes", "fora_do_balanco", "abertas"];
    expect(chaves.every((c) => ordem.includes(c))).toBe(true);
    expect([...chaves].sort((a, b) => ordem.indexOf(a) - ordem.indexOf(b))).toEqual(chaves);
    const abertas = fatosDaBase.grupos[fatosDaBase.grupos.length - 1];
    expect(abertas.chave).toBe("abertas");
    expect(abertas.fatos.map((f) => f.chave)).toEqual(["lucros", "parecer"]);
    const fatos = fatosDaBase.grupos.flatMap((g) => g.fatos);
    const cartoes = secao.split('<article class="cartao v2-fato"').slice(1);
    expect(cartoes).toHaveLength(fatos.length);
    fatosDaBase.grupos.forEach((grupo) => {
      expect(grupo.fatos.length, grupo.chave).toBeGreaterThan(0);
      expect(semTags(secao), grupo.chave).toContain(esc(grupo.pergunta));
    });
    fatos.forEach((fato, i) => {
      const texto = semTags(cartoes[i]);
      expect(texto, fato.chave).toContain(fato.numero);
      expect(texto, fato.chave).toContain(esc(fato.texto));
      expect(texto, fato.chave).toContain(`Fonte: ${esc(fato.fonte)}`);
      expect(cartoes[i], fato.chave).toContain("<summary>Como foi calculado</summary>");
      expect(texto, fato.chave).toContain(esc(fato.como_foi_calculado));
      // o recorte por estado e por setor (2º PR da linha 925), quando a medição o trouxe
      expect(cartoes[i].includes("<summary>Por estado e por setor</summary>"), fato.chave).toBe(
        fato.recorte !== undefined,
      );
      for (const barra of [...(fato.recorte?.por_uf.barras ?? []), ...(fato.recorte?.por_setor.barras ?? [])]) {
        expect(texto, fato.chave).toContain(`${esc(barra.rotulo)}${barra.parte} de ${barra.todo} (${barra.porcento})`);
      }
    });
    // a vaga "cruzamentos" da vitrine leva até aqui
    expect(vitrine.find((v) => v.chave === "cruzamentos")?.link).toBe("/#cruzamentos");
  });

  it("a chamada final leva à documentação (sem um segundo botão de chave) e diz que o beta é fechado", () => {
    const final = trecho('<section class="faixa secao final"', "</section>");
    expect(final).toContain(`href="${URL_DA_API}/documentacao/" rel="noopener">Ler a documentação</a>`);
    expect(final).not.toContain(`href="${COMO_PEDIR_A_CHAVE}"`);
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
    const semAviso = desesc(texto).replace(AVISOS, "");
    for (const proibida of PROIBIDAS) expect(proibida.test(semAviso), String(proibida)).toBe(false);
  });
});
