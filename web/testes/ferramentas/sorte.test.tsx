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
    expect(html.match(/class="grafico-ferramenta-linha"/g)).toHaveLength(3);
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

// --- ferramentas v2: eixos, histograma e a correção pelas tentativas ----------------------------
describe("sorte em série v2", () => {
  const abrir = async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="sorte" />);
    await act(async () => {
      ligarFerramentas(document);
    });
  };
  const r = simular(100, 250, SEMENTE_INICIAL);

  it("as três curvas começam em R$ 100 e terminam no retorno de cada uma", async () => {
    await abrir();
    const pontas = [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));
    expect(pontas[0]).toBeCloseTo(100 * (1 + r.retorno_da_melhor), 9);
    expect(pontas[1]).toBeCloseTo(100 * (1 + r.retorno_da_mediana), 9);
    expect(pontas[2]).toBeCloseTo(100 * (1 + r.retorno_da_pior), 9);
  });

  it("o histograma conta todas as estratégias", async () => {
    await abrir();
    const contagens = [...document.querySelectorAll("[data-quantas]")].map((el) => Number(el.getAttribute("data-quantas")));
    expect(contagens.reduce((a, b) => a + b, 0)).toBe(100);
  });

  it("mostra quantas passam no teste ingênuo e quantas sobram com a correção", async () => {
    await abrir();
    const texto = document.body.textContent ?? "";
    expect(texto).toContain(`${r.passam_sem_correcao} de 100 passariam`);
    expect(texto).toContain(`corrigindo pelas 100 tentativas, ${r.passam_com_correcao}`);
  });

  it("o eixo do tempo fala em dias de pregão", async () => {
    await abrir();
    const grafico = screen.getByRole("img", { name: /dia a dia/ });
    await act(async () => {
      fireEvent.keyDown(grafico, { key: "ArrowLeft" });
    });
    expect(screen.getByRole("status").textContent).toContain("dia 249");
  });
});
