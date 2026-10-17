// @vitest-environment jsdom
// O Início do app novo é o Workspace (ADR 0062; Workspace, PR 2): o cartão "Estratégias acompanhadas"
// com o veredito da ficha refeito pelo Pulse, a janela que o F5 não encolhe e a lista de telas embaixo.
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";

const JANELA = {
  inicio: "2026-10-02T23:00:00Z",
  fim: "2026-10-09T23:00:00Z",
  primeira_vez: true,
  texto: "Primeira visita: o que aconteceu nos últimos 7 dias.",
};
const MUDOU = {
  id: "11111111-1111-1111-1111-111111111111",
  nome: "Médias 10/40 na Petrobras",
  ticker: "PETR4.SA",
  antes: "passou",
  agora: "não passou",
  mudou: true,
  conferido_em: "2026-10-09T23:00:00Z",
  tese_ligada: "Sua tese sobre PETR4 em 08/10/2026: “Dividendos <b>altos</b>”",
  endereco: "/backtest?ticker=PETR4.SA&periodo=2y",
};
const IGUAL = {
  ...MUDOU,
  id: "22222222-2222-2222-2222-222222222222",
  nome: "Vale no app atual",
  ticker: "VALE3.SA",
  antes: "passou",
  agora: "passou",
  mudou: false,
  tese_ligada: "Sua tese sobre VALE3 em 01/10/2026: “Minério”",
  endereco: null,
};
const SEM_CONFERIR = {
  ...IGUAL,
  id: "33333333-3333-3333-3333-333333333333",
  nome: "Sem dados hoje",
  agora: null,
  conferido_em: null,
  tese_ligada: null,
};
const PULSE = {
  janela: JANELA,
  estrategias: [MUDOU, IGUAL, SEM_CONFERIR],
  limites: { sem_ficha: 1, alem_do_maximo: 0, nao_conferidas: 1 },
  avisos: ["Não deu para conferir agora: Sem dados hoje."],
  sem_estrategias: "Salve um backtest para acompanhar: o Pulse refaz a ficha com os preços de hoje.",
  notas: ["O Pulse mostra o que mudou, não o que fazer: nada aqui é recomendação de investimento."],
};

function abrir(resposta: Response | (() => Response) = () => respostaJson(200, PULSE)) {
  return abrirApp("/", {
    rotas: (endereco) =>
      endereco.startsWith("/api/v1/pulse") ? (typeof resposta === "function" ? resposta() : resposta) : undefined,
  });
}

const cartao = () => screen.findByRole("region", { name: "Estratégias acompanhadas" }, { timeout: 5000 });
const pedidosDoPulse = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.map(([e]) => String(e)).filter((e) => e.startsWith("/api/v1/pulse"));

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("o Início é o Workspace", () => {
  it("pede o Pulse uma vez e mostra o texto da janela", async () => {
    const { buscar } = abrir();
    const c = await cartao();
    expect(await within(c).findByText(JANELA.texto)).toBeTruthy();
    expect(pedidosDoPulse(buscar)).toEqual(["/api/v1/pulse"]);
  });

  it("guarda o início da janela na aba e o reenvia no F5", async () => {
    abrir();
    await within(await cartao()).findByText(JANELA.texto);
    cleanup();
    vi.unstubAllGlobals();
    const { buscar } = abrir(); // o F5: a mesma aba (o sessionStorage continua)
    await within(await cartao()).findByText(JANELA.texto);
    const [pedido] = pedidosDoPulse(buscar);
    expect(new URL(pedido, "http://app").searchParams.get("desde")).toBe(JANELA.inicio);
  });

  it("o que mudou vem primeiro, com o selo de antes e agora, a data, a tese e o backtest", async () => {
    abrir();
    const c = await cartao();
    const lista = await within(c).findByRole("list", { name: "Estratégias" });
    const [mudou, igual, semConferir] = within(lista).getAllByRole("listitem");
    expect(within(mudou).getByText(MUDOU.nome)).toBeTruthy();
    expect(within(mudou).getByText("passou → não passou · 09/10")).toBeTruthy();
    // o texto da tese é da pessoa: aparece como texto, sem virar HTML
    expect(within(mudou).getByText(MUDOU.tese_ligada)).toBeTruthy();
    expect(within(mudou).getByRole("link", { name: /Abrir o backtest/ }).getAttribute("href")).toBe(MUDOU.endereco);
    expect(within(igual).getByText(IGUAL.nome)).toBeTruthy();
    expect(within(igual).getByText(/sem mudança/)).toBeTruthy();
    expect(within(igual).queryByText(IGUAL.tese_ligada)).toBeNull(); // a tese só junto do que mudou
    expect(within(igual).getByRole("link", { name: /app atual/ }).getAttribute("href")).toBe(
      "https://app.tickerlab.com.br/simulacoes",
    );
    expect(within(semConferir).getByText(/Não deu para conferir agora/)).toBeTruthy();
    expect(within(c).getByText(PULSE.avisos[0])).toBeTruthy();
    expect(within(c).getByText(PULSE.notas[0])).toBeTruthy();
  });

  it("sem estratégias salvas, a frase da API e o caminho para o backtest", async () => {
    abrir(() => respostaJson(200, { ...PULSE, estrategias: [], avisos: [] }));
    const c = await cartao();
    expect(await within(c).findByText(PULSE.sem_estrategias)).toBeTruthy();
    expect(within(c).getByRole("link", { name: "Rodar um backtest" }).getAttribute("href")).toBe("/backtest");
  });

  it("a lista de telas continua embaixo do cartão, e o Pulse não aparece nela", async () => {
    abrir();
    const c = await cartao();
    const telas = await screen.findByRole("list", { name: "Telas novas" });
    expect(c.compareDocumentPosition(telas) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(telas).getByRole("link", { name: "Visão geral" })).toBeTruthy();
    expect(within(telas).queryByRole("link", { name: "Pulse" })).toBeNull();
  });

  it("se o Pulse falha, o cartão mostra o erro e as telas continuam", async () => {
    abrir(() => respostaJson(503, { detail: "fora do ar" }));
    const c = await cartao();
    expect(await within(c).findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Telas novas" })).toBeTruthy();
  });
});
