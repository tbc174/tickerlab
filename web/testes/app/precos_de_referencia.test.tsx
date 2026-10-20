// @vitest-environment jsdom
// Preços de referência no app novo, com a resposta de exemplo gerada pelo Python
// (tests/test_app_novo_mesmos_numeros.py).
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";
import precos from "./exemplos/precos_de_referencia.json";

const ROTA = "/api/v1/precos-de-referencia";

function abrir(resposta = () => respostaJson(200, precos.resposta)) {
  return abrirApp("/precos-de-referencia", {
    rotas: (endereco) => (endereco.startsWith(ROTA) ? resposta() : undefined),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("preços de referência", () => {
  it("mostra cada preço como o Streamlit, com a variação e a fonte", async () => {
    abrir();
    for (const [rotulo, valor] of Object.entries(precos.na_tela)) {
      const item = await screen.findByRole("region", { name: rotulo });
      expect(within(item).getByText(valor, { exact: true }), rotulo).toBeTruthy();
    }
    for (const item of precos.resposta.itens) {
      const regiao = screen.getByRole("region", { name: `${item.nome} (${item.unidade})` });
      expect(within(regiao).getByText(item.legenda)).toBeTruthy();
      if (item.texto_da_variacao) expect(within(regiao).getByText(item.texto_da_variacao)).toBeTruthy();
    }
  });

  it("o aviso do preço diário no topo e a atribuição das fontes no fim", async () => {
    abrir();
    expect((await screen.findByRole("note")).textContent).toBe(precos.resposta.aviso_diario);
    expect(screen.getByText(precos.resposta.atribuicao)).toBeTruthy();
  });

  it("café com duas linhas (Banco Mundial e FMI); fertilizante com uma e a nota das fontes", async () => {
    abrir();
    const arabica = await screen.findByRole("img", { name: /^Café arábica \(US\$\/kg\), média mensal/ });
    expect(arabica.querySelectorAll("path.grafico-linha")).toHaveLength(2);
    const ureia = screen.getByRole("img", { name: /^Ureia \(US\$\/kg\), média mensal/ });
    expect(ureia.querySelectorAll("path.grafico-linha")).toHaveLength(1);
    const regiao = screen.getByRole("region", { name: "Ureia (US$/kg)" });
    expect(within(regiao).getByText(/os indicadores do Banco Mundial e do FMI diferem/)).toBeTruthy();
  });

  it("o spread arábica menos robusta, com a explicação", async () => {
    abrir();
    const spread = await screen.findByRole("region", { name: precos.resposta.titulo_do_spread });
    expect(within(spread).getByText(precos.resposta.nota_do_spread)).toBeTruthy();
    expect(spread.querySelectorAll("path.grafico-linha")).toHaveLength(1);
  });

  it("preços ainda não coletados: a mensagem da API", async () => {
    abrir(() => respostaJson(503, { detail: "Os preços de referência ainda não foram coletados neste servidor." }));
    expect(await screen.findByText(/ainda não foram coletados/)).toBeTruthy();
  });
});
