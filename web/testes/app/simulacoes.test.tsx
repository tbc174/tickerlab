// @vitest-environment jsdom
// Minhas simulações no app novo (Workspace, PR 1): a lista com o uso do plano, reabrir (no app novo ou
// no atual) e apagar com confirmação.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TOKEN, abrirApp, respostaJson } from "./ajudantes";

const DO_APP_NOVO = {
  id: "11111111-1111-1111-1111-111111111111",
  tipo: "backtest",
  nome: "Médias 10/40 na Petrobras",
  criada_em: "2026-10-17T21:40:00",
  dados_ate: "09/10/2026",
  numeros: { "Retorno total": "+12,0%", Operações: "7" },
  veredito: "passou",
  endereco: "/backtest?ticker=PETR4.SA&periodo=2y&estrategia=Cruzamento+de+m%C3%A9dias&p.curta=10",
};
const DO_APP_ATUAL = {
  id: "22222222-2222-2222-2222-222222222222",
  tipo: "carteira",
  nome: "Carteira defensiva",
  criada_em: "2026-10-10T10:00:00",
  dados_ate: null,
  numeros: {},
  veredito: null,
  endereco: null,
};
const LISTA = {
  simulacoes: [DO_APP_NOVO, DO_APP_ATUAL],
  usadas: 2,
  limite: 5,
  uso: "2 de 5",
  sem_simulacoes: "Você ainda não guardou nenhuma simulação. Rode um backtest e clique em Salvar.",
};

function abrir(lista = LISTA) {
  return abrirApp("/simulacoes", {
    rotas: (endereco, pedido) => {
      if (endereco === "/api/v1/simulacoes") return respostaJson(200, lista);
      if (endereco === "/api/v1/apagar-simulacao") {
        const { id } = JSON.parse(String(pedido?.body));
        const restantes = lista.simulacoes.filter((s) => s.id !== id);
        return respostaJson(200, { ...lista, simulacoes: restantes, usadas: restantes.length, uso: `${restantes.length} de 5` });
      }
      return undefined;
    },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("minhas simulações", () => {
  it("lista as simulações com o uso do plano, os números e o veredito guardado", async () => {
    abrir();
    const lista = await screen.findByRole("list", { name: "Minhas simulações" });
    expect(screen.getByText("Simulações guardadas: 2 de 5.")).toBeTruthy();
    const [nova, antiga] = within(lista).getAllByRole("listitem");
    expect(within(nova).getByText(DO_APP_NOVO.nome)).toBeTruthy();
    expect(within(nova).getByText("Retorno total: +12,0% · Operações: 7")).toBeTruthy();
    expect(within(nova).getByText(/Backtest · criada em 17\/10\/2026 · dados até 09\/10\/2026 · Foi sorte\? passou/)).toBeTruthy();
    expect(within(antiga).getByText(/^Carteira · criada em 10\/10\/2026$/)).toBeTruthy();
  });

  it("reabre no app novo pelo endereço da API; a da versão clássica só reabre lá", async () => {
    abrir();
    const lista = await screen.findByRole("list", { name: "Minhas simulações" });
    const [nova, antiga] = within(lista).getAllByRole("listitem");
    expect(within(nova).getByRole("link", { name: "Reabrir" }).getAttribute("href")).toBe(DO_APP_NOVO.endereco);
    expect(within(antiga).getByRole("link", { name: "Reabrir na versão clássica" }).getAttribute("href")).toBe(
      "/classico/simulacoes",
    );
  });

  it("apagar pede confirmação, manda o id com o token e atualiza a lista", async () => {
    const { buscar } = abrir();
    const lista = await screen.findByRole("list", { name: "Minhas simulações" });
    const [nova] = within(lista).getAllByRole("listitem");
    fireEvent.click(within(nova).getByRole("button", { name: "Apagar" }));
    expect(buscar.mock.calls.some(([e]) => e === "/api/v1/apagar-simulacao")).toBe(false);
    fireEvent.click(within(nova).getByRole("button", { name: "Apagar mesmo" }));
    await waitFor(() => expect(screen.getByText("Simulações guardadas: 1 de 5.")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText(DO_APP_NOVO.nome)).toBeNull();
    const pedido = buscar.mock.calls.find(([e]) => e === "/api/v1/apagar-simulacao");
    expect(JSON.parse(String(pedido?.[1]?.body))).toEqual({ id: DO_APP_NOVO.id });
    expect(pedido?.[1]?.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` });
  });

  it("cancelar a confirmação não apaga nada", async () => {
    const { buscar } = abrir();
    const lista = await screen.findByRole("list", { name: "Minhas simulações" });
    const [nova] = within(lista).getAllByRole("listitem");
    fireEvent.click(within(nova).getByRole("button", { name: "Apagar" }));
    fireEvent.click(within(nova).getByRole("button", { name: "Cancelar" }));
    expect(within(nova).getByRole("button", { name: "Apagar" })).toBeTruthy();
    expect(buscar.mock.calls.some(([e]) => e === "/api/v1/apagar-simulacao")).toBe(false);
  });

  it("sem simulações, a frase da API e o caminho para o backtest", async () => {
    abrir({ ...LISTA, simulacoes: [], usadas: 0, uso: "0 de 5" });
    expect(await screen.findByText(LISTA.sem_simulacoes)).toBeTruthy();
    expect(screen.getByText("Simulações guardadas: 0 de 5.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "backtest" }).getAttribute("href")).toBe("/backtest");
  });
});
