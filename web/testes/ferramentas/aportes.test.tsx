// @vitest-environment jsdom
// A tela de aportes e metas: as três perguntas usam a mesma conta (conferida no golden.test.ts).
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { EXEMPLO_DE_APORTES, prazoPorExtenso, responder } from "../../src/ferramentas/AportesEMetas";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { aporteParaMeta, valorFuturo } from "../../src/ferramentas/contas/aportes";
import { taxaPorMes } from "../../src/ferramentas/contas/juros";
import { formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

afterEach(() => {
  document.body.innerHTML = "";
});

const oitoAoAno = taxaPorMes(0.08, "ano");

describe("aportes e metas", () => {
  it("quanto vou ter: o exemplo de R$ 5.000 + R$ 500 por mês a 8% ao ano por 20 anos", () => {
    const resposta = responder(EXEMPLO_DE_APORTES);
    expect(typeof resposta).toBe("object");
    if (typeof resposta === "string") return;
    expect(resposta.principal).toBe(formatarReais(valorFuturo(5000, 500, oitoAoAno, 240)));
    expect(resposta.linhas).toHaveLength(241);
    expect(resposta.linhas.at(-1)!.aportado).toBe(5000 + 500 * 240);
  });

  it("quanto guardar por mês para R$ 200 mil", () => {
    const resposta = responder({ ...EXEMPLO_DE_APORTES, pergunta: "quanto-guardar" });
    if (typeof resposta === "string") throw new Error(resposta);
    expect(resposta.principal).toBe(formatarReais(aporteParaMeta(200000, 5000, oitoAoAno, 240)));
  });

  it("em quanto tempo, por extenso, e a meta que não chega", () => {
    const resposta = responder({ ...EXEMPLO_DE_APORTES, pergunta: "quanto-tempo" });
    if (typeof resposta === "string") throw new Error(resposta);
    expect(resposta.principal).toMatch(/^\d+ anos( e \d+ (mês|meses))?$/);
    const nunca = responder({ ...EXEMPLO_DE_APORTES, pergunta: "quanto-tempo", aporte: "0", taxa: "0" });
    expect(nunca).toMatch(/não chega em 100 anos/);
  });

  it("o campo que a pergunta não usa pode ficar vazio", () => {
    expect(typeof responder({ ...EXEMPLO_DE_APORTES, meta: "" })).toBe("object");
    expect(typeof responder({ ...EXEMPLO_DE_APORTES, pergunta: "quanto-tempo", anos: "" })).toBe("object");
    expect(responder({ ...EXEMPLO_DE_APORTES, aporte: "" })).toMatch(/números/);
  });

  it.each([
    [0, "0 meses"],
    [1, "1 mês"],
    [12, "1 ano"],
    [15, "1 ano e 3 meses"],
    [241, "20 anos e 1 mês"],
  ])("prazoPorExtenso(%i) = %s", (meses, texto) => {
    expect(prazoPorExtenso(meses)).toBe(texto);
  });

  it("no navegador, trocar a pergunta mostra o campo da meta", async () => {
    document.body.innerHTML = renderToStaticMarkup(<Ilha nome="aportes" />);
    expect(screen.queryByLabelText("Meta")).toBeNull();
    await act(async () => {
      ligarFerramentas(document);
    });
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Quanto guardar por mês?"));
    });
    expect(screen.getByLabelText("Meta")).toBeTruthy();
    expect(screen.queryByLabelText("Aporte por mês")).toBeNull();
  });
});
