// @vitest-environment jsdom
// A moldura do app feita para o celular (ADR 0066; série site e app v2, PR 4): abas embaixo, toque de
// 44 px, campos de 16 px, fundo animado só no login e no início (ADR 0065 item 2) e tabelas que rolam
// por dentro. O jsdom não aplica media queries: o CSS é conferido como texto.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TELAS_DO_APP } from "../../src/app/rotas";
import { abrirApp, respostaJson } from "./ajudantes";
import juros from "./exemplos/juros_e_inflacao.json";
import linha from "./exemplos/linha_do_tempo.json";
import visao from "./exemplos/visao_geral.json";

const CSS_DO_APP = readFileSync(join(process.cwd(), "src", "app", "app.css"), "utf8");
const PAGINA_DO_APP = readFileSync(join(process.cwd(), "app", "index.html"), "utf8");
/** As regras do CSS do app que valem no celular (o bloco `@media (max-width: 760px)`). */
const NO_CELULAR = CSS_DO_APP.split("@media (max-width: 760px)").slice(1).join("");

const abas = () => screen.getByRole("navigation", { name: "Telas, atalhos" });
/** Espera o login terminar e a tela Início abrir (o login também tem um h1 e o fundo). O primeiro
 * teste do arquivo monta o app inteiro: com o PC ocupado passa de 1 s, a espera padrão. */
const noInicio = () =>
  screen.findByRole("heading", { name: "As telas novas do TickerLab" }, { timeout: 5000 });

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("abas embaixo no celular (por área, ADR 0096)", () => {
  const folha = () => document.querySelector<HTMLDialogElement>("dialog.folha-mais")!;

  it("Início, as três áreas e 'Mais': toda tela pronta fica a um ou dois toques", async () => {
    abrirApp("/");
    await noInicio();
    const nav = abas();
    const nomes = [...nav.querySelectorAll(":scope > :is(a, button)")].map((el) => el.textContent);
    expect(nomes).toEqual(["Início", "Ativo", "Estratégias", "Acompanhar", "Mais"]);
    expect(within(nav).getByRole("button", { name: "Mais" }).getAttribute("aria-haspopup")).toBe("dialog");
    // a folha fica fora da barra (a barra é fixa e borrada: um filho fixo dela ficaria preso nela)
    expect(nav.contains(folha())).toBe(false);
    const alcancaveis = [...nav.querySelectorAll("a"), ...folha().querySelectorAll("a")].map((a) =>
      a.getAttribute("href"),
    );
    // o Pulse é o próprio Início ("/")
    for (const pagina of TELAS_DO_APP.filter((p) => p.chave !== "pulse"))
      expect(alcancaveis, pagina.url).toContain(`/${pagina.url}`);
  });

  it("cada aba de área abre a primeira tela pronta dela", async () => {
    abrirApp("/");
    await noInicio();
    const destino = (nome: string) => within(abas()).getByRole("link", { name: nome }).getAttribute("href");
    expect(destino("Ativo")).toBe("/visao-geral");
    expect(destino("Estratégias")).toBe("/backtest");
    expect(destino("Acompanhar")).toBe("/juros-e-inflacao");
  });

  it("no início só a aba Início fica marcada", async () => {
    abrirApp("/");
    await noInicio();
    const atuais = abas().querySelectorAll("[aria-current]");
    expect([...atuais].map((a) => a.textContent)).toEqual(["Início"]);
  });

  it("numa tela da área Ativo, a aba Ativo fica marcada (mesmo não sendo a primeira tela dela)", async () => {
    abrirApp("/risco", { rotas: () => new Promise(() => {}) as never });
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const atuais = abas().querySelectorAll("[aria-current]");
    expect([...atuais].map((a) => a.textContent)).toEqual(["Ativo"]);
    expect(within(abas()).getByRole("link", { name: "Ativo" }).classList.contains("active")).toBe(true);
  });

  it("'Mais' abre a folha com as telas por área e a Conta; escolher uma tela fecha", async () => {
    abrirApp("/", {
      rotas: (endereco) =>
        endereco.startsWith("/api/v1/juros-e-inflacao") ? respostaJson(200, juros.resposta) : undefined,
    });
    await noInicio();
    const botao = within(abas()).getByRole("button", { name: "Mais" });
    expect(folha().open).toBe(false);
    fireEvent.click(botao);
    expect(folha().open).toBe(true);
    expect(botao.getAttribute("aria-expanded")).toBe("true");
    const titulos = within(folha())
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(titulos).toEqual(["Ativo", "Estratégias", "Acompanhar", "Conta"]);
    fireEvent.click(within(folha()).getByRole("link", { name: "Juros e inflação" }));
    expect(folha().open).toBe(false);
    expect(botao.getAttribute("aria-expanded")).toBe("false");
  });

  it("tocar fora da folha ou no 'Fechar' fecha", async () => {
    abrirApp("/");
    await noInicio();
    const botao = within(abas()).getByRole("button", { name: "Mais" });
    fireEvent.click(botao);
    fireEvent.click(folha()); // o clique no fundo escuro chega no próprio dialog
    expect(folha().open).toBe(false);
    fireEvent.click(botao);
    fireEvent.click(within(folha()).getByRole("button", { name: "Fechar" }));
    expect(folha().open).toBe(false);
  });

  it("o CSS: até 760 px as abas ficam fixas embaixo, com toque de 44 px e a margem do iPhone", () => {
    expect(CSS_DO_APP).toMatch(/\.app-abas \{ display: none; \}/);
    expect(NO_CELULAR).toMatch(/\.app-menu \{ display: none; \}/);
    expect(NO_CELULAR).toMatch(/\.app-abas \{ display: flex; position: fixed;[^}]*bottom: 0;/);
    expect(NO_CELULAR).toContain("env(safe-area-inset-bottom)");
    expect(NO_CELULAR).toMatch(/\.app-abas :is\(a, button\) \{[^}]*min-height: 44px;/);
    // na folha "Mais", cada tela também tem toque de 44 px
    expect(CSS_DO_APP).toMatch(/\.folha-mais a \{[^}]*min-height: 44px;/);
    // o conteúdo não fica escondido atrás das abas
    expect(NO_CELULAR).toMatch(/body \{ padding-bottom: calc\(/);
  });
});

describe("topo compacto e campos que não dão zoom", () => {
  it("campos com 16 px (o iPhone dá zoom em campo menor) e a página até a borda", () => {
    expect(CSS_DO_APP).toMatch(/\.formulario-do-app input, \.formulario-do-app select \{[^}]*font-size: 16px;/);
    expect(PAGINA_DO_APP).toContain('content="width=device-width, initial-scale=1, viewport-fit=cover"');
  });

  it("no celular o topo esconde o selo e fica mais baixo", () => {
    expect(NO_CELULAR).toMatch(/\.selo-novo \{ display: none; \}/);
  });
});

describe("fundo contido (ADR 0065 item 2)", () => {
  it("o início tem o fundo e o botão de pausa; nada de canvas no app", async () => {
    abrirApp("/");
    await noInicio();
    expect(document.querySelector(".v2-heroi-fundo .v2-aurora")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Pausar animação" })).toBeTruthy();
    expect(document.querySelector("canvas")).toBeNull();
  });

  it("o cartão do fundo não sobe por baixo do topo, como o hero do site", () => {
    expect(CSS_DO_APP).toMatch(/\.app-fundo \{[^}]*margin: 0 0 1\.5rem;/);
  });

  it("o login também tem o fundo", async () => {
    abrirApp("/", { entraSozinho: false });
    await screen.findByRole("button", { name: "Pausar animação" });
    expect(document.querySelector(".v2-heroi-fundo .v2-aurora")).not.toBeNull();
  });

  it("nas telas de dados nada roda sem parar", async () => {
    abrirApp("/visao-geral", {
      rotas: (endereco) =>
        endereco.startsWith("/api/v1/visao-geral") ? respostaJson(200, visao.resposta) : undefined,
    });
    await screen.findByRole("img", { name: /em base 100/ });
    expect(document.querySelector(".v2-aurora")).toBeNull();
    expect(screen.queryByRole("button", { name: /animação/ })).toBeNull();
  });

  it("pausar para a aurora, guarda a escolha (a mesma do site) e troca o rótulo", async () => {
    abrirApp("/");
    await noInicio();
    const botao = screen.getByRole("button", { name: "Pausar animação" });
    fireEvent.click(botao);
    expect(botao.getAttribute("aria-pressed")).toBe("true");
    expect(botao.closest(".v2-heroi-fundo")!.classList.contains("v2-pausado")).toBe(true);
    expect(localStorage.getItem("tl-animacao-pausada")).toBe("1");
    expect(screen.getByRole("button", { name: "Retomar animação" })).toBe(botao);
  });
});

describe("gráficos e tabelas no celular", () => {
  it("os gráficos usam a largura do contêiner", () => {
    expect(CSS_DO_APP).toMatch(/\.grafico svg \{ width: 100%;/);
  });

  for (const [caminho, rota, resposta] of [
    ["/juros-e-inflacao", "juros-e-inflacao", juros.resposta],
    ["/linha-do-tempo", "linha-do-tempo", linha.resposta],
  ] as const) {
    it(`${caminho}: toda tabela rola por dentro (a página não ganha rolagem lateral)`, async () => {
      abrirApp(caminho, {
        rotas: (endereco) => (endereco.startsWith(`/api/v1/${rota}`) ? respostaJson(200, resposta) : undefined),
      });
      await waitFor(() => expect(document.querySelector("table")).not.toBeNull());
      for (const tabela of document.querySelectorAll("table"))
        expect(tabela.parentElement!.classList.contains("tabela-rolavel")).toBe(true);
    });
  }
});
