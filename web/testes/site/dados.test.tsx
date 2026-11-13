// A página Dados (dados.html) é gerada do catálogo de contratos: nenhum número é digitado à mão
// (ADR 0099 itens 4 e 7; plano do site para quem analisa, PR 3).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { baseEmNumeros, catalogo } from "../../src/conteudo";
import { arquivosFixos, renderizar } from "../../src/entry-server";
import { ROTAS } from "../../src/rotas";
import { ComoFoiCalculado } from "../../src/site/ComoFoiCalculado";
import { enderecoDaConsulta } from "../../src/site/ConsultaDaBase";

const pagina = () => renderizar("dados.html");
const semTags = (html: string) => html.replace(/<[^>]+>/g, "");
// o texto como o React escreve no HTML
const esc = (texto: string) =>
  texto.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("'", "&#x27;");
// confere sem despejar a página inteira na mensagem de erro
const tem = (texto: string, trecho: string) => texto.includes(esc(trecho));

describe("ComoFoiCalculado", () => {
  it("é um <details> fechado, que funciona sem JavaScript", () => {
    const html = renderToStaticMarkup(
      <ComoFoiCalculado resumo="Como foi calculado">o texto da conta</ComoFoiCalculado>,
    );
    expect(html).toContain("<details");
    expect(html).not.toMatch(/<details[^>]*\sopen/);
    expect(html).toContain("<summary>Como foi calculado</summary>");
    expect(html).toContain("o texto da conta");
  });
});

describe("página Dados", () => {
  it("tem rota própria e entra no mapa do site", () => {
    expect(ROTAS.map((r) => r.arquivo)).toContain("dados.html");
    expect(arquivosFixos()["sitemap.xml"]).toContain("/dados.html</loc>");
  });

  it("mostra os números medidos da base, com o 'medido em'", () => {
    const texto = semTags(pagina());
    const { numeros } = baseEmNumeros;
    expect(texto).toContain(numeros.empresas.toLocaleString("pt-BR"));
    expect(texto).toContain(numeros.linhas_de_demonstracoes.toLocaleString("pt-BR"));
    expect(texto).toContain(`Medido em ${baseEmNumeros.medido_em_curto}.`);
  });

  it("mostra os totais do catálogo, não números digitados", () => {
    const texto = semTags(pagina());
    expect(texto).toContain(`${catalogo.totais.tabelas} tabelas`);
    expect(texto).toContain(`${catalogo.totais.fontes} fontes`);
    expect(catalogo.totais.tabelas).toBe(catalogo.tabelas.length);
    expect(catalogo.totais.fontes).toBe(catalogo.fontes.length);
  });

  it("diz as quatro regras que valem para toda tabela", () => {
    const texto = semTags(pagina());
    for (const regra of ["Como era na data", "Linhagem", "Licença por tabela", "Explicação"]) {
      expect(texto, regra).toContain(regra);
    }
  });

  it("lista uma linha por tabela, nos módulos certos", () => {
    const html = pagina();
    for (const t of catalogo.tabelas) expect(html, t.tabela).toContain(`>${t.tabela}<`);
    for (const m of catalogo.modulos) expect(tem(semTags(html), m.nome), m.nome).toBe(true);
    expect(html.match(/data-tabela="/g)?.length).toBe(catalogo.tabelas.length);
  });

  it("marca 'licença em consulta' nas fontes sem resposta escrita", () => {
    const html = pagina();
    const selos = html.match(/licença em consulta/gi) ?? [];
    expect(selos.length).toBeGreaterThanOrEqual(catalogo.totais.fontes_em_consulta);
    expect(catalogo.totais.fontes_em_consulta).toBeGreaterThan(0);
  });

  it("traz cada fonte com o órgão e o que pode ser repassado", () => {
    const texto = semTags(pagina());
    for (const f of catalogo.fontes) {
      expect(tem(texto, f.orgao), f.orgao).toBe(true);
      expect(tem(texto, f.repasse), f.orgao).toBe(true);
    }
  });

  it("explica como auditar um número, com a explicação recolhida", () => {
    const html = pagina();
    expect(semTags(html)).toContain("auditar");
    expect(html).toMatch(/<details[^>]*>\s*<summary>/);
    expect(html).not.toMatch(/<details[^>]*\sopen/);
  });

  it("não cita concorrente nem promete mais dados (ADR 0099)", () => {
    const texto = semTags(pagina());
    expect(/Bloomberg|FactSet|Refinitiv|Economatica|mais dados que/i.test(texto)).toBe(false);
  });

  it("cada tabela consultável tem o botão Consultar e o link do CSV; as outras ficam só no app", () => {
    const html = pagina();
    const consultaveis = catalogo.tabelas.filter((t) => t.consultavel);
    expect(consultaveis.length).toBeGreaterThan(40);
    expect(consultaveis.length).toBeLessThan(catalogo.tabelas.length);
    expect(html.match(/data-consultar="/g)?.length).toBe(consultaveis.length);
    for (const t of consultaveis) {
      expect(html, t.tabela).toContain(`data-consultar="${t.tabela}"`);
      expect(html, t.tabela).toContain(`href="${enderecoDaConsulta(t.tabela, "", "csv")}"`);
    }
    expect(html.match(/>só no app</g)?.length).toBe(catalogo.tabelas.length - consultaveis.length);
    expect(html).toMatch(/<th data-com-consulta="" hidden="">Consulta<\/th>/);
  });

  it("a coluna, a frase e o painel da consulta nascem escondidos: só aparecem quando a API responde (revisão do PR 3)", () => {
    const html = pagina();
    const marcados = html.match(/<[a-z0-9]+ [^>]*data-com-consulta=""[^>]*>/g) ?? [];
    const modulos = html.match(/data-modulo-da-lista=""/g)?.length ?? 0;
    // um cabeçalho por módulo, uma célula por tabela, a frase e o painel
    expect(marcados.length).toBe(modulos + catalogo.tabelas.length + 2);
    for (const tag of marcados) expect(tag).toContain('hidden=""');
    expect(html).toMatch(/<div [^>]*data-com-consulta=""[^>]*><div data-consulta-base="">/);
    // nada promete a tabela inteira: o CSV tem teto, e a última linha do arquivo avisa quando corta
    expect(semTags(html)).not.toMatch(/tabela inteira/);
    expect(semTags(html)).toContain("a última linha do arquivo avisa");
  });

  it("o painel de consulta vem depois da lista e antes das fontes, e a página carrega o ferramentas.js", () => {
    const html = pagina();
    const painel = html.indexOf('data-consulta-base=""');
    expect(painel).toBeGreaterThan(html.lastIndexOf('data-modulo-da-lista=""'));
    expect(painel).toBeLessThan(html.search(/<h2 id="[^"]+">De onde vêm os dados<\/h2>/));
    expect(html).toContain('id="consulta-da-base"');
    expect(html).toMatch(/<script src="\/ferramentas\.js\?v=[0-9a-f]{12}" defer="">/);
    // sem JavaScript, o painel só explica como usar; nenhuma linha vem pronta no HTML
    expect(semTags(html)).toContain("Escolha uma tabela");
    expect(semTags(html)).toContain("sem login");
  });
});
