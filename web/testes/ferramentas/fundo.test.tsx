// @vitest-environment jsdom
// Fundo ou CDB: o fundo vira "um CDB de X% do CDI" (a conta é conferida no golden.test.ts), a tabela
// com as taxas e o come-cotas, e o gráfico do que cada um daria se resgatasse no fim de cada mês.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EXEMPLO_DO_FUNDO, calcularFundo, curvas } from "../../src/ferramentas/FundosERendaFixa";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import type { DadosDoBc } from "../../src/ferramentas/dados";
import { formatarPorcentagem, formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

const ontem = new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
const CDI = 0.1365;
const DADOS: DadosDoBc = {
  gerado_em: `${ontem}T13:40:00-03:00`,
  fonte: "Banco Central do Brasil",
  cdi: { ao_ano: CDI, data: ontem },
};
const MES = new Date().getMonth() + 1;

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

async function abrir(busca = "") {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(DADOS))));
  window.history.replaceState(null, "", `/fundo-ou-cdb.html${busca}`);
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome="fundo" />);
  await act(async () => {
    ligarFerramentas(document);
  });
  await screen.findAllByText(/come-cotas/i);
}

function conta(campos = EXEMPLO_DO_FUNDO) {
  const r = calcularFundo(campos, CDI, MES);
  if (typeof r === "string") throw new Error(r);
  return r;
}

describe("fundo ou CDB", () => {
  it("com 1% de administração, o fundo de 100% do CDI equivale a um CDB de menos de 100%", async () => {
    await abrir();
    const r = conta();
    expect(r.equivalente).toBeLessThan(1);
    expect(r.fundo.liquido).toBeLessThan(r.cdb.liquido);
    expect(document.querySelector("[data-resultado]")?.textContent).toBe(
      `um CDB de ${formatarPorcentagem(r.equivalente!, 1)} do CDI`,
    );
    expect(document.body.textContent).toContain(formatarReais(r.cdb.liquido - r.fundo.liquido));
  });

  it("o gráfico termina no líquido de cada um no fim do prazo", async () => {
    await abrir();
    const r = conta();
    const pontas = [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));
    expect(pontas[0]).toBeCloseTo(r.fundo.liquido, 6);
    expect(pontas[1]).toBeCloseTo(r.cdb.liquido, 6);
    expect(curvas(EXEMPLO_DO_FUNDO, CDI, MES).fundo).toHaveLength(r.meses + 1);
  });

  it("a taxa de performance só aparece quando o fundo passa do CDI e vai para o endereço", async () => {
    await abrir("?fundo=120&performance=20");
    expect(new URLSearchParams(window.location.search).get("performance")).toBe("20");
    const r = conta({ ...EXEMPLO_DO_FUNDO, fundo: "120", performance: "20" });
    expect(r.fundo.taxa_de_performance).toBeGreaterThan(0);
    expect(document.body.textContent).toContain(formatarReais(r.fundo.taxa_de_performance));
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Rende"), { target: { value: "100" } });
    });
    expect(conta({ ...EXEMPLO_DO_FUNDO, performance: "20" }).fundo.taxa_de_performance).toBe(0);
  });

  it("o prazo vai até 10 anos, o máximo do CDB da comparação", () => {
    expect(typeof calcularFundo({ ...EXEMPLO_DO_FUNDO, anos: "10" }, CDI, MES)).toBe("object");
    expect(calcularFundo({ ...EXEMPLO_DO_FUNDO, anos: "11" }, CDI, MES)).toBe("O prazo vai até 10 anos.");
  });

  it("os rótulos do tipo de fundo mostram a alíquota do come-cotas", async () => {
    await abrir();
    expect(screen.getByLabelText("Longo prazo (15%)")).toBeTruthy();
    expect(screen.getByLabelText("Curto prazo (20%)")).toBeTruthy();
  });
});
