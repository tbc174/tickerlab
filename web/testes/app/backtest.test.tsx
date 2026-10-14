// @vitest-environment jsdom
// O backtest simples no app novo, com a resposta de exemplo do Python (a estratégia padrão da tela do
// Streamlit): os números têm de sair iguais, e o pedido vai por POST com os parâmetros da estratégia.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";
import exemplo from "./exemplos/backtest.json";

function abrir(caminho = "/backtest") {
  return abrirApp(caminho, {
    rotas: (endereco) => (endereco === "/api/v1/backtest" ? respostaJson(200, exemplo.resposta) : undefined),
  });
}

function corposDosPedidos(buscar: ReturnType<typeof abrirApp>["buscar"]) {
  return buscar.mock.calls
    .filter(([e]) => String(e) === "/api/v1/backtest")
    .map(([, pedido]) => {
      expect(pedido?.method).toBe("POST");
      return JSON.parse(String(pedido?.body));
    });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("backtest", () => {
  it("os números iguais aos do Streamlit e a curva de capital em base 100", async () => {
    abrir();
    const painel = await screen.findByRole("region", { name: "Resultado do backtest" });
    for (const [rotulo, valor] of Object.entries(exemplo.na_tela)) {
      const numero = within(painel).getByText(rotulo, { exact: true }).closest(".numero-do-painel");
      expect(numero, rotulo).not.toBeNull();
      expect(within(numero as HTMLElement).getByText(valor, { exact: true }), rotulo).toBeTruthy();
    }
    expect(within(painel).getByText("Operações")).toBeTruthy();
    expect(screen.getByRole("img", { name: /Curva de capital de .* em PETR4 \(base 100\)/ })).toBeTruthy();
  });

  it("o pedido padrão vai por POST, com a estratégia e o custo do contrato", async () => {
    const { buscar } = abrir();
    await screen.findByRole("region", { name: "Resultado do backtest" });
    expect(corposDosPedidos(buscar)[0]).toEqual({
      ticker: "PETR4.SA",
      periodo: "2y",
      estrategia: "Comprar e segurar",
      parametros: {},
      custo_por_operacao: 0.0005,
      capital_inicial: 10000,
    });
  });

  it("escolher uma estratégia mostra os parâmetros dela, e o pedido leva os números", async () => {
    const { buscar } = abrir();
    await screen.findByRole("region", { name: "Resultado do backtest" });
    fireEvent.change(screen.getByLabelText("Estratégia"), { target: { value: "Cruzamento de médias" } });
    const ajustes = screen.getByRole("group", { name: "Ajustes da estratégia" });
    const curta = within(ajustes).getByLabelText("Média curta (dias)") as HTMLInputElement;
    expect(curta.value).toBe("20");
    expect(curta.min).toBe("5");
    expect(curta.max).toBe("100");
    fireEvent.change(curta, { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/Custo por operação/), { target: { value: "0,1" } });
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    await waitFor(() => {
      const ultimo = corposDosPedidos(buscar).at(-1);
      expect(ultimo).toEqual({
        ticker: "PETR4.SA",
        periodo: "2y",
        estrategia: "Cruzamento de médias",
        parametros: { curta: 10, longa: 50, tipo: "Simples" },
        custo_por_operacao: 0.001,
        capital_inicial: 10000,
      });
    });
  });

  it("a estratégia e os parâmetros ficam no endereço", async () => {
    const { buscar } = abrir("/backtest?estrategia=Filtro+de+tend%C3%AAncia&p.janela=100");
    await screen.findByRole("region", { name: "Resultado do backtest" });
    expect(corposDosPedidos(buscar)[0]).toMatchObject({
      estrategia: "Filtro de tendência",
      parametros: { janela: 100 },
    });
  });

  it("a ficha: tolerância em % (fração na API), capital em R$ e os parâmetros que variam", async () => {
    const { buscar } = abrir();
    await screen.findByRole("region", { name: "Resultado do backtest" });
    expect(screen.queryByRole("group", { name: /Parâmetros que variam/ })).toBeNull(); // sem números
    fireEvent.change(screen.getByLabelText("Estratégia"), { target: { value: "Cruzamento de médias" } });
    const grupo = screen.getByRole("group", { name: /Parâmetros que variam/ });
    const curta = within(grupo).getByLabelText("Média curta (dias)") as HTMLInputElement;
    const longa = within(grupo).getByLabelText("Média longa (dias)") as HTMLInputElement;
    expect(curta.checked && longa.checked).toBe(true); // os dois primeiros, como no Streamlit
    expect(within(grupo).queryByLabelText("Tipo de média")).toBeNull(); // opção não varia
    expect(longa.disabled).toBe(false);
    fireEvent.click(curta);
    expect(longa.disabled).toBe(true); // ao menos um fica marcado
    fireEvent.change(screen.getByLabelText(/Quanto de queda/), { target: { value: "40" } });
    fireEvent.change(screen.getByLabelText(/Capital inicial/), { target: { value: "50.000" } });
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    await waitFor(() => {
      expect(corposDosPedidos(buscar).at(-1)).toMatchObject({
        estrategia: "Cruzamento de médias",
        capital_inicial: 50000,
        tolerancia_de_queda: 0.4,
        livres: ["longa"],
      });
    });
  });

  it("os parâmetros que variam ficam no endereço e voltam ao padrão ao trocar de estratégia", async () => {
    const { buscar } = abrir("/backtest?estrategia=Cruzamento+de+m%C3%A9dias&livres=longa");
    await screen.findByRole("region", { name: "Resultado do backtest" });
    expect(corposDosPedidos(buscar)[0]).toMatchObject({ livres: ["longa"] });
    fireEvent.change(screen.getByLabelText("Estratégia"), { target: { value: "Filtro de tendência" } });
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    await waitFor(() => {
      const ultimo = corposDosPedidos(buscar).at(-1);
      expect(ultimo?.estrategia).toBe("Filtro de tendência");
      expect(ultimo).not.toHaveProperty("livres");
    });
  });
});
