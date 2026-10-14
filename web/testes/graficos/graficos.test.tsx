// @vitest-environment jsdom
// Os gráficos das ferramentas: a ponta de cada curva é o último valor (o gráfico e o número do
// resultado não podem discordar), a área empilhada soma as camadas, o teclado move a mira, o leitor
// de tela ouve o começo e o fim, e as cores vêm só das variáveis da marca.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GraficoDeBarras } from "../../src/graficos/GraficoDeBarras";
import { GraficoDoTempo, empilhar } from "../../src/graficos/GraficoDoTempo";
import { SERIES } from "../../src/graficos/cores";
import { formatarReais, formatarReaisCurto } from "../../src/ferramentas/numeros";

afterEach(() => {
  document.body.innerHTML = "";
});

const meses = Array.from({ length: 13 }, (_, i) => i);
const aportado = meses.map((m) => 1000 + 100 * m);
const juros = meses.map((m) => 10 * m * m);

function cores(svg: Element): string[] {
  return [...svg.querySelectorAll("*")].flatMap((el) =>
    ["stroke", "fill"].map((a) => el.getAttribute(a)).filter((v): v is string => v !== null),
  );
}

describe("gráfico do tempo", () => {
  it("empilhar soma as camadas ponto a ponto", () => {
    expect(empilhar([[1, 2], [3, 4], [0.5, 0.5]])).toEqual([[1, 2], [4, 6], [4.5, 6.5]]);
  });

  it("na área empilhada, a ponta de cima é a soma do último ponto", () => {
    const { container } = render(
      <GraficoDoTempo
        titulo="Evolução"
        meses={meses}
        series={[
          { nome: "Você pôs", cor: SERIES[1], valores: aportado },
          { nome: "Juros", cor: SERIES[0], valores: juros },
        ]}
        empilhado
        formatarValor={formatarReais}
      />,
    );
    const pontas = [...container.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));
    expect(pontas).toEqual([aportado[12], aportado[12] + juros[12]]);
  });

  it("nas linhas, a ponta de cada série é o último valor dela", () => {
    const { container } = render(
      <GraficoDoTempo
        titulo="Cenários"
        meses={meses}
        series={[
          { nome: "A", cor: SERIES[0], valores: aportado },
          { nome: "B", cor: SERIES[1], valores: juros },
        ]}
        formatarValor={formatarReais}
      />,
    );
    const pontas = [...container.querySelectorAll("[data-fim]")].map((el) => Number(el.getAttribute("data-fim")));
    expect(pontas).toEqual([aportado[12], juros[12]]);
  });

  it("as setas do teclado movem a mira e a dica mostra o mês e os valores", async () => {
    render(
      <GraficoDoTempo
        titulo="Evolução"
        meses={meses}
        series={[{ nome: "Valor", cor: SERIES[0], valores: aportado }]}
        formatarValor={formatarReais}
      />,
    );
    const grafico = screen.getByRole("img", { name: "Evolução" });
    await act(async () => {
      fireEvent.keyDown(grafico, { key: "ArrowLeft" });
    });
    const dica = screen.getByRole("status");
    expect(dica.textContent).toContain("mês 11");
    expect(dica.textContent).toContain(formatarReais(aportado[11]));
    await act(async () => {
      fireEvent.keyDown(grafico, { key: "Home" });
    });
    expect(screen.getByRole("status").textContent).toContain("início");
  });

  it("o leitor de tela ouve o começo e o fim de cada série", () => {
    render(
      <GraficoDoTempo
        titulo="Evolução"
        meses={meses}
        series={[
          { nome: "A", cor: SERIES[0], valores: aportado },
          { nome: "B", cor: SERIES[1], valores: juros },
        ]}
        formatarValor={formatarReais}
      />,
    );
    const resumo = document.querySelector("figcaption")?.textContent ?? "";
    expect(resumo).toContain(`A: começa em ${formatarReais(aportado[0])} e termina em ${formatarReais(aportado[12])}`);
    expect(resumo).toContain(`B: começa em ${formatarReais(0)} e termina em ${formatarReais(juros[12])}`);
  });

  it("legenda só com duas ou mais séries", () => {
    const um = render(
      <GraficoDoTempo titulo="Um" meses={meses} series={[{ nome: "A", cor: SERIES[0], valores: aportado }]} formatarValor={formatarReais} />,
    );
    expect(um.container.querySelector(".grafico-ferramenta-legenda")).toBeNull();
    um.unmount();
    const dois = render(
      <GraficoDoTempo
        titulo="Dois"
        meses={meses}
        series={[
          { nome: "A", cor: SERIES[0], valores: aportado },
          { nome: "B", cor: SERIES[1], valores: juros },
        ]}
        formatarValor={formatarReais}
      />,
    );
    expect(dois.container.querySelector(".grafico-ferramenta-legenda")?.textContent).toContain("B");
  });

  it("só usa as cores da marca", () => {
    const { container } = render(
      <GraficoDoTempo
        titulo="Evolução"
        meses={meses}
        series={[
          { nome: "A", cor: SERIES[1], valores: aportado },
          { nome: "B", cor: SERIES[0], valores: juros },
        ]}
        empilhado
        formatarValor={formatarReais}
      />,
    );
    for (const cor of cores(container.querySelector("svg")!)) {
      expect(cor === "none" || cor.startsWith("var(--")).toBe(true);
    }
  });
});

describe("gráfico de barras", () => {
  it("barra negativa cresce para a esquerda do zero e a positiva para a direita", () => {
    const { container } = render(
      <GraficoDeBarras
        titulo="Comparação"
        barras={[
          { nome: "Ganha", valor: 10 },
          { nome: "Perde", valor: -5 },
        ]}
        formatarValor={formatarReais}
      />,
    );
    const zero = Number(container.querySelector("[data-zero]")?.getAttribute("x1"));
    const [ganha, perde] = [...container.querySelectorAll("[data-barra]")];
    expect(Number(ganha.getAttribute("x"))).toBeGreaterThanOrEqual(zero);
    expect(Number(perde.getAttribute("x")) + Number(perde.getAttribute("width"))).toBeLessThanOrEqual(zero + 0.01);
    expect(container.textContent).toContain(formatarReais(-5));
    for (const cor of cores(container.querySelector("svg")!)) {
      expect(cor === "none" || cor.startsWith("var(--")).toBe(true);
    }
  });
});

describe("reais no eixo", () => {
  it("encurta mil e milhão", () => {
    expect(formatarReaisCurto(0)).toBe("R$ 0");
    expect(formatarReaisCurto(800)).toBe("R$ 800");
    expect(formatarReaisCurto(30000)).toBe("R$ 30 mil");
    expect(formatarReaisCurto(2500)).toBe("R$ 2,5 mil");
    expect(formatarReaisCurto(1500000)).toBe("R$ 1,5 mi");
    expect(formatarReaisCurto(-20000)).toBe("−R$ 20 mil");
  });
});
