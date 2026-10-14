// @vitest-environment jsdom
// A ilha das ferramentas: o HTML pronto do build já mostra a conta com os valores de exemplo, e o
// ferramentas.js (cliente.tsx) liga os campos no navegador sem mudar o desenho.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EXEMPLO_DE_JUROS, calcularJuros } from "../../src/ferramentas/CalculadoraDeJuros";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { Ilha } from "../../src/ferramentas/registro";
import { formatarReais, lerNumero } from "../../src/ferramentas/numeros";

// o React avisa no console.error quando algo dá errado ao montar
const erros = vi.spyOn(console, "error");
afterEach(() => {
  document.body.innerHTML = "";
  erros.mockClear();
});

const resultado = () => document.querySelector("[data-resultado]")?.textContent ?? "";

describe("ilha da calculadora de juros", () => {
  it("o HTML pronto já tem o resultado do exemplo", () => {
    const html = renderToStaticMarkup(<Ilha nome="juros" />);
    // R$ 10.000 a 10% ao ano por 10 anos: 10.000 × 1,1^10
    expect(html).toContain(formatarReais(10000 * 1.1 ** 10));
    expect(html).toContain('data-ferramenta="juros"');
  });

  it("no navegador, mudar a taxa muda o resultado, sem aviso do React", async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="juros" />);
    const antes = resultado();
    await act(async () => {
      expect(ligarFerramentas(document)).toBe(1);
    });
    expect(resultado()).toBe(antes); // montar por cima não muda o que a pessoa vê
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Taxa de juros"), { target: { value: "12" } });
    });
    expect(resultado()).toBe(formatarReais(10000 * 1.12 ** 10));
    expect(erros).not.toHaveBeenCalled();
  });

  it("não liga duas vezes a mesma ferramenta", async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="juros" />);
    await act(async () => {
      ligarFerramentas(document);
    });
    expect(ligarFerramentas(document)).toBe(0);
  });

  it("entrada que não é número vira uma mensagem, não um erro na página", () => {
    expect(calcularJuros({ ...EXEMPLO_DE_JUROS, taxa: "dez" })).toMatch(/números/);
    expect(calcularJuros({ ...EXEMPLO_DE_JUROS, taxa: "-100" })).toMatch(/-100%/);
    expect(calcularJuros({ ...EXEMPLO_DE_JUROS, prazo: "1,5", unidadeDoPrazo: "meses" })).toMatch(
      /meses inteiros/,
    );
    expect(calcularJuros({ ...EXEMPLO_DE_JUROS, prazo: "101" })).toMatch(/100 anos/);
  });
});

describe("resultado para leitor de tela", () => {
  it("só o número principal é anunciado, não a tabela da evolução", () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="juros" />);
    const anunciado = document.querySelector('[aria-live="polite"]');
    expect(anunciado?.querySelector("[data-resultado]")).not.toBeNull();
    expect(anunciado?.querySelector("table")).toBeNull();
  });
});

describe("números no jeito brasileiro", () => {
  it.each([
    ["1.234,56", 1234.56],
    ["1.000", 1000],
    ["10.000.000", 10000000],
    ["12,5", 12.5],
    ["1234.5", 1234.5],
    ["R$ 2.500", 2500],
    ["7%", 7],
    ["-0,5", -0.5],
    ["  42 ", 42],
    ["0.500", 0.5], // começa com zero: é decimal, não milhar
    ["0.5", 0.5],
  ])("lerNumero(%s) = %s", (texto, numero) => {
    expect(lerNumero(texto)).toBe(numero);
  });

  it.each(["", "abc", "1,2,3", "1.2.3,4,5", "--1"])("lerNumero(%s) = null", (texto) => {
    expect(lerNumero(texto)).toBeNull();
  });
});
