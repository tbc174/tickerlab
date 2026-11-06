// @vitest-environment jsdom
// Boas-vindas ao beta (linha 211): o roteiro dos 10 minutos, com um link para cada página do app.
import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";

const BOAS_VINDAS = {
  titulo: "Boas-vindas ao beta do TickerLab",
  texto_de_boas_vindas: "Você foi convidado para usar o TickerLab antes do lançamento.",
  sobre_o_beta: "O beta é grátis e pode mudar. Nada aqui é recomendação de investimento.",
  como_responder: "Responda ao e-mail do convite.",
  total_de_minutos: 10,
  roteiro: [
    { ordem: 1, minutos: 3, titulo: "Relatório do setor", o_que_fazer: "Escolha um setor.", url: "relatorio-do-setor" },
    { ordem: 2, minutos: 4, titulo: "Relatório de uma empresa", o_que_fazer: "Abra uma empresa.", url: "relatorio-empresa" },
  ],
};

afterEach(cleanup);

describe("boas-vindas do beta", () => {
  it("mostra o roteiro com um link para cada página e o aviso do beta", async () => {
    abrirApp("/boas-vindas-beta", {
      rotas: (endereco) => (endereco === "/api/v1/beta/boas-vindas" ? respostaJson(200, BOAS_VINDAS) : undefined),
    });
    expect(await screen.findByRole("heading", { name: "Boas-vindas ao beta do TickerLab" }, { timeout: 5000 })).toBeTruthy();
    const lista = await screen.findByRole("list", { name: "Roteiro do beta" });
    const links = lista.querySelectorAll("a");
    expect(links[0].getAttribute("href")).toBe("/relatorio-do-setor");
    expect(links[1].getAttribute("href")).toBe("/relatorio-empresa");
    expect(screen.getAllByText(/Nada aqui é recomendação de investimento/).length).toBeGreaterThan(0);
  });
});
