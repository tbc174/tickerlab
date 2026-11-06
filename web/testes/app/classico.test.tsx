// @vitest-environment jsdom
// O Streamlit virou a "versão clássica" em app.tickerlab.com.br/classico/ (plano "app novo vira o
// principal", 18/10): todo link do app novo para ele sai daqui, relativo (mesmo endereço).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CAMINHO_DO_CLASSICO, linkDoClassico } from "../../src/app/classico";
import { TELAS_DO_APP } from "../../src/app/rotas";
import { EmConstrucao } from "../../src/app/telas/EmConstrucao";

afterEach(cleanup);

describe("links para a versão clássica (o Streamlit em /classico)", () => {
  it("a raiz do clássico termina em barra (é a página inicial do Streamlit)", () => {
    expect(CAMINHO_DO_CLASSICO).toBe("/classico");
    expect(linkDoClassico()).toBe("/classico/");
  });

  it("uma página com os parâmetros na ordem dada, como o linkDoApp do site", () => {
    expect(linkDoClassico("research", { ticker: "PETR4" })).toBe("/classico/research?ticker=PETR4");
    expect(linkDoClassico("comparar", { tickers: "PETR4,VALE3", periodo: "1y" })).toBe(
      "/classico/comparar?tickers=PETR4,VALE3&periodo=1y",
    );
    expect(linkDoClassico("meus-dados")).toBe("/classico/meus-dados");
  });

  it("página com contrato e sem tela nova leva à mesma página na versão clássica", () => {
    const pagina = { ...TELAS_DO_APP[0], titulo: "Tela futura", url: "tela-futura" };
    render(<EmConstrucao pagina={pagina} />);
    const link = screen.getByRole("link", { name: /Abrir na versão clássica/ });
    expect(link.getAttribute("href")).toBe("/classico/tela-futura");
  });
});
