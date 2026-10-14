// @vitest-environment jsdom
// A tela do viver de renda (a conta é conferida no golden.test.ts).
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { EXEMPLO_DE_RENDA, calcularRenda, duracaoPorExtenso } from "../../src/ferramentas/ViverDeRenda";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
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
