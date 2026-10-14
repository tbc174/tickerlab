// O site público em React: as rotas, a pasta site/ em dia com o React e as peças comuns.
// (Até a troca, no PR 10 da série 2, cada página foi comparada com a gerada pelo Python e saiu igual.)
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { Modulo } from "../src/conteudo";
import { arquivos, arquivosFixos, renderizar } from "../src/entry-server";
import { dataPorExtenso } from "../src/paginas/Novidades";
import { ROTAS } from "../src/rotas";
import { contagem } from "../src/site/comum";

const SITE = join(process.cwd(), "..", "site");
// LF sempre: o Git no Windows pode tirar os arquivos com CRLF
const doSite = (nome: string) => readFileSync(join(SITE, nome), "utf8").replace(/\r\n/g, "\n");

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

