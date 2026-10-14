// O site público em React: as rotas, a pasta site/ em dia com o React e as peças comuns.
// (Até a troca, no PR 10 da série 2, cada página foi comparada com a gerada pelo Python e saiu igual.)
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { type Modulo, marca } from "../src/conteudo";
import { arquivos, arquivosFixos, renderizar } from "../src/entry-server";
import { css } from "../src/estilo";
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

describe("estilo v2 (ADR 0065)", () => {
  const estilo = css();
  // os blocos de "reduzir movimento" (o do CSS antigo e os do visual v2)
  const menosMovimento = estilo.split("@media (prefers-reduced-motion: reduce)").slice(1).join("");

  it("traz as peças do visual novo", () => {
    for (const classe of [".v2-heroi-fundo", ".v2-painel", ".v2-bento", ".v2-pausa", ".v2-fita"])
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
    for (const peca of [".v2-aurora span", ".v2-painel::before", ".v2-fita-faixa"])
      expect(menosMovimento).toContain(`${peca} { animation: none !important; }`);
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

