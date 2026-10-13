import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { modulos } from "../src/conteudo";
import { arquivos, renderizar } from "../src/entry-server";
import { ROTAS } from "../src/rotas";

describe("rotas do site", () => {
  it("cada página vira um arquivo .html diferente", () => {
    const nomes = ROTAS.map((r) => r.arquivo);
    expect(new Set(nomes).size).toBe(nomes.length);
    for (const nome of nomes) expect(nome).toMatch(/^[a-z0-9-]+\.html$/);
  });
});

describe("HTML pronto (sem JavaScript)", () => {
  it("a página inicial já traz o conteúdo que vem do Python", () => {
    const html = renderizar("index.html", "/assets/x.js");
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain('<html lang="pt-BR">');
    for (const m of modulos) expect(html).toContain(m.nome);
  });

  it("título e descrição escapados", () => {
    expect(renderizar("index.html", '/a.js?"x"')).toContain('src="/a.js?&quot;x&quot;"');
  });

  it("todas as rotas renderizam", () => {
    for (const arquivo of arquivos) {
      expect(renderToStaticMarkup(ROTAS.find((r) => r.arquivo === arquivo)!.pagina())).not.toBe("");
    }
  });
});
