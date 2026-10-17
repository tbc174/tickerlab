// @vitest-environment jsdom
// O esqueleto de carregamento e o estado vazio (ADR 0096): no lugar do texto "Calculando…", blocos cinza do
// tamanho do que vem; quando não há nada, uma frase com a ação.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Carregando } from "../../src/app/Carregando";
import { Vazio } from "../../src/app/Vazio";
import { abrirApp } from "./ajudantes";

const CSS = readFileSync(join(process.cwd(), "src", "app", "app.css"), "utf8");
const NUNCA = () => new Promise(() => {}) as never; // a API que não responde: a tela fica carregando

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("esqueleto de carregamento", () => {
  it("a tela espera a resposta com o esqueleto, sem o texto 'Calculando…' na página", async () => {
    abrirApp("/visao-geral", { rotas: NUNCA });
    const espera = await screen.findByRole("status", { name: "Calculando…" });
    expect(espera.getAttribute("aria-busy")).toBe("true");
    expect(espera.querySelector(".esqueleto")).not.toBeNull();
    expect(screen.queryByText("Calculando…")).toBeNull(); // o texto fica só no rótulo para o leitor de tela
  });

  it("tem três formatos: painel (4 blocos), gráfico (1 retângulo) e lista (3 linhas)", () => {
    const { container, rerender } = render(<Carregando tipo="painel" rotulo="a" />);
    expect(container.querySelectorAll(".esqueleto")).toHaveLength(4);
    rerender(<Carregando tipo="grafico" rotulo="a" />);
    expect(container.querySelectorAll(".esqueleto")).toHaveLength(1);
    expect(container.querySelector(".esqueleto-grafico")).not.toBeNull();
    rerender(<Carregando tipo="lista" rotulo="a" />);
    expect(container.querySelectorAll(".esqueleto")).toHaveLength(3);
  });

  it("o brilho para com 'reduzir movimento'", () => {
    const reduzido = CSS.slice(CSS.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduzido).toMatch(/\.esqueleto \{[^}]*animation: none;/);
  });

  it("as estratégias acompanhadas esperam com o esqueleto de lista", async () => {
    abrirApp("/", { rotas: NUNCA });
    const espera = await screen.findByRole("status", { name: /Conferindo as suas estratégias/ });
    expect(espera.querySelectorAll(".esqueleto")).toHaveLength(3);
    expect(screen.queryByText(/Conferindo as suas estratégias/)).toBeNull();
  });
});

describe("estado vazio", () => {
  it("mostra a frase e o link da ação", () => {
    render(
      <MemoryRouter>
        <Vazio frase="Nada por aqui ainda." acao={{ texto: "Rodar um backtest", para: "/backtest" }} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Nada por aqui ainda.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Rodar um backtest" }).getAttribute("href")).toBe("/backtest");
  });

  it("sem ação, só a frase", () => {
    render(
      <MemoryRouter>
        <Vazio frase="Nada por aqui ainda." />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link")).toBeNull();
  });
});
