// As páginas das ferramentas no site: rota, mapa do site, script só onde há calculadora, aviso e
// anúncio da casa em todas, e o catálogo do Produto (src/modulos.py) apontando para elas.
import { describe, expect, it } from "vitest";
import { modulos } from "../../src/conteudo";
import { arquivos, arquivosFixos, renderizar } from "../../src/entry-server";
import { FERRAMENTAS_DO_SITE } from "../../src/ferramentas/paginas";
import { ROTAS } from "../../src/rotas";

const PAGINAS_DE_FERRAMENTA = FERRAMENTAS_DO_SITE.map((f) => f.arquivo);

describe("páginas das ferramentas", () => {
  it("cada ferramenta da vitrine tem uma rota que carrega o script das calculadoras", () => {
    for (const arquivo of PAGINAS_DE_FERRAMENTA) {
      const rota = ROTAS.find((r) => r.arquivo === arquivo);
      expect(rota, arquivo).toBeDefined();
      expect(rota!.dados.ferramenta, arquivo).toBe(true);
    }
  });

  it("só as páginas com calculadora carregam o ferramentas.js", () => {
    for (const arquivo of arquivos) {
      const carrega = /<script src="\/ferramentas\.js\?v=[0-9a-f]{12}" defer="">/.test(renderizar(arquivo));
      expect(carrega, arquivo).toBe(PAGINAS_DE_FERRAMENTA.includes(arquivo));
    }
  });

  it("toda página de ferramenta tem a calculadora, o aviso e o anúncio da casa", () => {
    for (const arquivo of PAGINAS_DE_FERRAMENTA) {
      const html = renderizar(arquivo);
      expect(html, arquivo).toContain("data-ferramenta=");
      expect(html, arquivo).toContain("não é recomendação de investimento");
      expect(html, arquivo).toContain("O que a conta deixa de fora");
      expect(html, arquivo).toContain('aria-label="Do TickerLab"');
      expect(html, arquivo).toContain(`utm_content=${arquivo.replace(".html", "")}`);
    }
  });

  it("a vitrine, as ferramentas e o menu entram no site", () => {
    const mapa = arquivosFixos()["sitemap.xml"];
    for (const arquivo of ["ferramentas.html", ...PAGINAS_DE_FERRAMENTA]) {
      expect(mapa).toContain(`https://tickerlab.com.br/${arquivo}`);
    }
    const vitrine = renderizar("ferramentas.html");
    for (const arquivo of PAGINAS_DE_FERRAMENTA) expect(vitrine).toContain(`href="/${arquivo}"`);
    expect(renderizar("index.html")).toContain('<a href="/ferramentas.html">Ferramentas</a>');
  });

  it("o Produto leva às ferramentas que estão na vitrine (src/modulos.py)", () => {
    const doCatalogo = modulos
      .flatMap((m) => m.funcionalidades)
      .map((f) => f.pagina_do_site)
      .filter((p): p is string => p !== null);
    expect(doCatalogo.length).toBeGreaterThan(0);
    for (const pagina of doCatalogo) expect(PAGINAS_DE_FERRAMENTA).toContain(pagina);
    expect(renderizar("produto.html")).toContain('href="/calculadora-de-juros-compostos.html"');
  });
});
