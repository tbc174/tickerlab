// O site público em React: as rotas, a pasta site/ em dia com o React e as peças comuns.
// (Até a troca, no PR 10 da série 2, cada página foi comparada com a gerada pelo Python e saiu igual.)
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  type Modulo,
  amostraRelatorio,
  marca,
  planos,
  relatorioSemanalEletricas,
} from "../src/conteudo";
import { arquivos, arquivosFixos, renderizar } from "../src/entry-server";
import { css } from "../src/estilo";
import { dataPorExtenso } from "../src/paginas/Novidades";
import {
  DADOS as DADOS_DO_RAIO_X,
  MOMENTO_DO_RAIO_X,
  PDF_DO_RAIO_X,
  RAIO_X,
} from "../src/paginas/RaioXDoChoque";
import { DADOS as DADOS_DO_RELATORIO } from "../src/paginas/RelatorioExemplo";
import { DADOS as DADOS_DO_SETOR } from "../src/paginas/RelatorioSemanalEletricas";
import { ROTAS } from "../src/rotas";
import { MODULOS_DO_PRODUTO, contagem, disponiveis, moduloPelaChave } from "../src/site/comum";
import { ASSINATURA, EMAIL_DE_CONTATO, URL_DO_SITE, linkDoApp } from "../src/site/textos";

const SITE = join(process.cwd(), "..", "site");
// LF sempre: o Git no Windows pode tirar os arquivos com CRLF
const doSite = (nome: string) => readFileSync(join(SITE, nome), "utf8").replace(/\r\n/g, "\n");
// o texto como o React escreve no HTML
const esc = (texto: string) =>
  texto.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("'", "&#x27;");
const semTags = (html: string) => html.replace(/<[^>]+>/g, "");
/** O pedaço do HTML que começa em `inicio` e vai até o primeiro `fim` depois dele. */
function trecho(html: string, inicio: string, fim: string): string {
  const de = html.indexOf(inicio);
  expect(de, `não achei ${inicio}`).toBeGreaterThanOrEqual(0);
  return html.slice(de, html.indexOf(fim, de) + fim.length);
}

describe("rotas do site", () => {
  it("cada página vira um arquivo .html diferente", () => {
    const nomes = ROTAS.map((r) => r.arquivo);
    expect(new Set(nomes).size).toBe(nomes.length);
    for (const nome of nomes) expect(nome).toMatch(/^[a-z0-9-]+\.html$/);
  });

  it("nenhuma página .html sobra em site/ sem rota no React", () => {
    const naPasta = readdirSync(SITE).filter((n) => n.endsWith(".html"));
    expect(naPasta.sort()).toEqual([...arquivos].sort());
  });
});

describe("site/ em dia com o React (rode `npm run site` em web/ se falhar)", () => {
  for (const arquivo of arquivos) {
    it(arquivo, () => {
      expect(renderizar(arquivo)).toBe(doSite(arquivo));
    });
  }
  for (const [nome, conteudo] of Object.entries(arquivosFixos())) {
    it(nome, () => {
      expect(conteudo).toBe(doSite(nome));
    });
  }
});

describe("HTML pronto", () => {
  it("começa com o doctype e em português", () => {
    expect(renderizar("index.html").startsWith('<!doctype html>\n<html lang="pt-BR">')).toBe(
      true,
    );
  });

  it("nenhuma marca de HTML cru sobra depois de expandir", () => {
    for (const arquivo of arquivos) expect(renderizar(arquivo)).not.toContain("tl-bruto");
  });

  it("o security.txt segue a RFC 9116", () => {
    const texto = arquivosFixos()[".well-known/security.txt"];
    expect(texto).toContain("Contact: mailto:contato@tickerlab.com.br\n");
    expect(texto).toContain("Expires: 2027-10-17T00:00:00.000Z\n");
    expect(texto).toContain("Preferred-Languages: pt-BR, en\n");
    expect(texto).toContain("Canonical: https://tickerlab.com.br/.well-known/security.txt\n");
  });

  it("a descrição de cada página cabe no resultado do Google (até 160 caracteres)", () => {
    for (const arquivo of arquivos.filter((a) => a !== "404.html")) {
      const descricao = /<meta name="description" content="([^"]*)"/.exec(renderizar(arquivo))?.[1];
      expect(descricao, arquivo).toBeDefined();
      // o HTML escapa & e aspas; conta cada entidade como um caractere
      const texto = descricao!.replace(/&(amp|quot|#x27);/g, "x");
      expect(texto.length, `${arquivo}: ${texto.length}`).toBeLessThanOrEqual(160);
    }
  });

  it("o mapa do site tem todas as páginas menos a 404", () => {
    const mapa = arquivosFixos()["sitemap.xml"];
    expect(mapa).toContain("<loc>https://tickerlab.com.br/</loc>");
    expect(mapa).toContain("<loc>https://tickerlab.com.br/sobre.html</loc>");
    expect(mapa).toContain("<loc>https://tickerlab.com.br/novidades.html</loc>");
    expect(mapa).not.toContain("404");
  });
});

function moduloDeTeste(prontas: number, emBreve: number): Modulo {
  const funcionalidade = (disponivel: boolean, i: number) => ({
    nome: `f${i}`,
    descricao: "x",
    pagina_do_app: disponivel ? "visao-geral" : null,
    pagina_do_site: null,
    ticker: null,
    disponivel,
  });
  return {
    chave: "teste",
    nome: "Teste",
    objetivo: "obj",
    frase: "frase",
    funcionalidades: [
      ...Array.from({ length: prontas }, (_, i) => funcionalidade(true, i)),
      ...Array.from({ length: emBreve }, (_, i) => funcionalidade(false, prontas + i)),
    ],
  };
}

describe("movimento sem prejuízo (ADR 0065)", () => {
  it("nada vem escondido esperando o JavaScript: o Google e quem não tem JS veem tudo", () => {
    for (const arquivo of arquivos) {
      const html = renderizar(arquivo);
      expect(html, arquivo).not.toContain("v2-revelar");
      expect(html, arquivo).not.toContain("v2-anima");
    }
  });

  it("todo fundo animado tem o botão de pausa (WCAG 2.2.2)", () => {
    const comFundo = arquivos.filter((a) => renderizar(a).includes("data-fundo-mercado"));
    expect(comFundo).toContain("index.html");
    for (const arquivo of comFundo) {
      expect(renderizar(arquivo), arquivo).toMatch(
        /<button class="v2-pausa" type="button" data-pausa="" aria-pressed="false">/,
      );
    }
  });
});

describe("página inicial v2", () => {
  const html = renderizar("index.html");

  it("o título é a assinatura do manual", () => {
    expect(semTags(trecho(html, '<h1 id="titulo-heroi">', "</h1>"))).toBe(ASSINATURA);
  });

  it("o bento das frentes saiu da inicial: backtest e carteira vivem em Ferramentas", () => {
    expect(html).not.toContain('<div class="v2-bento">');
    const ferramentas = renderizar("ferramentas.html");
    const bento = trecho(ferramentas, '<div class="v2-bento">', "</div></section>");
    for (const chave of ["estrategias", "carteira"]) {
      const modulo = moduloPelaChave(chave);
      expect(bento).toContain(`<h3>${esc(modulo.nome)}`);
      expect(bento).toContain(`href="/produto.html#${modulo.chave}"`);
      expect(bento).toContain(`<p class="contagem">${contagem(modulo)}</p>`);
    }
  });
});

describe("outras páginas v2 (série site e app v2, PR 2)", () => {
  const outras = arquivos.filter((a) => a !== "index.html");

  it("toda página abre com o mesmo topo escuro da inicial, com o título dentro dele", () => {
    for (const arquivo of outras) {
      const html = renderizar(arquivo);
      const topo = trecho(html, '<div class="escura topo-da-pagina v2-heroi-fundo v2-heroi-pagina', "</section>");
      expect(topo, arquivo).toContain("data-fundo-mercado");
      expect(topo, arquivo).toMatch(/<h1[ >]/);
    }
  });

  it("toda chamada final tem o horizonte que sobe", () => {
    for (const arquivo of outras) {
      const html = renderizar(arquivo);
      expect(html, arquivo).not.toContain('<div class="escura"><section class="faixa secao final"');
    }
  });

  it("Produto: a barra de cada módulo mostra a fração já disponível, sem depender do JS", () => {
    const html = renderizar("produto.html");
    for (const modulo of MODULOS_DO_PRODUTO) {
      const topo = trecho(html, `<h2 id="titulo-${modulo.chave}">`, "</p></div>");
      const fracao = disponiveis(modulo) / modulo.funcionalidades.length;
      expect(topo).toContain(
        `<span class="v2-barra" aria-hidden="true"><i style="--p:${fracao.toFixed(3)}"></i></span>`,
      );
    }
  });

  it("Produto: os atalhos ficam no topo (o movimento.js copia para o menu que gruda)", () => {
    const topo = trecho(renderizar("produto.html"), '<section class="faixa secao v2-pagina-topo">', "</section>");
    for (const modulo of MODULOS_DO_PRODUTO) expect(topo).toContain(`href="#${modulo.chave}"`);
  });

  for (const arquivo of ["metodologia.html", "termos.html", "privacidade.html", "novidades.html"]) {
    it(`${arquivo}: sumário feito no build, um link para cada seção, e a barra de leitura`, () => {
      const html = renderizar(arquivo);
      expect(html).toContain('<div class="v2-progresso" data-progresso="" aria-hidden="true">');
      const sumario = trecho(html, '<nav class="v2-sumario"', "</nav>");
      const links = [...sumario.matchAll(/href="#([^"]+)"/g)].map((m) => m[1]);
      expect(links.length).toBeGreaterThanOrEqual(2);
      expect(new Set(links).size).toBe(links.length);
      const texto = trecho(html, '<section class="secao texto-longo v2-texto"', "</main>");
      for (const id of links) expect(texto, id).toContain(`id="${id}"`);
      // nenhuma seção fica de fora do sumário
      const nivel = arquivo === "termos.html" || arquivo === "privacidade.html" ? "h3" : "h2";
      const secoes = arquivo === "novidades.html" ? texto.match(/<article /g) : texto.match(new RegExp(`<${nivel}[ >]`, "g"));
      expect(links).toHaveLength(secoes!.length);
    });
  }

  it("Sobre: a Inteligência Integrada em três círculos, com as três perspectivas", () => {
    const html = renderizar("sobre.html");
    const venn = trecho(html, '<figure class="v2-venn"', "</figure>");
    for (const nome of ["Fundamentalista", "Técnica", "Quantitativa", "Inteligência", "Integrada"])
      expect(venn).toContain(`>${nome}</text>`);
    expect(trecho(html, '<div class="v2-acreditamos">', '<p class="contagem v2-lema">')).toContain(
      "Inteligência Integrada.",
    );
  });

  it("Planos: a faixa grátis, o cartão Pessoa e o cartão Casa, sem preço", () => {
    const html = renderizar("precos.html");
    const texto = semTags(html);
    // a faixa grátis leva ao app; o Pessoa mostra os limites do plano completo, da mesma tabela do app
    const gratis = trecho(html, '<section class="faixa secao v2-depois-do-topo"', "</section>");
    expect(semTags(gratis)).toContain("Para conhecer, de graça");
    expect(gratis).toContain("Começar grátis");
    const cartoes = trecho(html, '<div class="v2-planos">', "</div></section>");
    expect(cartoes.match(/<article class="v2-plano/g)).toHaveLength(2);
    const pessoa = trecho(cartoes, "<h3>Pessoa</h3>", "</article>");
    const completo = planos.nomes[planos.nomes.length - 1];
    const linhas = planos.tabela as Record<string, string>[];
    for (const recurso of ["Simulações salvas", "Favoritos", "Ativos na carteira"]) {
      const linha = linhas.find((l) => l.Recurso === recurso)!;
      expect(pessoa).toContain(`${esc(recurso)}: <b>${esc(linha[completo])}</b>`);
    }
    // o Casa está em construção: sem botão que leve a lugar nenhum, só o e-mail do site
    const casa = trecho(cartoes, "<h3>Casa</h3>", "</article>");
    expect(semTags(casa)).toContain("por assento");
    expect(semTags(casa)).toContain("em construção");
    expect(casa).not.toContain(linkDoApp());
    expect(casa).toContain(`mailto:${EMAIL_DE_CONTATO}`);
    // o texto do pré-lançamento (ADR 0029, Emenda 1) e nenhum valor em dinheiro
    expect(texto).toContain("definido antes do lançamento");
    expect(texto).toContain("toda conta usa");
    expect(html).not.toContain("R$");
  });

  it("Planos: a tabela agrupa os níveis em Para conhecer e Pessoa, com todos os planos do app", () => {
    const tabela = trecho(renderizar("precos.html"), '<table class="planos v2-comparativo">', "</table>");
    const cabecalho = trecho(tabela, "<thead>", "</thead>");
    expect(semTags(cabecalho)).toContain("Para conhecer, de graça");
    expect(semTags(cabecalho)).toContain("Pessoa");
    for (const nome of planos.nomes) expect(cabecalho).toContain(`>${nome}</th>`);
  });

  it("Planos: ✓ e — na tabela, com Sim e Não para quem usa leitor de tela", () => {
    const tabela = trecho(renderizar("precos.html"), '<table class="planos v2-comparativo">', "</table>");
    expect(tabela).toContain('<span class="v2-sim" role="img" aria-label="Sim">✓</span>');
    expect(tabela).toContain('<span class="v2-nao" role="img" aria-label="Não">—</span>');
    expect(tabela).not.toContain("<td>Sim</td>");
  });

  it("404: o número grande, a linha que despenca e os dois caminhos", () => {
    const html = renderizar("404.html");
    expect(html).toContain('<p class="v2-quatro-zero-quatro" aria-hidden="true">404</p>');
    expect(html).toContain('<svg class="v2-queda"');
    expect(html).toContain('href="/">Ir para o início</a>');
    expect(html).toContain(">Abrir o app</a>");
  });
});

describe("estilo v2 (ADR 0065)", () => {
  const estilo = css();
  // os blocos de "reduzir movimento" (o do CSS antigo e os do visual v2)
  const menosMovimento = estilo.split("@media (prefers-reduced-motion: reduce)").slice(1).join("");

  it("traz as peças do visual novo", () => {
    for (const classe of [".v2-heroi-fundo", ".v2-painel", ".v2-bento", ".v2-pausa"])
      expect(estilo).toContain(classe);
  });

  it("alta e queda vêm da marca, nos dois temas", () => {
    const { paleta_clara: claro, paleta_escura: escuro } = marca;
    expect(estilo).toContain(`--alta: ${claro.alta}; --queda: ${claro.queda};`);
    expect(estilo).toContain(`--alta: ${escuro.alta}; --queda: ${escuro.queda};`);
    expect(estilo).not.toContain("#f0525b"); // o vermelho do protótipo, que não é o da marca
  });

  it("com 'reduzir movimento', o que roda sem parar para e o botão de pausa some", () => {
    expect(menosMovimento).toContain(".v2-pausa { display: none; }");
    for (const peca of [".v2-aurora span", ".v2-painel::before"])
      expect(menosMovimento).toContain(`${peca} { animation: none !important; }`);
  });

  it("no celular o hero volta a ter uma coluna só (a regra do v2 vem depois da antiga)", () => {
    const duasColunas = estilo.lastIndexOf(".heroi { grid-template-columns: 1.05fr .95fr; }");
    const umaColuna = estilo.lastIndexOf(".heroi { grid-template-columns: 1fr; }");
    expect(duasColunas).toBeGreaterThan(0);
    expect(umaColuna).toBeGreaterThan(duasColunas);
    expect(estilo.lastIndexOf("@media (max-width: 860px)", umaColuna)).toBeGreaterThan(duasColunas);
  });

  it("o botão de pausa tem área de toque de 44 px em tela de toque (ADR 0066)", () => {
    expect(estilo).toMatch(/@media \(pointer: coarse\) \{[^}]*\.v2-pausa \{ min-height: 44px;/);
  });

  it("nada do catálogo do design system (só existia no protótipo)", () => {
    expect(estilo).not.toContain("no-catalogo");
  });
});

describe("contagem do módulo", () => {
  it("no singular e no plural", () => {
    expect(contagem(moduloDeTeste(1, 2))).toBe("1 disponível · 2 em breve");
    expect(contagem(moduloDeTeste(3, 1))).toBe("3 disponíveis · 1 em breve");
    expect(contagem(moduloDeTeste(0, 3))).toBe("3 em breve");
  });
});

describe("Novidades", () => {
  it("mostra a atualização mais nova com a data por extenso e as correções", () => {
    const html = renderizar("novidades.html");
    expect(html).toContain("13 de outubro de 2026");
    expect(html).toContain("Relatório da empresa");
    expect(html).toContain("<h3>Correções</h3>");
    expect(html).toContain("Nada aqui é recomendação");
  });

  it("escreve a data sem fuso (o dia 1º não vira o último dia do mês anterior)", () => {
    expect(dataPorExtenso("2026-11-01")).toBe("1 de novembro de 2026");
  });
});


describe("relatório de exemplo da base (plano do relatório-modelo, 17/10/2026)", () => {
  const html = renderizar("relatorio-de-exemplo.html");
  const texto = semTags(html);

  it("abre com a empresa, o CNPJ, a data dos dados e o aviso", () => {
    expect(texto).toContain(`${amostraRelatorio.empresa}: o que a base do TickerLab mostra`);
    expect(texto).toContain(`CNPJ ${amostraRelatorio.cnpj}`);
    expect(texto).toContain(`Dados da base de ${amostraRelatorio.dados_de}`);
    expect(html).toContain('<p class="v2-aviso">');
    expect(texto.toLowerCase()).toContain("nada aqui é recomendação de investimento");
  });

  it("cada destaque traz a fonte, a data e o caminho para o detalhe", () => {
    expect(amostraRelatorio.destaques.length).toBeGreaterThanOrEqual(5);
    for (const d of amostraRelatorio.destaques) {
      expect(html).toContain(esc(d.texto));
      expect(texto).toContain(`dado de ${d.data}`);
    }
    expect(html).toContain('href="#ofertas-e-fundos">Ver o detalhe</a>');
  });

  it("o PDF e as seções da base estão na página, com o sumário", () => {
    expect(html).toContain(`href="${amostraRelatorio.pdf}"`);
    for (const id of [
      "auditor-e-controladas",
      "ofertas-e-fundos",
      "setor-regulado",
      "negocios-e-eventos",
    ]) {
      expect(html).toContain(`<h2 id="${id}">`);
      expect(html).toContain(`href="#${id}"`);
    }
    expect(html).toContain('href="#limites-e-cuidados"');
  });

  it("tabela longa fica fechada; o assunto do documento leva à CVM", () => {
    expect(html).toContain('<details class="v2-tabela-da-base"><summary>');
    expect(html).toMatch(/<a href="https:\/\/www\.rad\.cvm\.gov\.br\/[^"]+" rel="noopener">/);
  });

  it("não promete o que ainda não existe: o Pro aparece como em breve", () => {
    expect(texto).toContain("Em breve no plano Pro");
  });

  it("a página inicial leva ao relatório de exemplo", () => {
    expect(renderizar("index.html")).toContain('href="/relatorio-de-exemplo.html"');
  });
});


describe("relatório de setor da semana: elétricas (ADR 0109, item 10)", () => {
  const html = renderizar("relatorio-de-setor-eletricas.html");
  const texto = semTags(html);

  it("abre com o título, a data dos dados e o aviso de que não é recomendação", () => {
    expect(texto).toContain(relatorioSemanalEletricas.titulo);
    expect(texto).toContain(`Dados da base de ${relatorioSemanalEletricas.dados_de}`);
    expect(texto).toContain("Nada aqui é recomendação de investimento");
  });

  it("cada destaque mostra a fonte e a data", () => {
    expect(relatorioSemanalEletricas.destaques.length).toBeGreaterThanOrEqual(3);
    for (const d of relatorioSemanalEletricas.destaques) {
      expect(texto).toContain(d.titulo);
      expect(texto).toContain(`Fonte: ${d.fonte}; dado de ${d.data}.`);
    }
  });

  it("mostra as tabelas, o que falta e os limites", () => {
    for (const t of relatorioSemanalEletricas.tabelas) expect(texto).toContain(t.titulo);
    expect(texto).toContain("O que este relatório ainda não traz");
    expect(texto).toContain("Limites e cuidados");
    for (const l of relatorioSemanalEletricas.limites) expect(texto).toContain(l);
  });
});

describe("página Relatórios (menu do plano de 18/10, pode do Tiago em 23/10)", () => {
  const html = renderizar("relatorios.html");
  const texto = semTags(html);

  it("tem o título e a frase aprovados", () => {
    expect(texto).toContain("Relatórios");
    expect(texto).toContain(
      "Dois relatórios de exemplo, feitos com a base: o de uma empresa e o de um setor.",
    );
  });

  it("um cartão para cada relatório, com o título e a descrição da própria página", () => {
    for (const dados of [DADOS_DO_RELATORIO, DADOS_DO_SETOR]) {
      expect(html).toContain(`href="${dados.caminho}"`);
      expect(html).toContain(esc(dados.titulo));
      expect(html).toContain(esc(dados.descricao));
    }
  });

  it("os dois relatórios marcam Relatórios no topo", () => {
    for (const arquivo of [
      "relatorio-de-exemplo.html",
      "relatorio-de-setor-eletricas.html",
      "raio-x-do-choque.html",
    ]) {
      const topo = renderizar(arquivo).split("</header>")[0];
      expect(topo).toMatch(/<a href="\/relatorios.html" aria-current="[a-z]+">Relatórios<\/a>/);
    }
  });

  it("o estudo do dia vem antes dos exemplos, com o momento dos preços", () => {
    expect(html).toContain(`href="${DADOS_DO_RAIO_X.caminho}"`);
    expect(texto).toContain("Estudo do dia");
    expect(texto).toContain(MOMENTO_DO_RAIO_X);
    expect(html.indexOf(DADOS_DO_RAIO_X.caminho)).toBeLessThan(
      html.indexOf(DADOS_DO_RELATORIO.caminho),
    );
  });
});

describe("Raio-X do choque de 26/10/2026 (pode do Tiago para publicar, 26/10)", () => {
  const html = renderizar("raio-x-do-choque.html");
  const texto = semTags(html);

  it("abre sem login, com o título do estudo e o momento dos preços", () => {
    expect(texto).toContain(RAIO_X.titulo);
    expect(texto).not.toMatch(/Entrar para ler|faça login/i);
    if (RAIO_X.parcial) expect(texto).toContain(`26/10 às ${RAIO_X.hora}`);
  });

  it("traz os limites, as fontes e o aviso de que não é recomendação", () => {
    expect(texto).toContain("Limites e cuidados");
    expect(texto).toContain("De onde vem cada número");
    expect(texto).toContain("Nada aqui é recomendação de investimento");
  });

  it("o rodapé atribui os preços do estudo à B3, sem trocar a fonte das outras páginas", () => {
    const rodape = trecho(html, '<footer class="rodape escura">', "</footer>");
    expect(semTags(rodape)).toContain("Os preços deste estudo são da B3");
    expect(semTags(rodape)).not.toContain("Yahoo");
    expect(semTags(renderizar("index.html"))).toContain("Os dados vêm do Yahoo Finance");
  });

  it("o estilo do estudo fica preso dentro dele (classes rx-)", () => {
    const corpo = readFileSync(join("src", "paginas", "raio-x", "corpo.html"), "utf8");
    const estilo = trecho(corpo, "<style>", "</style>").slice("<style>".length, -"</style>".length);
    for (const regra of estilo.split("}").filter((r) => r.includes("{"))) {
      const seletor = regra.split("{")[0].trim();
      if (seletor.startsWith("@") || seletor === "") continue;
      expect(seletor, seletor).toMatch(/\.rx/);
    }
  });

  it("tem a própria imagem de compartilhar e o PDF, e os dois existem em site/", () => {
    expect(html).toContain(
      `<meta property="og:image" content="${URL_DO_SITE}${DADOS_DO_RAIO_X.imagem}"`,
    );
    expect(html).toContain(`href="${PDF_DO_RAIO_X}"`);
    for (const arquivo of [DADOS_DO_RAIO_X.imagem, PDF_DO_RAIO_X])
      expect(() => readFileSync(join(SITE, arquivo))).not.toThrow();
  });

  it("a página inicial chama para o estudo, no selo do topo e na faixa logo abaixo", () => {
    const inicio = renderizar("index.html");
    expect(inicio.split(DADOS_DO_RAIO_X.caminho).length - 1).toBeGreaterThanOrEqual(3);
    expect(semTags(inicio)).toContain("Estudo do dia");
    expect(inicio).toContain(`href="${PDF_DO_RAIO_X}"`);
  });
});
