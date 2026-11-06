// @vitest-environment jsdom
// A página pública do link compartilhado (onda 4): abre sem login, com o código depois do "#".
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";

const CODIGO = "Ab0_-" + "x".repeat(38); // 43 caracteres, como os do servidor
const NAO_VALE = "Este link não existe ou não vale mais.";
const AVISO = "Vale para os dados do passado. Não é promessa de resultado nem recomendação.";

const FICHA = {
  tipo: "ficha",
  titulo: "Foi sorte? Cruzamento de médias em PETR4",
  criado_em: "2026-10-13T23:30:00Z",
  expira_em: "2026-11-12T23:30:00Z",
  pdf: null,
  aviso: AVISO,
  ficha: {
    ticker: "PETR4.SA",
    codigo: "PETR4",
    estrategia: "Cruzamento de médias",
    parametros: { curta: 20, longa: 50, tipo: "Simples" },
    protecoes: { stop_loss: 0.1 },
    custo_por_operacao: 0.001,
    inicio: "2024-01-02",
    fim: "2025-12-30",
    checagens: [
      { pergunta: "Funcionou fora do período usado para escolher?", situacao: "passou", explicacao: "Rendeu 8,0% fora." },
      { pergunta: "Sobrevive aos custos e ao imposto?", situacao: "não passou", explicacao: "Perdeu para o CDI." },
    ],
    tentativas: 37,
    resultado: "não passou",
    titulo_do_veredito: "Não passou no teste contra a sorte",
    texto_do_veredito: `Uma checagem não passou. ${AVISO}`,
    texto_das_tentativas: "Você testou 3 configurações em PETR4.",
    fonte: "Yahoo Finance",
    calculada_em: "2026-10-13T23:30:00Z",
  },
};

const PDF = {
  tipo: "pdf",
  titulo: "Petrobras em 2026",
  criado_em: "2026-10-13T23:30:00Z",
  expira_em: "2026-11-12T23:30:00Z",
  ficha: null,
  aviso: AVISO,
  pdf: {
    nome_do_arquivo: "TickerLab-Petrobras-em-2026.pdf",
    tamanho: 204_800,
    sha256: "a".repeat(64),
    gerado_em: "2026-10-12T15:00:00Z",
  },
};

function rotasCom(resposta: () => Response) {
  return (endereco: string) =>
    endereco.startsWith("/api/v1/compartilhados/") ? resposta() : undefined;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("link compartilhado", () => {
  it("abre a ficha sem login, mandando o código no corpo e nunca no endereço", async () => {
    const { buscar, google } = abrirApp(`/c#${CODIGO}`, {
      rotas: rotasCom(() => respostaJson(200, FICHA)),
      entraSozinho: false,
    });
    expect(await screen.findByRole("heading", { name: FICHA.titulo })).toBeTruthy();
    const chamada = buscar.mock.calls.find(([endereco]) => endereco.includes("compartilhados"));
    expect(chamada?.[0]).toBe("/api/v1/compartilhados/abrir");
    expect(chamada?.[1]).toEqual({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: CODIGO }),
    });
    for (const [endereco] of buscar.mock.calls) expect(String(endereco)).not.toContain(CODIGO);
    expect(google.id.prompt).not.toHaveBeenCalled();
    expect(screen.queryByText(/Entrar no TickerLab/)).toBeNull();
  });

  it("mostra o veredito, as checagens, a data do cálculo, a fonte e o aviso", async () => {
    abrirApp(`/c#${CODIGO}`, { rotas: rotasCom(() => respostaJson(200, FICHA)) });
    expect(await screen.findByText("Não passou no teste contra a sorte")).toBeTruthy();
    expect(screen.getByText("Funcionou fora do período usado para escolher?")).toBeTruthy();
    expect(screen.getByText("Perdeu para o CDI.")).toBeTruthy();
    expect(screen.getByText(/Calculada em 13\/10\/2026/)).toBeTruthy();
    expect(screen.getByText("Yahoo Finance")).toBeTruthy();
    expect(screen.getByText(/02\/01\/2024 a 30\/12\/2025/)).toBeTruthy();
    expect(screen.getByText("Você testou 3 configurações em PETR4.")).toBeTruthy();
    expect(screen.getAllByText(new RegExp(AVISO.slice(0, 30))).length).toBeGreaterThan(0);
  });

  it("mostra o código da tela do ativo, sem o ^ do Yahoo (ADR 0065)", async () => {
    const doIbovespa = { ...FICHA, ficha: { ...FICHA.ficha, ticker: "^BVSP", codigo: "IBOV" } };
    abrirApp(`/c#${CODIGO}`, { rotas: rotasCom(() => respostaJson(200, doIbovespa)) });
    const ativo = (await screen.findByText("Ativo")).nextElementSibling;
    expect(ativo?.textContent).toBe("IBOV");
    expect(screen.queryByText("^BVSP")).toBeNull();
  });

  it("sem código ou com código inválido, avisa sem chamar a API", async () => {
    for (const caminho of ["/c", "/c#curto", `/c#${CODIGO}/`]) {
      const { buscar } = abrirApp(caminho);
      expect(await screen.findByText(NAO_VALE)).toBeTruthy();
      expect(buscar.mock.calls.some(([e]) => String(e).includes("compartilhados"))).toBe(false);
      cleanup();
    }
  });

  it("link vencido ou revogado mostra a mesma mensagem", async () => {
    abrirApp(`/c#${CODIGO}`, { rotas: rotasCom(() => respostaJson(404, { detail: NAO_VALE })) });
    expect(await screen.findByText(NAO_VALE)).toBeTruthy();
  });

  it("abre mesmo sem o login configurado neste servidor", async () => {
    abrirApp(`/c#${CODIGO}`, {
      configuracao: respostaJson(200, { google_client_id: null }),
      rotas: rotasCom(() => respostaJson(200, FICHA)),
    });
    expect(await screen.findByRole("heading", { name: FICHA.titulo })).toBeTruthy();
  });

  it("PDF: mostra tamanho e hash e baixa por POST", async () => {
    const criarUrl = vi.fn(() => "blob:teste");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: criarUrl, revokeObjectURL: vi.fn() }));
    const { buscar } = abrirApp(`/c#${CODIGO}`, {
      rotas: (endereco) => {
        if (endereco === "/api/v1/compartilhados/abrir") return respostaJson(200, PDF);
        if (endereco === "/api/v1/compartilhados/pdf")
          return new Response(new Blob(["%PDF"]), { headers: { "content-type": "application/pdf" } });
        return undefined;
      },
    });
    expect(await screen.findByRole("heading", { name: "Petrobras em 2026" })).toBeTruthy();
    expect(screen.getByText(/200 KB/)).toBeTruthy();
    expect(screen.getByText("a".repeat(64))).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Baixar o PDF" }));
    await waitFor(() => expect(criarUrl).toHaveBeenCalled());
    const pedido = buscar.mock.calls.find(([e]) => e === "/api/v1/compartilhados/pdf");
    expect(pedido?.[1]).toMatchObject({ method: "POST", body: JSON.stringify({ codigo: CODIGO }) });
  });

  it("convida a conhecer o TickerLab sem passar o endereço adiante", async () => {
    abrirApp(`/c#${CODIGO}`, { rotas: rotasCom(() => respostaJson(200, FICHA)) });
    const convite = await screen.findByRole("link", { name: /Conheça o TickerLab/ });
    expect(convite.getAttribute("href")).toBe("https://tickerlab.com.br");
    expect(convite.getAttribute("rel")).toContain("noreferrer");
  });
});
