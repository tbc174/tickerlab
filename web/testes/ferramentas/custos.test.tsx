// @vitest-environment jsdom
// A tela do custo das taxas e da queda (a conta é conferida no golden.test.ts).
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { EXEMPLO_DA_TAXA, calcularQueda, calcularTaxa } from "../../src/ferramentas/CustoDasTaxas";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { formatarPorcentagem } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("custo das taxas e da queda", () => {
  it("o exemplo: 1% ao ano leva quase um quinto em 20 anos", () => {
    const r = calcularTaxa(EXEMPLO_DA_TAXA);
    if (typeof r === "string") throw new Error(r);
    expect(r.fracao_do_resultado).toBeCloseTo(1 - 0.99 ** 20, 12);
  });

  it("entradas ruins viram mensagem", () => {
    expect(calcularTaxa({ ...EXEMPLO_DA_TAXA, taxa: "x" })).toMatch(/números/);
    expect(calcularTaxa({ ...EXEMPLO_DA_TAXA, anos: "2,5" })).toMatch(/anos inteiros/);
    expect(calcularTaxa({ ...EXEMPLO_DA_TAXA, taxa: "100" })).toMatch(/entre 0% e 100%/);
  });

  it("a queda vale escrita com ou sem o sinal", () => {
    expect(calcularQueda("50")).toBeCloseTo(1, 12);
    expect(calcularQueda("-50")).toBeCloseTo(1, 12);
    expect(calcularQueda("100")).toMatch(/99,99%/);
    expect(calcularQueda("")).toMatch(/Digite/);
  });

  it("no navegador, mudar a queda muda a alta pedida", async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="queda" />);
    await act(async () => {
      ligarFerramentas(document);
    });
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Queda"), { target: { value: "20" } });
    });
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarPorcentagem(0.25));
  });
});
