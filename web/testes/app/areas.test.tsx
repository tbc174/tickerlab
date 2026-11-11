// @vitest-environment jsdom
// O menu do app novo por áreas (ADR 0096; linha 822): Empresas (o caminho do analista) no topo, Companhias
// abertas e Mais, que nasce recolhida; cada uma só com as telas que abrem (as que ainda não estão no app
// novo ficam atrás de um link só para a versão clássica, no fim do menu), favoritos no topo, áreas que
// recolhem e o trilho de ícones entre 761 e 1.100 px.
// A Conta fica no menu da pessoa.
// O jsdom não aplica CSS: as regras que o Chrome mostrou faltar são conferidas como texto.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AREAS, AREAS_DO_MENU, areaDoEndereco, itensDaArea, telasProntasDaArea } from "../../src/app/areas";
import { abrirApp } from "./ajudantes";

const CSS_DO_APP = readFileSync(join(process.cwd(), "src", "app", "app.css"), "utf8");
const menu = () => screen.getByRole("navigation", { name: "Telas" });
const secao = (rotulo: string) => within(menu()).getByRole("heading", { name: rotulo }).closest("section")!;
/** Abre uma tela que nunca termina de carregar (o menu é o que interessa aqui). */
const abrirTela = (caminho: string) => abrirApp(caminho, { rotas: () => new Promise(() => {}) as never });

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("as áreas (vindas de src/paginas.py)", () => {
  it("a ordem é Início, Empresas, Companhias abertas, Mais, Conta e Ajuda", () => {
    expect(AREAS.map((a) => a.rotulo)).toEqual(["Início", "Empresas", "Companhias abertas", "Mais", "Conta", "Ajuda"]);
  });

  it("cada endereço sabe a sua área; o início é a área Início", () => {
    expect(areaDoEndereco("/")).toBe("inicio");
    expect(areaDoEndereco("/risco")).toBe("ativo");
    expect(areaDoEndereco("/ficha-da-empresa")).toBe("empresas");
    expect(areaDoEndereco("/backtest/")).toBe("mais");
    expect(areaDoEndereco("/juros-e-inflacao")).toBe("mais");
    expect(areaDoEndereco("/planos")).toBe("conta");
    expect(areaDoEndereco("/nao-existe")).toBeNull();
  });

  it("as telas fora do menu (Termos e Privacidade) não entram em nenhuma área", () => {
    const todas = AREAS.flatMap((a) => itensDaArea(a.chave).map((i) => i.pagina.chave));
    expect(todas).not.toContain("termos");
    expect(todas).not.toContain("privacidade");
  });
});

describe("menu lateral por áreas", () => {
  it("uma seção por área, com o rótulo como título, e só as telas que abrem", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const titulos = within(menu())
      .getAllByRole("heading")
      .map((h) => h.textContent);
    expect(titulos).toEqual(["Empresas", "Companhias abertas", "Mais"]);
    const ativo = secao("Companhias abertas");
    expect(within(ativo).getByRole("link", { name: "Visão geral" }).getAttribute("href")).toBe("/visao-geral");
    expect(within(ativo).getByRole("link", { name: "Comparar ativos" })).toBeTruthy();
    // ainda não está no app novo: não aparece (o menu não mostra linha que não abre)
    expect(within(menu()).queryByText("Correlação e beta")).toBeNull();
    expect(within(menu()).getByRole("link", { name: "Início" }).getAttribute("href")).toBe("/");
  });

  it("Empresas vem primeiro, com o caminho do analista na ordem: encontrar, ficha e comparar", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const links = within(secao("Empresas")).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href")).slice(0, 3)).toEqual([
      "/encontrar-empresas",
      "/ficha-da-empresa",
      "/comparar-empresas",
    ]);
    const botao = within(secao("Empresas")).getByRole("button", { name: "Empresas" });
    expect(botao.getAttribute("aria-expanded")).toBe("true");
  });

  it("a área Mais nasce recolhida, com as telas dela lá dentro, e abre no clique", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const botao = within(secao("Mais")).getByRole("button", { name: "Mais" });
    expect(botao.getAttribute("aria-expanded")).toBe("false");
    expect(secao("Mais").querySelector("ul")!.hidden).toBe(true);
    // recolhida, não apagada: o Backtest segue na lista
    expect(secao("Mais").querySelector('a[href="/backtest"]')).not.toBeNull();
    fireEvent.click(botao);
    expect(botao.getAttribute("aria-expanded")).toBe("true");
    expect(JSON.parse(localStorage.getItem("tickerlab.menu.areas-recolhidas")!)).toEqual([]);
  });

  it("chegar numa tela da área Mais abre a área (o link da tela aberta fica à vista)", async () => {
    abrirTela("/backtest");
    await screen.findByRole("heading", { level: 1, name: "Backtest" });
    const botao = within(secao("Mais")).getByRole("button", { name: "Mais" });
    await waitFor(() => expect(botao.getAttribute("aria-expanded")).toBe("true"));
  });

  it("nenhuma linha do menu é 'em breve': toda tela listada tem link", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    expect(menu().textContent).not.toContain("em breve");
    const linhas = [...menu().querySelectorAll(".itens-da-area li")];
    expect(linhas.length).toBeGreaterThan(0);
    for (const linha of linhas) expect(linha.querySelector("a")).not.toBeNull();
    // cada área do menu segue com ao menos uma tela, e todas as prontas dela estão lá
    for (const area of AREAS_DO_MENU) {
      const prontas = telasProntasDaArea(area).map((p) => p.titulo);
      expect(prontas.length).toBeGreaterThan(0);
      const rotulo = AREAS.find((a) => a.chave === area)!.rotulo;
      // pelo DOM, não pelo papel: a lista da área recolhida ("Mais") está escondida e segue completa
      expect([...secao(rotulo).querySelectorAll(".itens-da-area a")].map((a) => a.textContent)).toEqual(prontas);
    }
  });

  it("as telas que só existem na versão clássica ficam atrás de um link só, no fim do menu", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const link = within(menu()).getByRole("link", { name: "Outras telas na versão clássica" });
    expect(link.getAttribute("href")).toBe("/classico/");
    expect(menu().lastElementChild).toBe(link);
  });

  it("a Conta não fica no menu lateral: fica no menu da pessoa, no topo", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    expect(within(menu()).queryByRole("link", { name: "Planos e assinatura" })).toBeNull();
    const daConta = document.querySelector(".conta-no-topo")!;
    for (const nome of ["Minhas simulações", "Meus dados e privacidade", "Planos e assinatura"])
      expect(within(daConta as HTMLElement).getByRole("link", { name: nome })).toBeTruthy();
  });

  it("a área da tela aberta vem expandida e o link da tela leva aria-current", async () => {
    localStorage.setItem("tickerlab.menu.areas-recolhidas", JSON.stringify(["ativo"]));
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const botao = within(secao("Companhias abertas")).getByRole("button", { name: "Companhias abertas" });
    // o menu nasce junto com a tela (a moldura só vem depois do login): a área abre no efeito da chegada
    await waitFor(() => expect(botao.getAttribute("aria-expanded")).toBe("true"));
    const risco = within(secao("Companhias abertas")).getByRole("link", { name: "Risco" });
    expect(risco.getAttribute("aria-current")).toBe("page");
    expect(JSON.parse(localStorage.getItem("tickerlab.menu.areas-recolhidas")!)).toEqual([]);
  });

  it("recolher uma área esconde as telas dela e fica guardado no navegador", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const botao = within(secao("Empresas")).getByRole("button", { name: "Empresas" });
    expect(botao.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(botao);
    expect(botao.getAttribute("aria-expanded")).toBe("false");
    expect(secao("Empresas").querySelector("ul")!.hidden).toBe(true);
    expect(JSON.parse(localStorage.getItem("tickerlab.menu.areas-recolhidas")!)).toEqual(["mais", "empresas"]);
  });

  it("a área da tela aberta também recolhe (só abre sozinha ao chegar numa tela dela)", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const botao = within(secao("Companhias abertas")).getByRole("button", { name: "Companhias abertas" });
    fireEvent.click(botao);
    expect(botao.getAttribute("aria-expanded")).toBe("false");
    expect(secao("Companhias abertas").querySelector("ul")!.hidden).toBe(true);
    expect(JSON.parse(localStorage.getItem("tickerlab.menu.areas-recolhidas")!)).toEqual(["mais", "ativo"]);
  });

  it("o CSS respeita o hidden da lista recolhida (o display: flex dela ganhava do hidden)", () => {
    expect(CSS_DO_APP).toMatch(/\.itens-da-area\[hidden\] \{ display: none; \}/);
  });

  it("a estrela põe a tela em Favoritos, no topo do menu, e guarda no navegador", async () => {
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    expect(within(menu()).queryByRole("heading", { name: "Favoritos" })).toBeNull();
    const estrela = within(secao("Companhias abertas")).getByRole("button", { name: "Favoritar Risco" });
    expect(estrela.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(estrela);
    expect(JSON.parse(localStorage.getItem("tickerlab.menu.favoritos")!)).toEqual(["risco"]);
    const titulos = within(menu())
      .getAllByRole("heading")
      .map((h) => h.textContent);
    expect(titulos[0]).toBe("Favoritos");
    expect(within(secao("Favoritos")).getByRole("link", { name: "Risco" })).toBeTruthy();
    // tirar dos favoritos pela mesma estrela
    fireEvent.click(within(secao("Favoritos")).getByRole("button", { name: "Favoritar Risco" }));
    expect(within(menu()).queryByRole("heading", { name: "Favoritos" })).toBeNull();
    expect(JSON.parse(localStorage.getItem("tickerlab.menu.favoritos")!)).toEqual([]);
  });

  it("favorito guardado de uma tela que saiu do app (ou lixo no navegador) não quebra o menu", async () => {
    localStorage.setItem("tickerlab.menu.favoritos", JSON.stringify(["nao_existe", 3, "backtest"]));
    localStorage.setItem("tickerlab.menu.areas-recolhidas", "{isto não é json");
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    const favoritos = within(secao("Favoritos")).getAllByRole("link").map((a) => a.textContent);
    expect(favoritos).toEqual(["Backtest"]);
  });

  it("sem localStorage (navegação privada que recusa), o menu abre do mesmo jeito", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("bloqueado");
    });
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    fireEvent.click(within(secao("Companhias abertas")).getByRole("button", { name: "Favoritar Risco" }));
    expect(within(secao("Favoritos")).getByRole("link", { name: "Risco" })).toBeTruthy();
    vi.restoreAllMocks();
  });
});

describe("trilho de ícones entre 761 e 1.100 px", () => {
  it("com a tela nessa largura, o menu vira trilho (o nome aparece ao passar o mouse)", async () => {
    vi.stubGlobal("matchMedia", (consulta: string) => ({
      matches: consulta.includes("1100px"),
      media: consulta,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    expect(menu().classList.contains("trilho")).toBe(true);
    // o nome da área continua para o leitor de tela e no "title" do botão
    const botao = within(secao("Companhias abertas")).getByRole("button", { name: "Companhias abertas" });
    expect(botao.getAttribute("title")).toBe("Companhias abertas");
  });

  it("no PC largo, sem trilho", async () => {
    vi.stubGlobal("matchMedia", (consulta: string) => ({
      matches: false,
      media: consulta,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    abrirTela("/risco");
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    expect(menu().classList.contains("trilho")).toBe(false);
  });

  it("as telas que abrem ao lado ficam por cima do gráfico (o menu fixo tem a própria camada)", () => {
    const noTrilho = CSS_DO_APP.split("@media (min-width: 761px) and (max-width: 1100px)")[1];
    expect(noTrilho).toMatch(/\.app-menu\.trilho \{[^}]*z-index: 7;/);
  });
});
