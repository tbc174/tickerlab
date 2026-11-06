// @vitest-environment jsdom
// O formulário em caixa (ADR 0096): os campos do dia a dia à vista, o resto recolhido em "Opções avançadas",
// rótulo acima do campo e, quando a tela já mostra o ativo e o período em outro lugar, a prop `ocultar`.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Formulario, valoresIniciais } from "../../src/app/Formulario";
import { paginasDoApp } from "../../src/conteudo";

const entradasDe = (url: string) => paginasDoApp.find((p) => p.url === url)!.contrato!.entradas;
const BACKTEST = entradasDe("backtest");

function abrir(url: string, busca = "", ocultar?: string[]) {
  const entradas = entradasDe(url);
  const aoAnalisar = vi.fn();
  render(
    <Formulario
      entradas={entradas}
      valores={valoresIniciais(entradas, new URLSearchParams(busca))}
      aoAnalisar={aoAnalisar}
      ocultar={ocultar}
    />,
  );
  return aoAnalisar;
}

afterEach(cleanup);

describe("formulário em caixa", () => {
  it("o ativo, o período e a estratégia ficam à vista; o resto, em 'Opções avançadas' fechadas", () => {
    abrir("backtest");
    const avancadas = document.querySelector("details.opcoes-avancadas") as HTMLDetailsElement;
    expect(avancadas.open).toBe(false);
    expect(within(avancadas).getByText("Opções avançadas").tagName).toBe("SUMMARY");
    for (const campo of ["Custo por operação (%)", "Taxa livre de risco (% ao ano)", "Capital inicial (R$)"]) {
      expect(within(avancadas).getByLabelText(campo), campo).toBeTruthy();
    }
    for (const campo of ["Ativo", "Período", "Estratégia"]) {
      expect(screen.getByLabelText(campo).closest("details"), campo).toBeNull();
    }
  });

  it("o rótulo fica acima do campo: o label contém o texto e o campo", () => {
    abrir("visao-geral");
    const rotulo = screen.getByLabelText("Ativo").closest("label")!;
    expect(rotulo.firstElementChild?.tagName).toBe("SPAN");
    expect(rotulo.querySelector("input")).not.toBeNull();
  });

  it("tela sem campo avançado não ganha a caixa recolhida", () => {
    abrir("linha-do-tempo");
    expect(document.querySelector("details.opcoes-avancadas")).toBeNull();
  });

  it("a comparação deixa os ativos à vista (são o assunto da tela)", () => {
    abrir("comparar");
    expect(screen.getByText("Comparar com").closest("details")).toBeNull();
  });

  it("valor diferente do padrão no endereço abre as opções avançadas (nada fica escondido ligado)", () => {
    abrir("backtest", "custo_por_operacao=0.002");
    expect((document.querySelector("details.opcoes-avancadas") as HTMLDetailsElement).open).toBe(true);
  });

  it("ocultar tira o campo da tela, mas o valor continua indo no envio", () => {
    const aoAnalisar = abrir("visao-geral", "ticker=VALE3.SA&periodo=1y", ["ticker", "periodo"]);
    expect(screen.queryByLabelText("Ativo")).toBeNull();
    expect(screen.queryByLabelText("Período")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    expect(aoAnalisar).toHaveBeenCalledWith(expect.objectContaining({ ticker: "VALE3.SA", periodo: "1y" }));
  });

  it("o contrato do backtest continua com os campos de antes", () => {
    expect(BACKTEST.map((e) => e.nome)).toContain("custo_por_operacao");
  });
});
