// @vitest-environment jsdom
// A tela da sorte em série (a conta é conferida no golden.test.ts).
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { simular } from "../../src/ferramentas/contas/sorte_em_serie";
import { formatarPorcentagem } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";
import { SEMENTE_INICIAL } from "../../src/ferramentas/SorteEmSerie";

afterEach(() => {
  document.body.innerHTML = "";
});

const resultado = () => document.querySelector("[data-resultado]")?.textContent;

describe("sorte em série", () => {
  it("o HTML pronto mostra o exemplo da semente inicial, com o gráfico das três curvas", () => {
    const html = renderToStaticMarkup(<Ilha nome="sorte" />);
    expect(html).toContain(formatarPorcentagem(simular(100, 250, SEMENTE_INICIAL).retorno_da_melhor));
    expect(html.match(/<polyline /g)).toHaveLength(3);
  });

  it("no navegador, sortear de novo troca as estratégias, e a quantidade muda o total", async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="sorte" />);
    await act(async () => {
      ligarFerramentas(document);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("Sortear de novo"));
    });
    expect(resultado()).toBe(formatarPorcentagem(simular(100, 250, SEMENTE_INICIAL + 1).retorno_da_melhor));
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Quantas estratégias"), { target: { value: "10" } });
    });
    expect(document.body.textContent).toContain("A melhor de 10");
  });
});
