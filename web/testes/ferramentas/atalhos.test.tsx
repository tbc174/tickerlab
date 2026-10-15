// @vitest-environment jsdom
// Os valores de hoje em um clique: Selic e CDI de hoje, IPCA de 12 meses e o esperado pelo Focus, e
// o juro real do Tesouro IPCA+. Cada um com a data e a fonte na dica; dado velho avisa; série que
// falta não vira botão. Na tela, o botão só aparece quando o arquivo chega, e sem ele nada quebra.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { atalhosDeInflacao, atalhosDeJuroReal, atalhosDeJuros } from "../../src/ferramentas/atalhos";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { em12Meses } from "../../src/ferramentas/contas/inflacao";
import type { DadosDoBc } from "../../src/ferramentas/dados";
import { formatarNumero, formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

const HOJE = new Date("2026-10-14T15:00:00-03:00");
const IPCA: [string, number][] = Array.from({ length: 12 }, (_, i) => [`2025-${String(i + 1).padStart(2, "0")}`, 0.004]);
const DADOS: DadosDoBc = {
  gerado_em: "2026-10-14T13:40:00-03:00",
  fonte: "Banco Central do Brasil e Tesouro Nacional",
  cdi: { ao_ano: 0.1315, data: "2026-10-13" },
  selic_meta: { ao_ano: 0.1325, data: "2026-10-13" },
  ipca: { meses: IPCA, ultimo: "2025-12" },
  focus: {
    ipca: { data: "2026-10-09", anos: { "2026": 0.0522, "2027": 0.043, "2028": 0.0379, "2029": 0.035 } },
    selic: { data: "2026-10-09", anos: { "2026": 0.1325, "2027": 0.12 } },
  },
  tesouro: {
    data: "2026-10-13",
    titulos: [
      { titulo: "Tesouro IPCA+", vencimento: "2029-05-15", taxa: 0.0666 },
      { titulo: "Tesouro IPCA+", vencimento: "2035-05-15", taxa: 0.0669 },
      { titulo: "Tesouro IPCA+", vencimento: "2050-08-15", taxa: 0.0657 },
      { titulo: "Tesouro Prefixado", vencimento: "2032-01-01", taxa: 0.1251 },
    ],
  },
};

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

describe("atalhos (contas)", () => {
  it("juros: Selic e CDI de hoje, em % ao ano, com a data e a fonte", () => {
    expect(atalhosDeJuros(DADOS, HOJE)).toEqual([
      { rotulo: "Selic hoje", valor: "13,25", dica: "Meta da Selic em 13/10/2026 · Banco Central" },
      { rotulo: "CDI hoje", valor: "13,15", dica: "CDI de 13/10/2026, ao ano · Banco Central" },
    ]);
  });

  it("inflação: IPCA de 12 meses e o esperado pelo Focus para este ano e o próximo", () => {
    const atalhos = atalhosDeInflacao(DADOS, HOJE);
    expect(atalhos.map((a) => a.rotulo)).toEqual(["IPCA 12 meses", "IPCA esperado 2026", "IPCA esperado 2027"]);
    expect(atalhos[0].valor).toBe(formatarNumero(em12Meses(IPCA) * 100));
    expect(atalhos[1]).toEqual({
      rotulo: "IPCA esperado 2026",
      valor: "5,22",
      dica: "Expectativa do mercado (mediana do Focus) de 09/10/2026 · Banco Central",
    });
  });

  it("juro real: o Tesouro IPCA+ com o vencimento mais perto de 10 anos", () => {
    expect(atalhosDeJuroReal(DADOS, HOJE)).toEqual([
      { rotulo: "Tesouro IPCA+ 2035", valor: "6,69", dica: "Taxa real de compra em 13/10/2026 · Tesouro Nacional" },
    ]);
  });

  it("série que falta não vira atalho; dado velho avisa na dica", () => {
    expect(atalhosDeJuros({ gerado_em: "", fonte: "" }, HOJE)).toEqual([]);
    expect(atalhosDeJuroReal({ gerado_em: "", fonte: "" }, HOJE)).toEqual([]);
    const velho = { ...DADOS, selic_meta: { ao_ano: 0.1325, data: "2026-09-20" } };
    expect(atalhosDeJuros(velho, HOJE)[0].dica).toMatch(/dado de \d+ dias úteis atrás/);
  });
});

describe("atalhos (na tela)", () => {
  const abrir = async (resposta: () => Promise<Response>) => {
    vi.stubGlobal("fetch", vi.fn(resposta));
    window.history.replaceState(null, "", "/calculadora-de-juros-compostos.html");
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="juros" />);
    await act(async () => {
      ligarFerramentas(document);
    });
  };

  it("com o arquivo, o botão Selic hoje põe a taxa e muda o resultado", async () => {
    await abrir(async () => new Response(JSON.stringify(DADOS)));
    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Selic hoje" }));
    });
    expect((screen.getByLabelText("Taxa de juros") as HTMLInputElement).value).toBe("13,25");
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(10000 * 1.1325 ** 10));
    expect(screen.getByRole("button", { name: "IPCA esperado 2026" })).toBeTruthy();
  });

  it("sem o arquivo, nenhum botão e nenhum erro", async () => {
    const erros = vi.spyOn(console, "error");
    await abrir(async () => new Response("", { status: 404 }));
    expect(screen.queryByRole("button", { name: "Selic hoje" })).toBeNull();
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(10000 * 1.1 ** 10));
    expect(erros).not.toHaveBeenCalled();
    erros.mockRestore();
  });
});

describe("juro real v2", () => {
  it("tem os valores de hoje nos dois campos e mostra o erro comum ao lado", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(DADOS))));
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="juroReal" />);
    await act(async () => {
      ligarFerramentas(document);
    });
    await act(async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Selic hoje" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "IPCA esperado 2026" }));
    });
    const texto = document.body.textContent ?? "";
    // 13,25% de rendimento e 5,22% de inflação: (1,1325 / 1,0522) − 1, não 13,25 − 5,22
    expect(texto).toContain(`não ${formatarNumero(13.25 - 5.22)}%`);
    expect(document.querySelector("[data-resultado]")?.textContent).toContain(formatarNumero((1.1325 / 1.0522 - 1) * 100));
  });
});
