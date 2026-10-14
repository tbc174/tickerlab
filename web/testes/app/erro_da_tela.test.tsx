// @vitest-environment jsdom
// Página fora do plano (ADR 0062): a tela mostra o motivo da API e o caminho para os planos.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErroDaApi } from "../../src/app/api";
import { ErroDaTela } from "../../src/app/telas/ErroDaTela";
import { abrirApp, respostaJson } from "./ajudantes";

const MOTIVO = "Pairs trading faz parte do plano Pro. Você está no plano Gratuito.";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("erro da tela", () => {
  it("fora do plano: o motivo e o link para os planos no app atual", () => {
    render(<ErroDaTela erro={new ErroDaApi("plano", MOTIVO)} />);
    expect(screen.getByRole("alert").textContent).toContain(MOTIVO);
    const link = screen.getByRole("link", { name: "Conhecer os planos" });
    expect(link.getAttribute("href")).toBe("https://app.tickerlab.com.br/planos");
  });

  it.each(["pedido-invalido", "nao-encontrado", "termos", "indisponivel"] as const)(
    "%s: só a mensagem, sem o link dos planos",
    (tipo) => {
      render(<ErroDaTela erro={new ErroDaApi(tipo, "Mensagem da API.")} />);
      expect(screen.getByRole("alert").textContent).toContain("Mensagem da API.");
      expect(screen.queryByRole("link", { name: "Conhecer os planos" })).toBeNull();
    },
  );

  it("o 403 de plano numa tela de verdade chega até a pessoa", async () => {
    abrirApp("/risco", {
      rotas: (endereco) =>
        endereco.startsWith("/api/v1/risco")
          ? respostaJson(403, { detail: MOTIVO }, { "X-TickerLab-Motivo": "plano" })
          : undefined,
    });
    expect(await screen.findByText(MOTIVO)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Conhecer os planos" })).toBeTruthy();
  });
});
