// @vitest-environment jsdom
// "Continue a conta": cada página de ferramenta termina com 2 ou 3 outras, e o link leva os números
// que a pessoa preencheu (do endereço desta para o endereço da outra), só onde a unidade bate.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EXEMPLO_DE_APORTES } from "../../src/ferramentas/AportesEMetas";
import { EXEMPLO_DO_ANO, EXEMPLO_DO_DARF } from "../../src/ferramentas/CalculadoraDeDarf";
import { EXEMPLO_DE_JUROS } from "../../src/ferramentas/CalculadoraDeJuros";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { CONTINUACOES, enderecoDaContinuacao, ligarContinuacoes } from "../../src/ferramentas/continuar";
import { EXEMPLO_DO_CONVERSOR } from "../../src/ferramentas/ConversorDeMoedas";
import { EXEMPLO_DA_CORRECAO } from "../../src/ferramentas/CorrecaoPelaInflacao";
import { EXEMPLO_DA_QUEDA, EXEMPLO_DA_TAXA } from "../../src/ferramentas/CustoDasTaxas";
import { EXEMPLO_DO_FINANCIAMENTO } from "../../src/ferramentas/Financiamento";
import { EXEMPLO_DO_FUNDO } from "../../src/ferramentas/FundosERendaFixa";
import { EXEMPLO_DO_JURO_REAL } from "../../src/ferramentas/JuroReal";
import { FERRAMENTAS_DO_SITE } from "../../src/ferramentas/paginas";
import { EXEMPLO_DO_PRECO_MEDIO } from "../../src/ferramentas/PrecoMedio";
import { EXEMPLO_DA_PONTE } from "../../src/ferramentas/QuantoDaria";
import { EXEMPLO_DA_RENDA_FIXA } from "../../src/ferramentas/RendaFixa";
import { EXEMPLO_DE_RENDA } from "../../src/ferramentas/ViverDeRenda";
import { renderizar } from "../../src/entry-server";
import type { DadosDoBc } from "../../src/ferramentas/dados";
import { Ilha } from "../../src/ferramentas/registro";

const chaves = (exemplo: object, prefixo = "") => Object.keys(exemplo).map((k) => prefixo + k);

// as chaves que cada página lê do endereço (com o prefixo de cada calculadora)
const CHAVES_DE: Record<string, string[]> = {
  "calculadora-de-juros-compostos.html": chaves(EXEMPLO_DE_JUROS),
  "calculadora-de-aportes-e-metas.html": chaves(EXEMPLO_DE_APORTES),
  "custo-das-taxas-e-da-queda.html": [...chaves(EXEMPLO_DA_TAXA, "taxa."), ...chaves({ queda: EXEMPLO_DA_QUEDA }, "queda.")],
  "calculadora-viver-de-renda.html": chaves(EXEMPLO_DE_RENDA),
  "sorte-em-serie.html": [],
  "calculadora-de-darf.html": [...chaves(EXEMPLO_DO_DARF), ...chaves(EXEMPLO_DO_ANO), "modo"],
  "conversor-de-moedas.html": chaves(EXEMPLO_DO_CONVERSOR),
  "calculadora-de-renda-fixa.html": chaves(EXEMPLO_DA_RENDA_FIXA),
  "calculadora-de-juro-real.html": chaves(EXEMPLO_DO_JURO_REAL, "real."),
  "calculadora-de-correcao-pela-inflacao.html": chaves(EXEMPLO_DA_CORRECAO),
  "calculadora-de-preco-medio.html": chaves(EXEMPLO_DO_PRECO_MEDIO),
  "fundo-ou-cdb.html": chaves(EXEMPLO_DO_FUNDO),
  "simulador-de-financiamento.html": chaves(EXEMPLO_DO_FINANCIAMENTO),
  "quanto-daria.html": chaves(EXEMPLO_DA_PONTE),
};
const PAGINAS = FERRAMENTAS_DO_SITE.map((f) => f.arquivo);

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("continue a conta", () => {
  it("cada ferramenta liga 2 ou 3 outras, e só leva chaves que as duas páginas leem", () => {
    expect(Object.keys(CONTINUACOES).sort()).toEqual([...PAGINAS].sort());
    for (const [origem, continuacoes] of Object.entries(CONTINUACOES)) {
      expect(continuacoes.length, origem).toBeGreaterThanOrEqual(2);
      expect(continuacoes.length, origem).toBeLessThanOrEqual(3);
      for (const c of continuacoes) {
        expect(PAGINAS, origem).toContain(c.para);
        expect(c.para, origem).not.toBe(origem);
        for (const [de, para, se] of c.levar) {
          expect(CHAVES_DE[origem], `${origem}: ${de}`).toContain(de);
          expect(CHAVES_DE[c.para], `${c.para}: ${para}`).toContain(para);
          if (se) expect(CHAVES_DE[origem], `${origem}: ${se[0]}`).toContain(se[0]);
        }
        for (const chave of Object.keys(c.fixos ?? {})) expect(CHAVES_DE[c.para], `${c.para}: ${chave}`).toContain(chave);
      }
    }
  });

  it("leva os números do endereço, com o nome de lá, e só a taxa ao ano onde a outra é ao ano", () => {
    const [aportes, custo] = CONTINUACOES["calculadora-de-juros-compostos.html"];
    expect(enderecoDaContinuacao(aportes, "?capital=20.000&taxa=1&unidadeDaTaxa=mes&prazo=5")).toBe(
      "/calculadora-de-aportes-e-metas.html?inicial=20.000&taxa=1&unidadeDaTaxa=mes",
    );
    expect(enderecoDaContinuacao(custo, "?capital=20.000&taxa=1&unidadeDaTaxa=mes")).toBe(
      "/custo-das-taxas-e-da-queda.html?taxa.capital=20.000",
    );
    expect(enderecoDaContinuacao(custo, "?capital=20.000&taxa=9&unidadeDaTaxa=ano")).toBe(
      "/custo-das-taxas-e-da-queda.html?taxa.capital=20.000&taxa.retorno=9",
    );
  });

  it("sem números no endereço, o link abre a outra com o exemplo dela", () => {
    const [aportes] = CONTINUACOES["calculadora-de-juros-compostos.html"];
    expect(enderecoDaContinuacao(aportes, "")).toBe("/calculadora-de-aportes-e-metas.html");
  });

  it("os fixos vão sempre: a unidade do que foi levado, o ativo que faz sentido vindo daqui", () => {
    const paraRendaFixa = CONTINUACOES["fundo-ou-cdb.html"].find((c) => c.para === "calculadora-de-renda-fixa.html")!;
    expect(enderecoDaContinuacao(paraRendaFixa, "?valor=5.000&anos=4")).toBe(
      "/calculadora-de-renda-fixa.html?valor=5.000&prazo=4&unidade=anos",
    );
    const paraODolar = CONTINUACOES["conversor-de-moedas.html"].find((c) => c.para === "quanto-daria.html")!;
    expect(enderecoDaContinuacao(paraODolar, "?valor=100&de=USD")).toBe("/quanto-daria.html?ativo=dolar");
  });

  it("toda página de ferramenta termina com o bloco das ligações", () => {
    for (const arquivo of PAGINAS) {
      const html = renderizar(arquivo);
      expect(html, arquivo).toContain('aria-label="Continue a conta"');
      for (const c of CONTINUACOES[arquivo]) expect(html, arquivo).toContain(`href="${enderecoDaContinuacao(c, "").replaceAll("&", "&amp;")}"`);
    }
  });

  it("no clique, o link já sai com os números que a pessoa mudou", async () => {
    window.history.replaceState(null, "", "/calculadora-de-juros-compostos.html");
    document.body.innerHTML = renderizar("calculadora-de-juros-compostos.html").replace(/^[\s\S]*<body[^>]*>|<\/body>[\s\S]*$/g, "");
    await act(async () => {
      ligarFerramentas(document);
    });
    ligarContinuacoes(document);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Valor aplicado"), { target: { value: "25.000" } });
    });
    const link = document.querySelector<HTMLAnchorElement>('a[href^="/calculadora-de-aportes-e-metas.html"]')!;
    fireEvent.click(link);
    expect(link.getAttribute("href")).toContain("inicial=25.000");
  });

  it("o juro real lê do endereço a taxa que chegou de outra ferramenta", async () => {
    const dados: DadosDoBc = { gerado_em: "2026-10-14T13:40:00-03:00", fonte: "BC" };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(dados))));
    window.history.replaceState(null, "", "/calculadora-de-juro-real.html?real.nominal=9&real.inflacao=4");
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="juroReal" />);
    await act(async () => {
      ligarFerramentas(document);
    });
    expect((screen.getByLabelText("Rendimento") as HTMLInputElement).value).toBe("9");
    expect((screen.getByLabelText("Inflação") as HTMLInputElement).value).toBe("4");
  });
});
