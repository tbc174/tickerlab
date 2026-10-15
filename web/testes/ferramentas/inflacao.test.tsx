// @vitest-environment jsdom
// A correção pela inflação v2: no mesmo período, quanto o valor teria virado na poupança e no CDI,
// o gráfico das três linhas e em quantos anos a poupança perdeu para a inflação.
import { act, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { anosAbaixo, corrigir } from "../../src/ferramentas/contas/inflacao";
import type { DadosDoBc } from "../../src/ferramentas/dados";
import { formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

const ontem = new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
const serie = (ao_mes: (ano: number) => number): [string, number][] =>
  Array.from({ length: 11 * 12 }, (_, i) => {
    const ano = 2015 + Math.floor(i / 12);
    return [`${ano}-${String((i % 12) + 1).padStart(2, "0")}`, ao_mes(ano)];
  });
const IPCA = serie((ano) => (ano % 2 ? 0.005 : 0.004));
const POUPANCA = serie(() => 0.0045);
const CDI = serie(() => 0.008);
const DADOS: DadosDoBc = {
  gerado_em: `${ontem}T13:40:00-03:00`,
  fonte: "Banco Central do Brasil",
  ipca: { meses: IPCA, ultimo: "2025-12" },
  poupanca_mensal: { meses: POUPANCA, ultimo: "2025-12" },
  cdi_mensal: { meses: CDI, ultimo: "2025-12" },
};

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

async function abrir() {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(DADOS))));
  window.history.replaceState(null, "", "/calculadora-de-correcao-pela-inflacao.html");
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome="inflacao" />);
  await act(async () => {
    ligarFerramentas(document);
  });
  await screen.findByLabelText("Até: ano");
}

describe("correção pela inflação v2", () => {
  it("mostra quanto o valor teria virado na poupança e no CDI no mesmo período", async () => {
    await abrir();
    const texto = document.body.textContent ?? "";
    expect(texto).toContain(formatarReais(corrigir(100, "2015-12", "2025-12", POUPANCA).valor_corrigido));
    expect(texto).toContain(formatarReais(corrigir(100, "2015-12", "2025-12", CDI).valor_corrigido));
  });

  it("o gráfico tem as três linhas, cada uma terminando no seu número", async () => {
    await abrir();
    const pontas = [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));
    expect(pontas).toHaveLength(3);
    expect(pontas[0]).toBeCloseTo(corrigir(100, "2015-12", "2025-12", IPCA).valor_corrigido, 9);
  });

  it("diz em quantos anos a poupança perdeu para a inflação", async () => {
    await abrir();
    const [perdeu, comparados] = anosAbaixo(POUPANCA, IPCA, 2025, 10);
    expect(perdeu).toBeGreaterThan(0);
    expect(document.body.textContent).toContain(`a poupança perdeu para a inflação em ${perdeu} dos ${comparados}`);
  });
});
