// @vitest-environment jsdom
// A tela do DARF (a conta é conferida no golden.test.ts) e a página com as regras e as fontes.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EXEMPLO_DO_ANO, EXEMPLO_DO_DARF, apurar, apurarOAno, principal } from "../../src/ferramentas/CalculadoraDeDarf";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { renderizar } from "../../src/entry-server";
import { formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

afterEach(() => {
  document.body.innerHTML = "";
});

const resultado = () => document.querySelector("[data-resultado]")?.textContent;

describe("calculadora de DARF", () => {
  it("o exemplo: R$ 30 mil vendidos com R$ 3 mil de lucro pagam R$ 448,50", () => {
    const a = apurar(EXEMPLO_DO_DARF);
    if (typeof a === "string") throw new Error(a);
    expect(principal(a)).toEqual(["DARF a pagar", formatarReais(448.5)]);
  });

  it("isento, abaixo de R$ 10 e sem imposto dizem por que não há DARF", () => {
    const isento = apurar({ ...EXEMPLO_DO_DARF, vendas: "15.000" });
    const pequeno = apurar({ ...EXEMPLO_DO_DARF, resultadoComum: "40", irrf: "0" });
    const prejuizo = apurar({ ...EXEMPLO_DO_DARF, resultadoComum: "-500" });
    for (const a of [isento, pequeno, prejuizo]) if (typeof a === "string") throw new Error(a);
    expect(principal(isento as never)[1]).toBe("Isento");
    expect(principal(pequeno as never)[1]).toBe("Abaixo de R$ 10");
    expect(principal(prejuizo as never)[1]).toBe("Sem imposto");
  });

  it("campo vazio vale zero e o prejuízo anterior pode vir com ou sem sinal", () => {
    const a = apurar({ ...EXEMPLO_DO_DARF, resultadoDayTrade: "", prejuizoComum: "-1.000" });
    if (typeof a === "string") throw new Error(a);
    expect(a.base_comum).toBe(2000);
    expect(apurar({ ...EXEMPLO_DO_DARF, vendas: "trinta" })).toMatch(/números/);
  });

  it("no navegador, o mês passa a ser o anterior ao de hoje e o resultado responde", async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="darf" />);
    await act(async () => {
      ligarFerramentas(document);
    });
    const hoje = new Date();
    const anterior = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
    expect((screen.getByLabelText("Ano das operações") as HTMLInputElement).value).toBe(
      String(anterior.getFullYear()),
    );
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Total vendido em ações (sem day trade)"), {
        target: { value: "19.999" },
      });
    });
    expect(resultado()).toBe("Isento");
  });

  it("a página lista cada regra com o link para a fonte oficial", () => {
    const html = renderizar("calculadora-de-darf.html");
    expect(html).toContain("pergunta 706");
    expect(html).toContain("pergunta 707");
    expect(html).toContain("art. 68");
    expect(html).toContain("https://www.gov.br/receitafederal/");
    expect(html).toContain("<strong>0,005%</strong>");
    expect(html).toContain(`<strong>${formatarReais(20000)}</strong>`);
    expect(html).toContain("não substitui um contador");
  });
});

// --- ferramentas v2: o ano inteiro, com o prejuízo e o imposto pequeno passando de um mês para outro
describe("DARF do ano", () => {
  const abrir = async (busca = "?modo=ano") => {
    window.history.replaceState(null, "", `/calculadora-de-darf.html${busca}`);
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="darf" />);
    await act(async () => {
      ligarFerramentas(document);
    });
  };
  const linhas = () => [...document.querySelectorAll(".darf-do-ano tbody tr")];

  it("a conta do ano leva o prejuízo de um mês para os seguintes, por tipo", () => {
    const ano = apurarOAno(EXEMPLO_DO_ANO);
    if (typeof ano === "string") throw new Error(ano);
    expect(ano.meses).toHaveLength(12);
    // fevereiro dá prejuízo comum de R$ 2.000; março compensa uma parte dele
    expect(ano.meses[1].saldos_seguintes.prejuizo_comum).toBe(2000);
    expect(ano.meses[3].base_comum).toBeLessThan(2500);
    expect(ano.total).toBeCloseTo(ano.meses.reduce((soma, m) => soma + m.darf, 0), 9);
    expect(ano.prejuizoQueSobra.comum).toBe(ano.meses[11].saldos_seguintes.prejuizo_comum);
  });

  it("a tela mostra os 12 meses, o total do ano e o que passa para o ano seguinte", async () => {
    await abrir();
    expect(linhas()).toHaveLength(12);
    const ano = apurarOAno(EXEMPLO_DO_ANO);
    if (typeof ano === "string") throw new Error(ano);
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(ano.total));
    expect(document.body.textContent).toContain("Prejuízo que passa para");
  });

  it("mexer num mês muda os meses seguintes e vai para o endereço", async () => {
    await abrir();
    const antes = linhas()[4].textContent;
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Resultado comum em abril"), { target: { value: "-20.000" } });
    });
    expect(linhas()[4].textContent).not.toBe(antes);
    expect(new URLSearchParams(window.location.search).get("c4")).toBe("-20.000");
  });

  it("copiar resumo leva o total e o prejuízo que sobra", async () => {
    const escrever = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: escrever }, configurable: true });
    await abrir();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copiar resultado" }));
    });
    expect(escrever.mock.calls[0][0]).toMatch(/Imposto sobre ações em \d{4}: R\$/);
  });
});
