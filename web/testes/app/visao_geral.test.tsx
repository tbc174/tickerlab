// @vitest-environment jsdom
// A visão geral em React mostra os mesmos números da visão geral do Streamlit. O exemplo vem do
// Python (tests/test_app_novo_mesmos_numeros.py): a resposta da API para os dados de exemplo e o que
// a tela do Streamlit mostra com eles (rótulo → valor).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";
import exemplo from "./exemplos/visao_geral.json";

function abrirVisaoGeral(caminho = "/visao-geral", resposta = () => respostaJson(200, exemplo.resposta)) {
  return abrirApp(caminho, {
    rotas: (endereco) => (endereco.startsWith("/api/v1/visao-geral") ? resposta() : undefined),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("visão geral", () => {
  it("mostra cada número da tela do Streamlit com o mesmo valor", async () => {
    abrirVisaoGeral();
    const painel = await screen.findByRole("region", { name: "Painel de números" });
    for (const [rotulo, valor] of Object.entries(exemplo.na_tela)) {
      const numero = within(painel).getByText(rotulo, { exact: true }).closest(".numero-do-painel");
      expect(numero, rotulo).not.toBeNull();
      expect(within(numero as HTMLElement).getByText(valor, { exact: true }), rotulo).toBeTruthy();
    }
  });

  it("pede a rota do contrato com os padrões (sem taxa = o CDI do período)", async () => {
    const { buscar } = abrirVisaoGeral();
    await screen.findByRole("region", { name: "Painel de números" });
    const pedido = buscar.mock.calls.find(([e]) => String(e).startsWith("/api/v1/visao-geral"));
    expect(pedido?.[0]).toBe("/api/v1/visao-geral?ticker=PETR4.SA&periodo=2y&confianca_do_var=95");
  });

  it("o ativo e o período vêm do endereço, como no app atual", async () => {
    const { buscar } = abrirVisaoGeral("/visao-geral?ticker=VALE3.SA&periodo=1y");
    await screen.findByRole("region", { name: "Painel de números" });
    const enderecos = buscar.mock.calls.map(([e]) => String(e));
    expect(enderecos).toContain("/api/v1/visao-geral?ticker=VALE3.SA&periodo=1y&confianca_do_var=95");
  });

  it("taxa digitada em % ao ano vai para a API como fração", async () => {
    const { buscar } = abrirVisaoGeral();
    await screen.findByRole("region", { name: "Painel de números" });
    fireEvent.change(screen.getByLabelText(/Taxa livre de risco/), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    await waitFor(() =>
      expect(buscar.mock.calls.map(([e]) => String(e))).toContain(
        "/api/v1/visao-geral?ticker=PETR4.SA&periodo=2y&taxa=0.1&confianca_do_var=95",
      ),
    );
  });

  it("mostra o aviso dos dados de exemplo, a frase do CVaR e a curva em base 100", async () => {
    abrirVisaoGeral();
    expect(await screen.findByText(exemplo.resposta.ativo.aviso_da_origem)).toBeTruthy();
    expect(screen.getByText(/Perda média nos piores dias \(CVaR 95%\): -3,65%/)).toBeTruthy();
    const grafico = screen.getByRole("img", { name: /PETR4\.SA em base 100/ });
    expect(grafico.querySelector("path.grafico-linha")).not.toBeNull();
  });

  it("o ? de cada número mostra o texto do glossário", async () => {
    abrirVisaoGeral();
    await screen.findByRole("region", { name: "Painel de números" });
    expect(screen.getAllByText("O que é").length).toBeGreaterThan(0);
  });

  it("ativo sem dados: a mensagem da API, sem quebrar a tela", async () => {
    abrirVisaoGeral("/visao-geral?ticker=XXXX9", () =>
      respostaJson(404, { detail: "Não encontrei dados para XXXX9.SA." }),
    );
    expect(await screen.findByText("Não encontrei dados para XXXX9.SA.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Painel de números" })).toBeNull();
  });
});
