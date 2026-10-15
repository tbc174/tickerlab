// @vitest-environment jsdom
// A página "Quanto daria? Foi sorte?": chama a rota pública do app (só números soltos, ADR 0070), mostra
// o valor de hoje em cada ativo, a régua de posição do ativo escolhido e a frase da sorte; só busca
// ao ligar e ao apertar "Calcular" (o limite por IP); com a API fora, diz que está indisponível.
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ENDERECO_DA_PONTE } from "../../src/ferramentas/QuantoDaria";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { formatarReais } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

const janelas = (pior: number, mediana: number, melhor: number, abaixo: number) => ({
  quantas: 300,
  pior,
  mediana,
  melhor,
  abaixo_da_sua: abaixo,
});
const ativo = (id: string, nome: string, final: number, j: ReturnType<typeof janelas> | null) => ({
  ativo: id,
  nome,
  fonte: `Fonte de ${nome}`,
  inicio: "2020-01-01",
  fim: "2026-10-01",
  valor_final: final,
  retorno: final / 1000 - 1,
  valor_real: final / 1.45,
  janelas: j,
});
const RESPOSTA = {
  desde: "2020-01-01",
  valor: 1000,
  ativos: [
    ativo("cdi", "CDI", 1909.6, janelas(1640, 2012, 6128, 0.309)),
    ativo("poupanca", "Poupança", 1507.92, janelas(1399, 1591, 3304, 0.248)),
    ativo("parado", "Parado (só a inflação)", 1000, null),
    ativo("ibovespa", "Ibovespa", 1578.76, janelas(687, 2097, 9020, 0.258)),
  ],
  indisponiveis: [{ nome: "Bitcoin", motivo: "Fonte fora do ar agora." }],
  aviso: "Simulação com dados do passado: não é recomendação de investimento.",
  calculado_em: "2026-10-15",
};

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

async function abrir(resposta: () => Promise<Response>, busca = "") {
  const buscar = vi.fn((_endereco: string) => resposta());
  vi.stubGlobal("fetch", buscar);
  window.history.replaceState(null, "", `/quanto-daria.html${busca}`);
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome="quantoDaria" />);
  await act(async () => {
    ligarFerramentas(document);
  });
  return buscar;
}

const ok = async () => new Response(JSON.stringify(RESPOSTA));

describe("quanto daria? foi sorte?", () => {
  it("o HTML pronto tem o formulário, e ao ligar busca uma vez a rota pública com o mês e o valor", async () => {
    expect(renderToStaticMarkup(<Ilha nome="quantoDaria" />)).toContain("Calcular");
    const buscar = await abrir(ok, "?mes=01&ano=2020&valor=1000");
    expect(buscar).toHaveBeenCalledTimes(1);
    expect(buscar.mock.calls[0][0]).toBe(`${ENDERECO_DA_PONTE}?desde=2020-01-01&valor=1000`);
  });

  it("mostra quanto daria em cada ativo e o que ficou de fora", async () => {
    await abrir(ok);
    await screen.findAllByText(/dariam menos/);
    const nomes = [...document.querySelectorAll(".grafico-ferramenta-nome")].map((el) => el.textContent);
    expect(nomes).toEqual(["CDI", "Poupança", "Parado (só a inflação)", "Ibovespa"]);
    expect(document.body.textContent).toContain(formatarReais(1909.6));
    expect(document.body.textContent).toContain("Bitcoin");
  });

  it("a frase da sorte é do ativo escolhido, e trocar o ativo não busca de novo", async () => {
    const buscar = await abrir(ok, "?ativo=ibovespa");
    await screen.findAllByText(/dariam menos/);
    expect(document.body.textContent).toContain("Entre as 300 datas de início com o mesmo prazo, 26% das outras dariam menos que a sua");
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Foi sorte? Ver o"), { target: { value: "cdi" } });
    });
    expect(document.body.textContent).toContain("31% das outras dariam menos que a sua");
    expect(buscar).toHaveBeenCalledTimes(1);
  });

  it("calcular de novo busca com o ano novo", async () => {
    const buscar = await abrir(ok);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Ano"), { target: { value: "2018" } });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Calcular" }));
    });
    expect(buscar).toHaveBeenCalledTimes(2);
    expect(String(buscar.mock.calls[1][0])).toContain("desde=2018-");
  });

  it("muitos pedidos e API fora dizem isso, sem quebrar", async () => {
    await abrir(async () => new Response(JSON.stringify({ detail: "Muitos pedidos: espere um minuto." }), { status: 429 }));
    expect(await screen.findByText(/espere um minuto/)).toBeTruthy();
    await abrir(async () => {
      throw new Error("sem rede");
    });
    expect(await screen.findByText(/indisponível agora/)).toBeTruthy();
  });
});
