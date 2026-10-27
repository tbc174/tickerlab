// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BuscaDaBase } from "../../src/site/BuscaDaBase";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const resposta = {
  cnpj: "02429144000193", empresa: "CPFL Energia", medido_em: "2026-10-26",
  destaques: ["Fundos", "Ofertas", "Setor"].map(titulo => ({ titulo, texto: `Dado de ${titulo}`, fonte: "CVM (ODbL)", data: "2025" })),
  aviso: "Nada aqui é recomendação de investimento.",
};
function pedir() {
  fireEvent.change(screen.getByLabelText("CNPJ, nome ou ticker"), { target: { value: "02.429.144/0001-93" } });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
}
it("busca sem cookie e mostra três destaques, data e caminho para o app", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => resposta });
  vi.stubGlobal("fetch", fetch);
  render(<BuscaDaBase />); pedir();
  expect(await screen.findByText("Dado de Fundos")).toBeTruthy();
  expect(screen.getByText("Dado de Ofertas")).toBeTruthy();
  expect(screen.getByText("Dado de Setor")).toBeTruthy();
  expect(screen.getByText(/26\/10\/2026/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Relatório completo no app" }).getAttribute("href")).toBe("https://app.tickerlab.com.br/busca-por-cnpj");
  expect(fetch.mock.calls[0][1].credentials).toBe("omit");
});
it("API fora preserva a ficha estática e permite tentar de novo", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<BuscaDaBase />); pedir();
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("indisponível"));
  expect(screen.getByRole("link", { name: /CPFL/ }).getAttribute("href")).toBe("/relatorio-de-exemplo.html");
  await waitFor(() => expect(screen.getByRole("button", { name: "Buscar" })).toHaveProperty("disabled", false));
});
it("sem ficha mostra a explicação e mantém a lista", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: { mensagem: "Esta empresa ainda não está na base aberta." } }) }));
  render(<BuscaDaBase />); pedir();
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("base aberta"));
  expect(screen.getByRole("link", { name: /CPFL/ })).toBeTruthy();
});
it("limite de pedidos é explicado", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 429, json: async () => ({ detail: "Muitos pedidos: espere um minuto." }) }));
  render(<BuscaDaBase />); pedir();
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("espere um minuto"));
});
