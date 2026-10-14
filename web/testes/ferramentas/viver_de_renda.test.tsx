// @vitest-environment jsdom
// A tela do viver de renda (a conta é conferida no golden.test.ts).
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { EXEMPLO_DE_RENDA, calcularRenda, duracaoPorExtenso } from "../../src/ferramentas/ViverDeRenda";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("viver de renda", () => {
  it("só com os juros, o dinheiro dura para sempre, mas a queda no começo pode encurtar", () => {
    const r = calcularRenda(EXEMPLO_DE_RENDA);
    if (typeof r === "string") throw new Error(r);
    expect(r.duracaoNormal).toBeNull();
    expect(duracaoPorExtenso(r.duracaoNormal)).toBe("mais de 100 anos");
  });

  it("gastando o principal em 30 anos, dura 30 anos; com a queda no 1º ano, menos", () => {
    const r = calcularRenda({ ...EXEMPLO_DE_RENDA, forma: "gastando" });
    if (typeof r === "string") throw new Error(r);
    expect(r.duracaoNormal).toBe(360);
    expect(r.duracaoComQueda!).toBeLessThan(360);
  });

  it("entradas ruins viram mensagem", () => {
    expect(calcularRenda({ ...EXEMPLO_DE_RENDA, taxa: "0" })).toMatch(/sem rendimento/);
    expect(calcularRenda({ ...EXEMPLO_DE_RENDA, renda: "0" })).toMatch(/maior que zero/);
    expect(calcularRenda({ ...EXEMPLO_DE_RENDA, forma: "gastando", anos: "" })).toMatch(/números/);
    // o prazo só importa quando se gasta o principal
    expect(typeof calcularRenda({ ...EXEMPLO_DE_RENDA, anos: "" })).toBe("object");
  });

  it("no navegador, escolher gastar o principal mostra o prazo", async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="renda" />);
    await act(async () => {
      ligarFerramentas(document);
    });
    expect(screen.queryByLabelText("Por quantos anos")).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Gastando também o que juntei"));
    });
    expect(screen.getByLabelText("Por quantos anos")).toBeTruthy();
  });
});

// --- ferramentas v2: a trajetória no gráfico e a simulação no endereço --------------------------
describe("viver de renda v2", () => {
  const abrir = async (busca = "") => {
    window.history.replaceState(null, "", `/calculadora-viver-de-renda.html${busca}`);
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="renda" />);
    await act(async () => {
      ligarFerramentas(document);
    });
  };
  const pontas = () => [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));

  it("só com os juros, a linha normal fica reta e a do ano ruim chega a zero", async () => {
    await abrir();
    const r = calcularRenda(EXEMPLO_DE_RENDA);
    if (typeof r === "string") throw new Error(r);
    const [normal, comQueda] = pontas();
    expect(normal).toBeCloseTo(r.patrimonio, 2);
    expect(comQueda).toBe(0);
    const legenda = document.querySelector(".grafico-ferramenta-legenda")?.textContent ?? "";
    expect(legenda).toContain("Rendendo");
    expect(legenda).toContain("30%");
  });

  it("gastando o que juntou, abre a simulação do endereço e as duas linhas acabam em zero", async () => {
    await abrir("?forma=gastando&anos=25");
    const r = calcularRenda({ ...EXEMPLO_DE_RENDA, forma: "gastando", anos: "25" });
    if (typeof r === "string") throw new Error(r);
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(r.patrimonio));
    expect(pontas()).toEqual([0, 0]);
  });
});
