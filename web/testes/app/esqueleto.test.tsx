// @vitest-environment jsdom
// O esqueleto do app em React (série 3 da ADR 0048): rotas, moldura e a API ligada ou não.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TELAS_DO_APP, temTelaPronta } from "../../src/app/rotas";
import { EmConstrucao } from "../../src/app/telas/EmConstrucao";
import { paginasDoApp } from "../../src/conteudo";
import { abrirApp, respostaJson } from "./ajudantes";

function abrir(caminho: string, resposta?: Response) {
  return abrirApp(caminho, resposta ? { configuracao: resposta } : {}).buscar;
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
    // o <main> do aviso "Carregando" é trocado quando a configuração chega: pegar o de depois
    await screen.findByRole("navigation", { name: "Telas" });
    const principal = screen.getByRole("main");
    expect(await within(principal).findByRole("link", { name: "Visão geral" })).toBeTruthy();
  });

  it("endereço desconhecido mostra que a página não existe", async () => {
    abrir("/nao-existe");
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
  });

  it("toda página com contrato já tem a tela em React", () => {
    expect(TELAS_DO_APP.filter((p) => !temTelaPronta(p.chave)).map((p) => p.chave)).toEqual([]);
  });

  it("página com contrato e sem tela nova leva à mesma página na versão clássica", () => {
    const pagina = { ...TELAS_DO_APP[0], titulo: "Tela futura", url: "tela-futura" };
    render(<EmConstrucao pagina={pagina} />);
    const link = screen.getByRole("link", { name: /Abrir na versão clássica/ });
    expect(link.getAttribute("href")).toBe("/classico/tela-futura");
  });
});

describe("a API de leitura", () => {
  it("a configuração é pedida sem token, no próprio endereço", async () => {
    const buscar = abrir("/");
    await screen.findByRole("navigation", { name: "Telas" });
    expect(buscar).toHaveBeenNthCalledWith(1, "/api/v1/configuracao");
  });

  it("ligada mas sem o client ID do Google: avisa que o login ainda não foi ligado", async () => {
    abrir("/", respostaJson(200, { google_client_id: null }));
    expect(await screen.findByText(/login da versão nova ainda não foi ligado/)).toBeTruthy();
  });

  it("desligada: o app novo avisa que está em preparação e leva à versão clássica", async () => {
    abrir("/", respostaJson(404, { detail: "Not Found" }));
    expect(await screen.findByText(/em preparação/)).toBeTruthy();
    const link = screen.getByRole("link", { name: /versão clássica/ });
    expect(link.getAttribute("href")).toBe("/classico/");
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
