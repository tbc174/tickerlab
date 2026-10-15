// @vitest-environment jsdom
// O simulador de financiamento: SAC e Price lado a lado (a conta é conferida no golden.test.ts), a
// diferença de juros, o gráfico das parcelas e a amortização extra.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { EXEMPLO_DO_FINANCIAMENTO, calcularFinanciamento } from "../../src/ferramentas/Financiamento";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

afterEach(() => {
  document.body.innerHTML = "";
});

async function abrir(busca = "") {
  window.history.replaceState(null, "", `/simulador-de-financiamento.html${busca}`);
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome="financiamento" />);
  await act(async () => {
    ligarFerramentas(document);
  });
}

const juros = (linhas: { juros: number }[]) => linhas.reduce((s, l) => s + l.juros, 0);

describe("financiamento SAC × Price", () => {
  it("mostra quanto a Price paga a mais de juros que o SAC", async () => {
    await abrir();
    const r = calcularFinanciamento(EXEMPLO_DO_FINANCIAMENTO);
    if (typeof r === "string") throw new Error(r);
    const diferenca = juros(r.price) - juros(r.sac);
    expect(diferenca).toBeGreaterThan(0);
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(diferenca));
  });

  it("o gráfico tem as parcelas dos dois sistemas e termina na última de cada um", async () => {
    await abrir();
    const r = calcularFinanciamento(EXEMPLO_DO_FINANCIAMENTO);
    if (typeof r === "string") throw new Error(r);
    const pontas = [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));
    expect(pontas[0]).toBeCloseTo(r.sac[r.sac.length - 1].parcela, 6);
    expect(pontas[1]).toBeCloseTo(r.price[r.price.length - 1].parcela, 6);
  });

  it("a amortização extra reduz o prazo e vai para o endereço", async () => {
    await abrir();
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Amortização extra"), { target: { value: "50.000" } });
    });
    expect(new URLSearchParams(window.location.search).get("extra")).toBe("50.000");
    const r = calcularFinanciamento({ ...EXEMPLO_DO_FINANCIAMENTO, extra: "50.000" });
    if (typeof r === "string") throw new Error(r);
    expect(r.price.length).toBeLessThan(360);
    expect(document.body.textContent).toContain(`${r.price.length} meses`);
  });
});
