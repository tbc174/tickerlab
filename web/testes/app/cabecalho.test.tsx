// @vitest-environment jsdom
// O cabeçalho padrão de toda tela com formulário (ADR 0096): o olho, o título e a descrição da página,
// com um lugar à direita para as ações (o botão do relatório entra no PR 3 da série).
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CabecalhoDaTela } from "../../src/app/CabecalhoDaTela";
import { paginasDoApp } from "../../src/conteudo";
import { abrirApp } from "./ajudantes";

const RISCO = paginasDoApp.find((p) => p.url === "risco")!;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("cabeçalho da tela", () => {
  it("a tela de Risco abre com o olho da área (Ativo), o título como h1 e a descrição da página", async () => {
    abrirApp("/risco", { rotas: () => new Promise(() => {}) as never });
    const cabecalho = (await screen.findByRole("heading", { level: 1, name: "Risco" })).closest("header");
    expect(cabecalho?.classList.contains("cabecalho-da-tela")).toBe(true);
    expect(within(cabecalho as HTMLElement).getByText("Ativo").classList.contains("olho")).toBe(true);
    expect(within(cabecalho as HTMLElement).getByText(RISCO.descricao)).toBeTruthy();
  });

  it("as ações ficam à direita do título", () => {
    render(<CabecalhoDaTela pagina={RISCO} acoes={<button type="button">Relatório</button>} />);
    const acoes = screen.getByRole("button", { name: "Relatório" }).closest(".cabecalho-acoes");
    expect(acoes).not.toBeNull();
    expect(acoes?.parentElement?.classList.contains("cabecalho-da-tela")).toBe(true);
  });

  it("sem ações, não sobra a caixa vazia", () => {
    render(<CabecalhoDaTela pagina={RISCO} />);
    expect(document.querySelector(".cabecalho-acoes")).toBeNull();
  });
});
