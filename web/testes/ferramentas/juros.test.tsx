// @vitest-environment jsdom
// A calculadora de juros v2: o gráfico termina no número do resultado, o cenário B aparece quando a
// pessoa pede, o valor em reais de hoje e depois do IR, os deslizantes e a simulação no endereço.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CalculadoraDeJuros } from "../../src/ferramentas/CalculadoraDeJuros";
import { emReaisDeHoje, liquidoDeIr } from "../../src/ferramentas/contas/juros";
import { formatarReais } from "../../src/ferramentas/numeros";

beforeEach(() => {
  window.history.replaceState(null, "", "/calculadora-de-juros-compostos.html");
});
afterEach(() => {
  document.body.innerHTML = "";
});

const FINAL = 10000 * 1.1 ** 10; // o exemplo: R$ 10.000 a 10% ao ano por 10 anos
const pontas = () => [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));

async function abrir() {
  await act(async () => {
    render(<CalculadoraDeJuros />);
  });
}

describe("calculadora de juros v2", () => {
  it("o gráfico empilha o que foi aplicado e os juros, e termina no valor do resultado", async () => {
    await abrir();
    expect(screen.getByRole("img", { name: /Evolução/ })).toBeTruthy();
    const [aplicado, total] = pontas();
    expect(aplicado).toBe(10000);
    expect(total).toBeCloseTo(FINAL, 6);
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(FINAL));
  });

  it("mostra o valor em reais de hoje e depois do IR", async () => {
    await abrir();
    const texto = document.body.textContent ?? "";
    expect(texto).toContain(formatarReais(emReaisDeHoje(FINAL, 0.04, 120)));
    expect(texto).toContain(formatarReais(liquidoDeIr(10000, FINAL, 120)));
  });

  it("com o cenário B, o gráfico vira duas linhas e a diferença aparece", async () => {
    await abrir();
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Comparar com outro cenário"));
    });
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Taxa de juros do cenário B"), { target: { value: "12" } });
    });
    const finalB = 10000 * 1.12 ** 10;
    const [a, b] = pontas();
    expect(a).toBeCloseTo(FINAL, 6);
    expect(b).toBeCloseTo(finalB, 6);
    expect(document.body.textContent).toContain(formatarReais(finalB - FINAL));
  });

  it("taxa e prazo têm deslizante", async () => {
    await abrir();
    expect(screen.getByLabelText("Taxa de juros (deslizante)")).toBeTruthy();
    expect(screen.getByLabelText("Prazo (deslizante)")).toBeTruthy();
  });

  it("abre a simulação que está no endereço", async () => {
    window.history.replaceState(null, "", "/calculadora-de-juros-compostos.html?taxa=12&prazo=5");
    await abrir();
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(10000 * 1.12 ** 5));
  });

  it("a tabela da evolução continua para quem quer os números", async () => {
    await abrir();
    expect(screen.getByText("Ver a evolução")).toBeTruthy();
  });

  it("copiar resultado está ao lado do gráfico", async () => {
    await abrir();
    expect(screen.getByRole("button", { name: "Copiar resultado" })).toBeTruthy();
  });

  // Regressão da avaliação externa de 16/10: os simples usavam a taxa mensal equivalente dos
  // compostos (19.568,97) em vez da proporcional (10% ao ano ÷ 12), que dá os R$ 20.000 do livro.
  it("no modo simples, 10% ao ano por 10 anos dão R$ 20.000,00", async () => {
    window.history.replaceState(null, "", "/calculadora-de-juros-compostos.html?tipo=simples");
    await abrir();
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(20000));
  });

  it("no modo composto, o campo 'Com juros simples daria' também mostra R$ 20.000,00", async () => {
    await abrir();
    const texto = screen.getByText("Com juros simples daria").nextElementSibling?.textContent;
    expect(texto).toBe(formatarReais(20000));
  });
});
