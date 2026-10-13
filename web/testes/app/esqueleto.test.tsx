// @vitest-environment jsdom
// O esqueleto do app em React (série 3 da ADR 0048): rotas, moldura e a API ligada ou não.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/app/App";
import { TELAS_DO_APP } from "../../src/app/rotas";
import { paginasDoApp } from "../../src/conteudo";

function respostaJson(status: number, corpo: unknown): Response {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function abrir(caminho: string, resposta = respostaJson(200, { google_client_id: "id-de-teste" })) {
  const buscar = vi.fn(async () => resposta);
  vi.stubGlobal("fetch", buscar);
  render(
    <MemoryRouter initialEntries={[caminho]}>
      <App />
    </MemoryRouter>,
  );
  return buscar;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("rotas do app novo", () => {
  it("são as páginas que têm contrato na API, com o mesmo endereço do app atual", () => {
    const comContrato = paginasDoApp.filter((p) => p.contrato !== null).map((p) => p.url);
    expect(TELAS_DO_APP.map((p) => p.url)).toEqual(comContrato);
    expect(comContrato).toContain("visao-geral");
    expect(TELAS_DO_APP.every((p) => !p.e_pro && !p.somente_admin)).toBe(true);
  });

  it("a página inicial lista as telas novas", async () => {
    abrir("/");
    const principal = await screen.findByRole("main");
    expect(await within(principal).findByRole("link", { name: "Visão geral" })).toBeTruthy();
  });

  it("endereço desconhecido mostra que a página não existe", async () => {
    abrir("/nao-existe");
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
  });

  it("tela ainda sem versão nova leva à mesma página no app atual", async () => {
    abrir("/visao-geral");
    const link = await screen.findByRole("link", { name: /Abrir no app atual/ });
    expect(link.getAttribute("href")).toBe("https://app.tickerlab.com.br/visao-geral");
  });
});

describe("a API de leitura", () => {
  it("é consultada sem token, só no próprio endereço", async () => {
    const buscar = abrir("/");
    await screen.findByRole("navigation", { name: "Telas" });
    expect(buscar).toHaveBeenCalledWith("/api/v1/configuracao");
  });

  it("desligada: o app novo avisa que está em preparação e leva ao app atual", async () => {
    abrir("/", respostaJson(404, { detail: "Not Found" }));
    expect(await screen.findByText(/em preparação/)).toBeTruthy();
    const link = screen.getByRole("link", { name: /app atual/ });
    expect(link.getAttribute("href")).toBe("https://app.tickerlab.com.br/");
  });

  it("sem a rota da API no endereço (resposta que não é JSON) conta como desligada", async () => {
    abrir("/", new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } }));
    expect(await screen.findByText(/em preparação/)).toBeTruthy();
  });
});

describe("segurança das telas", () => {
  it("nenhuma tela põe HTML pronto na página (só o símbolo da marca, que vem do Python)", () => {
    const pasta = join(process.cwd(), "src", "app");
    const arquivos = readdirSync(pasta, { recursive: true, encoding: "utf8" }).filter((a) =>
      /\.tsx?$/.test(a),
    );
    const comHtml = arquivos.filter((a) =>
      readFileSync(join(pasta, a), "utf8").includes("dangerouslySetInnerHTML"),
    );
    expect(comHtml.map((a) => a.replaceAll("\\", "/"))).toEqual(["Logo.tsx"]);
  });
});
