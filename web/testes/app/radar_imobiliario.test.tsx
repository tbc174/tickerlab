// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";

const resposta = {
  apurado_em: "2026-10-26", cidade: "SP", recorte: "todos",
  definicao: "DTIs no mês do pagamento.", tipo_regiao: "distrito",
  fonte: "https://prefeitura.sp.gov.br/", fonte_geografica: null,
  atribuicao: "Prefeitura de São Paulo. Agregação: TickerLab.", licenca: null,
  avisos: ["Distrito oficial não é bairro informado."],
  serie: [
    { cidade: "SP", recorte: "todos", mes: "2025-08", quantidade: 10, valor_medio: 100, localizadas: 0, variacao_anual_pct: null },
    { cidade: "SP", recorte: "todos", mes: "2026-08", quantidade: 15, valor_medio: 200, localizadas: 12, variacao_anual_pct: 50 },
  ],
  regioes: [{ cidade: "SP", recorte: "todos", mes: "2026-08", tipo: "distrito", nome: "CENTRO", quantidade: 12, valor_medio: 100 }],
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("abre pelo menu com fonte, cobertura e regiões; muda mês sem inventar cobertura", async () => {
  abrirApp("/radar-imobiliario", { rotas: (url) => url.startsWith("/api/v1/radar-imobiliario") ? respostaJson(200, resposta) : undefined });
  expect(await screen.findByText("Distrito oficial não é bairro informado.")).toBeTruthy();
  expect(screen.queryByText(/Os dados vêm do Yahoo/)).toBeNull();
  expect(screen.getByText(/12 de 15/)).toBeTruthy();
  const tabela = screen.getByRole("table", { name: /Distritos/ });
  expect(within(tabela).getByText("CENTRO")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Mês de referência"), { target: { value: "2025-08" } });
  expect(screen.getByText(/Sem recorte territorial neste mês/)).toBeTruthy();
  expect(screen.queryByText("CENTRO")).toBeNull();
});

it("sem pacote mostra o motivo sem exibir valores de exemplo", async () => {
  abrirApp("/radar-imobiliario", { rotas: (url) => url.startsWith("/api/v1/radar-imobiliario") ? respostaJson(503, { detail: "Radar aguardando dados." }) : undefined });
  expect(await screen.findByText("Radar aguardando dados.")).toBeTruthy();
  expect(screen.queryByText("CENTRO")).toBeNull();
});
