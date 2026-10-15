// @vitest-environment jsdom
// Os gráficos das ferramentas: a ponta de cada curva é o último valor (o gráfico e o número do
// resultado não podem discordar), a área empilhada soma as camadas, o teclado move a mira, o leitor
// de tela ouve o começo e o fim, e as cores vêm só das variáveis da marca.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GraficoDeBarras, geometriaDasBarras } from "../../src/graficos/GraficoDeBarras";
import { faixas } from "../../src/graficos/GraficoDeHistograma";
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

  it("se o prazo encurta com a mira no fim, a dica não mostra NaN", async () => {
    const serie = (n: number) => [{ nome: "Valor", cor: SERIES[0], valores: aportado.slice(0, n) }];
    const { rerender } = render(
      <GraficoDoTempo titulo="Evolução" meses={meses} series={serie(13)} formatarValor={formatarReais} />,
    );
    await act(async () => {
      fireEvent.keyDown(screen.getByRole("img", { name: "Evolução" }), { key: "End" });
    });
    await act(async () => {
      rerender(<GraficoDoTempo titulo="Evolução" meses={meses.slice(0, 7)} series={serie(7)} formatarValor={formatarReais} />);
    });
    expect(document.body.textContent).not.toContain("NaN");
    expect(document.querySelector("svg")?.innerHTML).not.toContain("NaN");
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

describe("faixas do histograma", () => {
  it("divide do menor ao maior em faixas iguais e conta cada valor uma vez", () => {
    const f = faixas([0, 0.1, 0.25, 0.3, 0.3], 3);
    expect(f.map((x) => x.quantas)).toEqual([1, 1, 3]);
    expect(f[0].de).toBe(0);
    expect(f[2].ate).toBeCloseTo(0.3, 12);
  });

  it("todos iguais cabem numa faixa só", () => {
    expect(faixas([0.2, 0.2], 4).map((x) => x.quantas)).toEqual([2]);
  });
});

describe("geometria das barras", () => {
  it.each([
    [248, true],
    [290, false],
    [461, true],
    [1030, true],
  ])("com %i px (negativos: %s), as barras ficam com pelo menos 40 por cento da largura", (largura, negativos) => {
    const g = geometriaDasBarras(largura, negativos);
    expect(g.fim - g.inicio).toBeGreaterThanOrEqual(0.4 * largura);
  });

  it("em tela estreita, o nome vai para cima da barra", () => {
    expect(geometriaDasBarras(300, true).compacto).toBe(true);
    expect(geometriaDasBarras(700, true).compacto).toBe(false);
  });
});

describe("faixa de posição", () => {
  it("pior na esquerda, mediana no meio, melhor na direita e a sua no percentil dela", async () => {
    const { FaixaDePosicao } = await import("../../src/graficos/FaixaDePosicao");
    const { container } = render(
      <FaixaDePosicao
        titulo="Foi sorte?"
        pior={687}
        mediana={2097}
        melhor={691020}
        sua={1579}
        abaixoDaSua={0.258}
        formatarValor={formatarReais}
      />,
    );
    const x = (marca: string) => Number(container.querySelector(`[data-marca="${marca}"]`)?.getAttribute("data-posicao"));
    expect(x("pior")).toBe(0);
    expect(x("mediana")).toBe(0.5);
    expect(x("melhor")).toBe(1);
    expect(x("sua")).toBeCloseTo(0.258, 9);
    expect(container.textContent).toContain(formatarReais(691020));
    expect(container.querySelector("figcaption")?.textContent).toContain("26% das datas dariam menos");
  });
});
