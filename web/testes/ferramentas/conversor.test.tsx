// @vitest-environment jsdom
// O conversor v2: inverter de/para, a variação em 30 dias e em 12 meses e o gráfico de 12 meses da
// PTAX de venda da moeda escolhida (com a data e a fonte).
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { formatarNaMoeda, variacao } from "../../src/ferramentas/ConversorDeMoedas";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import type { DadosDoBc } from "../../src/ferramentas/dados";
import { formatarPorcentagem } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

const ontem = new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
const diasAntes = (n: number) => new Date(Date.now() - (n + 1) * 24 * 3600 * 1000).toISOString().slice(0, 10);
const HISTORICO: [string, number][] = [
  [diasAntes(366), 5.4],
  [diasAntes(60), 5.2],
  [diasAntes(31), 5.1],
  [diasAntes(15), 5.05],
  [ontem, 5.0],
];
const DADOS: DadosDoBc = {
  gerado_em: `${ontem}T13:40:00-03:00`,
  fonte: "Banco Central do Brasil",
  moedas: [
    { codigo: "EUR", nome: "Euro", compra: 5.6, venda: 5.6, data: ontem },
    { codigo: "USD", nome: "Dólar dos Estados Unidos", compra: 5.0, venda: 5.0, data: ontem, historico: HISTORICO },
  ],
};

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

async function abrir(busca = "") {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(DADOS))));
  window.history.replaceState(null, "", `/conversor-de-moedas.html${busca}`);
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome="moedas" />);
  await act(async () => {
    ligarFerramentas(document);
  });
  await screen.findByLabelText("De");
}

const resultado = () => document.querySelector("[data-resultado]")?.textContent;

describe("conversor v2", () => {
  it("a variação compara com a cotação de até N dias antes do último dia", () => {
    const ultimo = new Date(`${ontem}T12:00:00`);
    const ha30 = new Date(ultimo.getTime() - 30 * 24 * 3600 * 1000).toISOString().slice(0, 10);
    const historico: [string, number][] = [["2025-01-02", 4], [ha30, 5], [ontem, 5.5]];
    expect(variacao(historico, 30)).toBeCloseTo(0.1, 12);
    expect(variacao(historico, 365)).toBeCloseTo(0.375, 12);
    expect(variacao([[ontem, 5]], 30)).toBeNull();
  });

  it("inverter troca de e para", async () => {
    await abrir();
    expect(resultado()).toBe(formatarNaMoeda(500, "BRL"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Inverter de e para" }));
    });
    expect((screen.getByLabelText("De") as HTMLSelectElement).value).toBe("BRL");
    expect(resultado()).toBe(formatarNaMoeda(20, "USD"));
  });

  it("mostra a variação em 12 meses e o gráfico que termina na cotação de hoje", async () => {
    await abrir();
    expect(document.body.textContent).toContain(`Em 12 meses: ${formatarPorcentagem(5.0 / 5.4 - 1)}`);
    const pontas = [...document.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));
    expect(pontas).toEqual([5.0]);
  });

  it("moeda sem histórico não tem gráfico, e o resto funciona", async () => {
    await abrir("?de=EUR");
    expect(document.querySelector("[data-fim]")).toBeNull();
    expect(resultado()).toBe(formatarNaMoeda(560, "BRL"));
  });
});
