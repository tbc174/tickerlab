// Os "anúncios da casa" (pedido da Campanha, 13/10/2026: sem anúncio de terceiros) e o aviso que
// toda ferramenta leva.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AnuncioDaCasa, DESTINOS, linkDoAnuncio } from "../../src/ferramentas/AnuncioDaCasa";
import { AvisoDaFerramenta } from "../../src/ferramentas/AvisoDaFerramenta";

describe("anúncio da casa", () => {
  it("o link leva a origem no padrão da campanha (campanha-medicao.md)", () => {
    const link = new URL(linkDoAnuncio("cadastro", "juros-compostos"));
    expect(link.origin).toBe("https://app.tickerlab.com.br");
    expect(Object.fromEntries(link.searchParams)).toEqual({
      utm_source: "site",
      utm_medium: "casa",
      utm_campaign: "ferramentas",
      utm_content: "juros-compostos",
    });
  });

  it("a ficha leva ao Backtest do app, onde ela fica, com um exemplo pronto", () => {
    const link = new URL(linkDoAnuncio("ficha", "sorte-em-serie"));
    expect(link.pathname).toBe("/backtest");
    expect(link.searchParams.get("ticker")).toBe("PETR4.SA");
    expect(link.searchParams.get("utm_content")).toBe("sorte-em-serie");
  });

  it("só destinos que existem hoje (a lista de espera entra quando a Campanha a criar)", () => {
    expect(Object.keys(DESTINOS).sort()).toEqual(["cadastro", "ficha"]);
  });

  it("o nome da ferramenta no link é um código simples", () => {
    expect(() => linkDoAnuncio("cadastro", "Juros & Cia")).toThrow(RangeError);
  });

  it("o bloco tem título, texto e o botão com o link", () => {
    const html = renderToStaticMarkup(<AnuncioDaCasa destino="ficha" ferramenta="juros-compostos" />);
    expect(html).toContain(DESTINOS.ficha.titulo);
    expect(html).toContain("utm_content=juros-compostos");
    expect(html).toContain('aria-label="Do TickerLab"');
  });
});

describe("aviso da ferramenta", () => {
  it("diz que não é recomendação e o que a conta deixa de fora", () => {
    const html = renderToStaticMarkup(
      <AvisoDaFerramenta foraDaConta={["imposto de renda", "taxas"]} />,
    );
    expect(html).toContain("não é recomendação de investimento");
    expect(html).toContain("imposto de renda");
    expect(html).toContain("taxas");
  });
});
