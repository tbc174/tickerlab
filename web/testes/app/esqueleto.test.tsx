// @vitest-environment jsdom
// O esqueleto do app em React (série 3 da ADR 0048): rotas, moldura e a API ligada ou não.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { navegador } from "../../src/app/navegador";
import { ENDERECOS_SO_DO_CLASSICO, TELAS_DO_APP, temTelaPronta } from "../../src/app/rotas";
import { EmConstrucao } from "../../src/app/telas/EmConstrucao";
import { paginasDoApp } from "../../src/conteudo";
import { abrirApp, respostaJson } from "./ajudantes";

function abrir(caminho: string, resposta?: Response) {
  return abrirApp(caminho, resposta ? { configuracao: resposta } : {}).buscar;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
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

describe("link antigo de página que ainda só existe na versão clássica (o Streamlit em /classico)", () => {
  // quem abre app.tickerlab.com.br/research cai no app novo, que é o principal agora, e tem que
  // chegar à mesma página em /classico, com os mesmos parâmetros, sem entrar no app novo antes
  function abrirLinkAntigo(caminho: string, opcoes: Parameters<typeof abrirApp>[1] = {}) {
    const trocar = vi.spyOn(navegador, "trocar").mockImplementation(() => undefined);
    abrirApp(caminho, opcoes);
    return trocar;
  }

  it("vai para a mesma página em /classico, com os parâmetros, e deixa o link à vista", async () => {
    const trocar = abrirLinkAntigo("/research?ticker=VALE3");
    const link = await screen.findByRole("link", { name: /Abrir na versão clássica/ });
    expect(link.getAttribute("href")).toBe("/classico/research?ticker=VALE3");
    expect(trocar).toHaveBeenCalledWith("/classico/research?ticker=VALE3");
  });

  it("a administração também (o catálogo dela fica fora do bundle; só o endereço entra)", async () => {
    const trocar = abrirLinkAntigo("/admin");
    await screen.findByRole("link", { name: /Abrir na versão clássica/ });
    expect(trocar).toHaveBeenCalledWith("/classico/admin");
  });

  it("sem a API ligada e sem login: mesmo assim (o link antigo não depende do app novo)", async () => {
    const trocar = abrirLinkAntigo("/carteira-b3/", {
      configuracao: respostaJson(404, { detail: "Not Found" }),
      entraSozinho: false,
    });
    await screen.findByRole("link", { name: /Abrir na versão clássica/ });
    expect(trocar).toHaveBeenCalledWith("/classico/carteira-b3");
    expect(screen.queryByText(/em preparação/)).toBeNull();
  });

  it("/inicio (a página inicial da versão clássica) é a página inicial do app novo", async () => {
    const trocar = abrirLinkAntigo("/inicio");
    await screen.findByRole("navigation", { name: "Telas" });
    expect(trocar).not.toHaveBeenCalled();
  });

  it("página com tela em React abre nela, não na versão clássica", async () => {
    const trocar = abrirLinkAntigo("/visao-geral");
    await screen.findByRole("navigation", { name: "Telas" });
    expect(trocar).not.toHaveBeenCalled();
  });

  it("endereço que não é de página nenhuma não vai para a versão clássica", async () => {
    const trocar = abrirLinkAntigo("/nao-existe");
    expect(await screen.findByText(/Página não encontrada/)).toBeTruthy();
    expect(trocar).not.toHaveBeenCalled();
  });

  it("toda página do app tem destino: tela em React, a inicial ou a versão clássica", () => {
    const comTela = new Set(TELAS_DO_APP.map((p) => p.url));
    const semDestino = paginasDoApp
      .map((p) => p.url)
      .filter((url) => url !== "inicio" && !comTela.has(url) && !ENDERECOS_SO_DO_CLASSICO.includes(url));
    expect(semDestino).toEqual([]);
    expect(ENDERECOS_SO_DO_CLASSICO).toContain("research");
    expect(ENDERECOS_SO_DO_CLASSICO).toContain("admin");
    expect(ENDERECOS_SO_DO_CLASSICO).not.toContain("visao-geral");
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
