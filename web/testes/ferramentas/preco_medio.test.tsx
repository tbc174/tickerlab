// @vitest-environment jsdom
// A calculadora de preço médio: até 8 operações numa grade, o preço médio e o resultado das vendas
// (a conta é conferida no golden.test.ts), a simulação no endereço e a mensagem quando sai mais do
// que há.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { EXEMPLO_DO_PRECO_MEDIO, operacoesDosCampos } from "../../src/ferramentas/PrecoMedio";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { calcular } from "../../src/ferramentas/contas/preco_medio";
import { formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

afterEach(() => {
  document.body.innerHTML = "";
});

async function abrir(busca = "") {
  window.history.replaceState(null, "", `/calculadora-de-preco-medio.html${busca}`);
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome="precoMedio" />);
  await act(async () => {
    ligarFerramentas(document);
  });
}

describe("preço médio", () => {
  it("as linhas vazias ficam de fora e as preenchidas viram operações", () => {
    const ops = operacoesDosCampos(EXEMPLO_DO_PRECO_MEDIO);
    expect(ops.map((o) => o.tipo)).toEqual(["compra", "compra", "venda"]);
    expect(ops[0]).toEqual({ tipo: "compra", quantidade: 100, preco: 25, custos: 4.9 });
  });

  it("mostra o preço médio e o resultado da venda do exemplo", async () => {
    await abrir();
    const linhas = calcular(operacoesDosCampos(EXEMPLO_DO_PRECO_MEDIO));
    const fim = linhas[linhas.length - 1];
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(fim.preco_medio!));
    expect(document.body.textContent).toContain(formatarReais(fim.resultado!));
    expect(document.querySelectorAll(".preco-medio tbody tr")).toHaveLength(8);
  });

  it("mexer numa operação muda o resultado e vai para o endereço", async () => {
    await abrir();
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Preço na operação 2"), { target: { value: "40" } });
    });
    expect(new URLSearchParams(window.location.search).get("p2")).toBe("40");
    const linhas = calcular(operacoesDosCampos({ ...EXEMPLO_DO_PRECO_MEDIO, p2: "40" }));
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(formatarReais(linhas[linhas.length - 1].preco_medio!));
  });

  it("vender mais do que tem dá a mensagem", async () => {
    await abrir("?q3=500");
    expect(document.body.textContent).toContain("Saem mais ações do que há na posição");
  });
});
