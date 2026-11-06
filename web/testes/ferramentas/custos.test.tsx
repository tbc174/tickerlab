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

// --- ferramentas v2: gráficos e atalhos --------------------------------------------------------
describe("custo das taxas e da queda v2", () => {
  const abrir = async (nome: "taxa" | "queda", busca = "") => {
    window.history.replaceState(null, "", `/custo-das-taxas-e-da-queda.html${busca}`);
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome={nome} />);
    await act(async () => {
      ligarFerramentas(document);
    });
  };
  const pontas = () => [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));

  it("o gráfico empilha o que ficou com você e o que a taxa levou; o topo é o valor sem taxa", async () => {
    await abrir("taxa");
    const r = calcularTaxa(EXEMPLO_DA_TAXA);
    if (typeof r === "string") throw new Error(r);
    const [comTaxa, semTaxa] = pontas();
    expect(comTaxa).toBeCloseTo(r.com_taxa, 6);
    expect(semTaxa).toBeCloseTo(r.sem_taxa, 6);
  });

  it("os atalhos da queda põem o valor com um clique", async () => {
    await abrir("queda");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "−80%" }));
    });
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarPorcentagem(4));
  });

  it("a queda e a alta aparecem lado a lado em barras", async () => {
    await abrir("queda");
    const nomes = [...document.querySelectorAll(".grafico-ferramenta-nome")].map((el) => el.textContent);
    expect(nomes).toEqual(["Queda", "Alta para voltar"]);
  });

  it("as duas calculadoras da página guardam o endereço sem se misturar", async () => {
    await abrir("queda", "?queda.queda=20&taxa.taxa=2");
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarPorcentagem(0.25));
  });
});
