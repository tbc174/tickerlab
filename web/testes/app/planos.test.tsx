// @vitest-environment jsdom
// Planos e assinatura no app novo (conta e planos, PR 3): o plano da conta, quanto já usou, a tabela
// dos planos (a mesma do Streamlit, src/planos.py) e o caminho para assinar, que ainda é no app atual.
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { planos } from "../../src/conteudo";
import { abrirApp, respostaJson } from "./ajudantes";

const MEU_PLANO = {
  plano: "gratuito",
  nome_do_plano: "Gratuito",
  simulacoes: "1 de 5",
  favoritos: "2 de 3",
  frase_da_assinatura: null,
  aviso: "Pagamento em modo de teste do Stripe: nenhum dinheiro real é cobrado.",
  tabela: planos.tabela,
};

function abrir(resposta: unknown = MEU_PLANO) {
  return abrirApp("/planos", {
    rotas: (endereco) => (endereco === "/api/v1/meu-plano" ? respostaJson(200, resposta) : undefined),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("planos", () => {
  it("o plano da conta e quanto já usou", async () => {
    abrir();
    const uso = await screen.findByRole("region", { name: "Seu plano" });
    for (const [rotulo, valor] of [
      ["Seu plano", "Gratuito"],
      ["Simulações salvas", "1 de 5"],
      ["Favoritos", "2 de 3"],
    ]) {
      const numero = within(uso).getByText(rotulo, { exact: true }).closest(".numero-do-painel");
      expect(within(numero as HTMLElement).getByText(valor), rotulo).toBeTruthy();
    }
  });

  it("a tabela dos planos, uma coluna por plano", async () => {
    abrir();
    const tabela = await screen.findByRole("table", { name: "O que cada plano inclui" });
    expect(within(tabela).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Recurso",
      ...planos.nomes,
    ]);
    expect(within(tabela).getAllByRole("row")).toHaveLength(planos.tabela.length + 1);
    expect(within(tabela).getByText("Simulações salvas")).toBeTruthy();
  });

  it("assinar e gerenciar ainda são no app atual", async () => {
    abrir();
    const link = await screen.findByRole("link", { name: /Assinar ou gerenciar a assinatura/ });
    expect(link.getAttribute("href")).toBe("https://app.tickerlab.com.br/planos");
    expect(screen.getByText(MEU_PLANO.aviso)).toBeTruthy();
  });

  it("com assinatura, diz quando renova", async () => {
    abrir({ ...MEU_PLANO, plano: "pro", nome_do_plano: "Pro", frase_da_assinatura: "Sua assinatura renova em 14/11/2026." });
    expect(await screen.findByText("Sua assinatura renova em 14/11/2026.")).toBeTruthy();
  });

  it("o motivo de uma página fora do plano leva aos planos do app novo", async () => {
    abrirApp("/risco", {
      rotas: (endereco) =>
        endereco.startsWith("/api/v1/risco")
          ? respostaJson(403, { detail: "Faz parte do plano Pro." }, { "X-TickerLab-Motivo": "plano" })
          : undefined,
    });
    const link = await screen.findByRole("link", { name: "Conhecer os planos" });
    expect(link.getAttribute("href")).toBe("/planos");
  });
});
