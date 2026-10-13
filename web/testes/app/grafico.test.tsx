// @vitest-environment jsdom
// O gráfico de linha do app novo: escala, referência, mira pelo teclado e a dica com o valor.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GraficoDeLinha, limitesDoEixo } from "../../src/app/graficos/GraficoDeLinha";

const DATAS = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"];

function desenhar() {
  render(
    <GraficoDeLinha
      titulo="PETR4.SA em base 100"
      datas={DATAS}
      series={[{ nome: "PETR4.SA", cor: "var(--azul)", valores: [100, 104.5, null, 98.25] }]}
      referencia={100}
    />,
  );
  return screen.getByRole("img", { name: "PETR4.SA em base 100" });
}

afterEach(cleanup);

describe("gráfico de linha", () => {
  it("o eixo cobre os valores e a referência, com passos redondos", () => {
    expect(limitesDoEixo([98.25, 104.5], 100)).toEqual([98, 106, 2]);
    expect(limitesDoEixo([80, 190], 100)).toEqual([50, 200, 50]);
  });

  it("um buraco na série quebra a linha em vez de ligar os pontos", () => {
    const grafico = desenhar();
    const d = grafico.querySelector("path.grafico-linha")?.getAttribute("d") ?? "";
    expect(d.match(/M/g)).toHaveLength(2);
    expect(grafico.querySelector("line.grafico-referencia")).not.toBeNull();
  });

  it("as setas do teclado andam pelos dias e a dica mostra a data e o valor", () => {
    const grafico = desenhar();
    fireEvent.keyDown(grafico, { key: "Home" });
    expect(screen.getByRole("status").textContent).toContain("02/01/2026");
    expect(screen.getByRole("status").textContent).toContain("PETR4.SA: 100");
    fireEvent.keyDown(grafico, { key: "ArrowRight" });
    expect(screen.getByRole("status").textContent).toContain("PETR4.SA: 104,5");
    fireEvent.keyDown(grafico, { key: "ArrowRight" });
    expect(screen.getByRole("status").textContent).toContain("PETR4.SA: —");
  });

  it("o resumo em texto diz o período e onde a curva termina", () => {
    desenhar();
    expect(screen.getByText(/de 02\/01\/2026 a 07\/01\/2026, termina em 98,3/)).toBeTruthy();
  });
});
