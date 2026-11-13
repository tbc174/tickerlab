// @vitest-environment jsdom
// A casca do app (linha 903): o mesmo menu de sete itens em toda tela, na ordem de src/paginas.py, só com o
// que abre; a lista "Todas as telas" para o resto; a busca do topo (Ctrl K), que acha uma tela pelo nome e
// abre a ficha de um CNPJ digitado inteiro, sem pôr o CNPJ no endereço; e o link "O que mudou".
// O jsdom não aplica CSS: as regras de largura são conferidas como texto.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { conteudoDoApp } from "../../src/conteudo";
import { cnpjDigitado, telasDaBusca } from "../../src/app/BuscaGlobal";
import { ITENS_COM_ABA, ITENS_DO_MENU, itemDoEndereco } from "../../src/app/menu";
import { TELAS_DO_APP, temTelaPronta } from "../../src/app/rotas";
import { abrirApp, respostaJson } from "./ajudantes";

const CSS_DO_APP = readFileSync(join(process.cwd(), "src", "app", "app.css"), "utf8");
const menu = () => screen.getByRole("navigation", { name: "Telas" });
// o cabeçalho de cada tela também é um <header>: o topo da casca se acha pela classe
const topo = () => document.querySelector<HTMLElement>("header.topo")!;
const folha = () => document.querySelector<HTMLDialogElement>("dialog.folha-mais")!;
const busca = () => document.querySelector<HTMLDialogElement>("dialog.busca-global")!;
const campoDaBusca = () => busca().querySelector("input")!;
/** Abre a busca pelo atalho. O atalho é ligado num efeito do React, que roda um instante depois de a casca
 * aparecer na tela: com a máquina ocupada (o CI), a tecla dada logo depois do título chegava antes do ouvinte
 * e se perdia, e esperar o campo não adiantava. Por isso a tecla se repete até a busca abrir (com ela aberta,
 * o atalho não faz nada). */
const abrirABusca = async () => {
  await waitFor(() => {
    if (busca().querySelector("input") === null) fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(busca().querySelector("input")).not.toBeNull();
  });
};
/** Abre uma tela que nunca termina de carregar (a casca é o que interessa aqui). */
const abrirTela = (caminho: string) => abrirApp(caminho, { rotas: () => new Promise(() => {}) as never });
const noRisco = async () => {
  abrirTela("/risco");
  await screen.findByRole("heading", { level: 1, name: "Risco" });
};
// um CNPJ inventado, só com o formato certo
const CNPJ_DE_TESTE = "11.222.333/0001-81";

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("o menu de sete itens (vindo de src/paginas.py)", () => {
  it("os sete, nesta ordem: Início, Perguntar, Empresas, Setores, Monitorar, Dados e cobertura, Conectar", () => {
    expect(conteudoDoApp.menu.map((item) => item.rotulo)).toEqual([
      "Início",
      "Perguntar",
      "Empresas",
      "Setores",
      "Monitorar",
      "Dados e cobertura",
      "Conectar",
    ]);
  });

  it("o menu só mostra o item que abre: o que ainda não tem tela fica de fora, sem 'em breve'", async () => {
    await noRisco();
    const comTela = conteudoDoApp.menu.filter(
      (item) => item.chave === "inicio" || item.paginas.some((chave) => temTelaPronta(chave)),
    );
    const links = within(menu()).getAllByRole("link");
    // o rótulo, sem o selo "Novo" do item que acabou de ganhar tela
    const rotulo = (a: HTMLElement) => a.querySelector(".rotulo-do-menu")?.textContent ?? a.textContent;
    expect(links.map(rotulo)).toEqual(comTela.map((item) => item.rotulo));
    expect(ITENS_DO_MENU.map((item) => item.chave)).toEqual(comTela.map((item) => item.chave));
    expect(menu().textContent).not.toMatch(/em breve/i);
    for (const link of links) expect(link.getAttribute("href")).toMatch(/^\//);
  });

  it("cada item abre a primeira tela pronta dele; o Início abre a raiz", async () => {
    await noRisco();
    const destino = (nome: string) => within(menu()).getByRole("link", { name: nome }).getAttribute("href");
    expect(destino("Início")).toBe("/");
    expect(destino("Empresas")).toBe("/encontrar-empresas");
    expect(destino("Setores")).toBe("/relatorio-do-setor");
    expect(destino("Dados e cobertura")).toBe("/dados-e-cobertura");
    expect(destino("Conectar")).toBe("/conectar");
  });

  it("os itens do fim (Dados e cobertura, Conectar) ficam numa lista à parte, depois do divisor", async () => {
    await noRisco();
    const listas = [...menu().querySelectorAll("ul.itens-do-menu")];
    expect(listas.length).toBe(2);
    expect([...listas[1].querySelectorAll("a")].map((a) => a.textContent)).toEqual(["Dados e cobertura", "Conectar"]);
    expect(CSS_DO_APP).toMatch(/\.itens-do-menu \+ \.itens-do-menu \{[^}]*border-top:/);
  });

  it("a ficha e a comparação marcam o item Empresas; só a tela que o item abre leva aria-current 'page'", async () => {
    expect(itemDoEndereco("/ficha-da-empresa")).toBe("empresas");
    expect(itemDoEndereco("/comparar-empresas/")).toBe("empresas");
    expect(itemDoEndereco("/")).toBe("inicio");
    expect(itemDoEndereco("/risco")).toBeNull();
    abrirTela("/ficha-da-empresa");
    await screen.findByRole("heading", { level: 1, name: "Ficha da empresa" });
    const empresas = within(menu()).getByRole("link", { name: "Empresas" });
    expect(empresas.getAttribute("aria-current")).toBe("true");
    expect(empresas.classList.contains("active")).toBe(true);
    expect(menu().querySelectorAll("[aria-current]").length).toBe(1);
  });

  it("numa tela sem item no menu, nenhum item fica marcado", async () => {
    await noRisco();
    expect(menu().querySelectorAll("[aria-current]").length).toBe(0);
  });

  it("a Conta não fica no menu lateral: fica no menu da pessoa, no topo", async () => {
    await noRisco();
    expect(within(menu()).queryByRole("link", { name: "Planos e assinatura" })).toBeNull();
    const daConta = document.querySelector<HTMLElement>(".conta-no-topo")!;
    for (const nome of ["Minhas simulações", "Meus dados e privacidade", "Planos e assinatura"])
      expect(within(daConta).getByRole("link", { name: nome })).toBeTruthy();
  });

  it("entre 761 e 1.100 px ficam só os ícones: o nome segue no 'title' e para o leitor de tela", async () => {
    await noRisco();
    expect(within(menu()).getByRole("link", { name: "Empresas" }).getAttribute("title")).toBe("Empresas");
    const estreito = CSS_DO_APP.split("@media (min-width: 761px) and (max-width: 1100px)")[1];
    expect(estreito).toMatch(/\.app-menu :is\(\.rotulo-do-menu, \.selo-do-app\) \{[^}]*clip-path: inset\(50%\);/);
  });

  it("as abas do celular são os primeiros itens do caminho principal (no máximo quatro)", () => {
    expect(ITENS_COM_ABA.length).toBeLessThanOrEqual(4);
    expect(ITENS_COM_ABA.every((item) => !item.secundario)).toBe(true);
    expect(ITENS_COM_ABA[0].chave).toBe("inicio");
  });
});

describe("'Todas as telas': o que não tem item no menu continua a um clique", () => {
  it("o botão do fim do menu abre a lista por área, com toda tela pronta e a versão clássica", async () => {
    await noRisco();
    const botao = within(menu()).getByRole("button", { name: "Todas as telas" });
    expect(menu().lastElementChild).toBe(botao);
    expect(folha().open).toBe(false);
    fireEvent.click(botao);
    expect(folha().open).toBe(true);
    expect(botao.getAttribute("aria-expanded")).toBe("true");
    const titulos = within(folha())
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(titulos).toEqual(["Empresas", "Companhias abertas", "Mais", "Conta"]);
    // a tela que tem item no menu (Perguntar) já está a um clique; a lista traz as outras
    const enderecos = [...menu().querySelectorAll("a"), ...folha().querySelectorAll("a")].map((a) =>
      a.getAttribute("href"),
    );
    // o Pulse é o próprio Início ("/"), o primeiro item do menu
    for (const pagina of TELAS_DO_APP.filter((p) => p.no_menu && p.chave !== "pulse" && temTelaPronta(p.chave)))
      expect(enderecos, pagina.url).toContain(`/${pagina.url}`);
    expect(within(folha()).getByRole("link", { name: "Versão clássica" }).getAttribute("href")).toBe("/classico/");
  });

  it("escolher uma tela, o 'Fechar' e o clique no fundo fecham a lista", async () => {
    await noRisco();
    const botao = within(menu()).getByRole("button", { name: "Todas as telas" });
    fireEvent.click(botao);
    fireEvent.click(within(folha()).getByRole("link", { name: "Backtest" }));
    expect(folha().open).toBe(false);
    expect(botao.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(botao);
    fireEvent.click(within(folha()).getByRole("button", { name: "Fechar" }));
    expect(folha().open).toBe(false);
    fireEvent.click(botao);
    fireEvent.click(folha()); // o clique no fundo escuro chega no próprio dialog
    expect(folha().open).toBe(false);
  });

  it("no computador a lista abre no meio da tela, em colunas", () => {
    const largo = CSS_DO_APP.split("@media (min-width: 761px) {")[1];
    expect(largo).toMatch(/\.folha-mais \{[^}]*margin: auto;/);
    expect(largo).toMatch(/\.areas-da-folha \{ display: grid;/);
  });
});

describe("o topo: busca, 'O que mudou' e conta", () => {
  it("'O que mudou' fica no topo de toda tela e abre a tela das novidades", async () => {
    await noRisco();
    // (o menu da conta também leva lá; no celular, só ele)
    const link = topo().querySelector("a.novidades-no-topo")!;
    expect(link.textContent).toBe("O que mudou");
    expect(link.getAttribute("href")).toBe("/o-que-mudou");
  });

  it("o selo 'Versão nova' saiu e a versão clássica fica na lista 'Todas as telas', não no topo", async () => {
    await noRisco();
    expect(within(topo()).queryByText("Versão nova")).toBeNull();
    expect(within(topo()).queryByRole("link", { name: "Versão clássica" })).toBeNull();
  });

  it("antes de entrar (link compartilhado) a casca vem sem menu e sem busca, com a versão clássica no topo", async () => {
    abrirApp("/c", { entraSozinho: false });
    await waitFor(() => expect(within(topo()).getByRole("link", { name: "Versão clássica" })).toBeTruthy());
    expect(screen.queryByRole("navigation", { name: "Telas" })).toBeNull();
    expect(within(topo()).queryByRole("button", { name: /Buscar/ })).toBeNull();
  });
});

describe("a busca do topo (Ctrl K)", () => {
  it("o botão abre a busca, com as primeiras telas do app à vista", async () => {
    await noRisco();
    const botao = within(topo()).getByRole("button", { name: /Buscar tela ou abrir um CNPJ/ });
    expect(busca().open).toBe(false);
    fireEvent.click(botao);
    expect(busca().open).toBe(true);
    expect(botao.getAttribute("aria-expanded")).toBe("true");
    expect(within(busca()).getAllByRole("link").length).toBeGreaterThan(1);
  });

  it("o clique no espaço interno da janela não fecha a busca; fora da caixa, fecha", async () => {
    await noRisco();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    busca().getBoundingClientRect = () => new DOMRect(100, 50, 400, 300);
    fireEvent.click(busca(), { clientX: 110, clientY: 60 }); // a margem de dentro: ainda é o dialog
    expect(busca().open).toBe(true);
    fireEvent.click(busca(), { clientX: 20, clientY: 20 }); // o fundo escuro
    expect(busca().open).toBe(false);
  });

  it("Ctrl K e Cmd K abrem a busca em qualquer tela", async () => {
    await noRisco();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(busca().open).toBe(true);
    fireEvent.click(busca()); // o fundo fecha
    expect(busca().open).toBe(false);
    fireEvent.keyDown(window, { key: "K", metaKey: true });
    expect(busca().open).toBe(true);
  });

  it("a letra K sozinha não abre nada (não atrapalha quem está digitando)", async () => {
    await noRisco();
    fireEvent.keyDown(window, { key: "k" });
    expect(busca().open).toBe(false);
  });

  it("acha a tela pelo nome, sem ligar para acento nem maiúscula, e o nome vem antes da descrição", () => {
    expect(telasDaBusca("inicio")[0].endereco).toBe("/");
    expect(telasDaBusca("JUROS").map((tela) => tela.endereco)).toContain("/juros-e-inflacao");
    expect(telasDaBusca("ficha")[0].endereco).toBe("/ficha-da-empresa");
    expect(telasDaBusca("xyzxyz")).toEqual([]);
    // só o que abre: uma tela que ainda está só na versão clássica não aparece
    expect(telasDaBusca("correlação")).toEqual([]);
  });

  it("escolher uma tela abre a tela e fecha a busca; o Enter abre a primeira", async () => {
    await noRisco();
    await abrirABusca();
    fireEvent.change(campoDaBusca(), { target: { value: "backtest" } });
    fireEvent.click(within(busca()).getByRole("link", { name: /^Backtest/ }));
    expect(busca().open).toBe(false);
    await screen.findByRole("heading", { level: 1, name: "Backtest" });
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(campoDaBusca().value).toBe(""); // a busca abre limpa
    fireEvent.change(campoDaBusca(), { target: { value: "planos" } });
    fireEvent.submit(campoDaBusca().closest("form")!);
    await screen.findByRole("heading", { level: 1, name: "Planos e assinatura" });
    expect(busca().open).toBe(false);
  });

  it("sem tela com o nome digitado, a busca diz, e aponta a tela que acha empresas", async () => {
    await noRisco();
    await abrirABusca();
    fireEvent.change(campoDaBusca(), { target: { value: "xyzxyz" } });
    expect(within(busca()).getByRole("status").textContent).toBe("Nenhuma tela com esse nome.");
    expect(within(busca()).getByRole("link", { name: "Encontrar empresas" }).getAttribute("href")).toBe(
      "/encontrar-empresas",
    );
  });

  it("reconhece o CNPJ inteiro, com ou sem pontuação e com letras; pedaço de CNPJ não é CNPJ", () => {
    expect(cnpjDigitado(CNPJ_DE_TESTE)).toBe("11222333000181");
    expect(cnpjDigitado(" 11222333000181 ")).toBe("11222333000181");
    expect(cnpjDigitado("12.abc.345/01de-35")).toBe("12ABC34501DE35");
    expect(cnpjDigitado("11.222.333")).toBeNull();
    expect(cnpjDigitado("112223330001811")).toBeNull();
    expect(cnpjDigitado("backtest")).toBeNull();
  });

  it("um CNPJ inteiro abre a ficha dele, e o CNPJ nunca vai para o endereço", async () => {
    const { buscar } = abrirApp("/risco", {
      rotas: (endereco) => (endereco.includes("/api/v1/risco") ? (new Promise(() => {}) as never) : undefined),
    });
    await screen.findByRole("heading", { level: 1, name: "Risco" });
    await abrirABusca();
    fireEvent.change(campoDaBusca(), { target: { value: CNPJ_DE_TESTE } });
    expect(within(busca()).queryAllByRole("link", { name: /^Backtest/ })).toEqual([]);
    fireEvent.click(within(busca()).getByRole("button", { name: /Abrir a ficha deste CNPJ/ }));
    expect(busca().open).toBe(false);
    await screen.findByRole("heading", { level: 1, name: "Ficha da empresa" });
    // a ficha recebeu o CNPJ pelo estado da navegação e já o pôs no campo dela
    expect((screen.getByLabelText("CNPJ") as HTMLInputElement).value).toBe("11222333000181");
    await waitFor(() => expect(buscar.mock.calls.some(([pedido]) => String(pedido).includes("ficha"))).toBe(true));
    for (const [pedido] of buscar.mock.calls) expect(String(pedido)).not.toContain("11222333000181");
  });

  it("com a ficha já aberta, buscar outro CNPJ troca a ficha (a tela recomeça com o CNPJ novo)", async () => {
    abrirApp("/ficha-da-empresa", { rotas: () => respostaJson(404, { detail: "Sem resposta no teste." }) });
    await screen.findByRole("heading", { level: 1, name: "Ficha da empresa" });
    const campo = () => screen.getByLabelText("CNPJ") as HTMLInputElement;
    expect(campo().value).toBe("");
    for (const cnpj of ["11222333000181", "44555666000199"]) {
      await abrirABusca();
      fireEvent.change(campoDaBusca(), { target: { value: cnpj } });
      fireEvent.submit(campoDaBusca().closest("form")!);
      await waitFor(() => expect(campo().value).toBe(cnpj));
    }
  });

  it("o CSS: no celular a busca vira um ícone de 44 px e 'O que mudou' sai do topo", () => {
    const noCelular = CSS_DO_APP.split("@media (max-width: 760px)").slice(1).join("");
    expect(noCelular).toMatch(/\.busca-do-topo \{[^}]*min-width: 44px; min-height: 44px;/);
    expect(noCelular).toMatch(/\.novidades-no-topo \{ display: none; \}/);
    // campo de 16 px: o iPhone dá zoom em campo menor
    expect(CSS_DO_APP).toMatch(/\.busca-global input \{[^}]*font-size: 16px;/);
  });
});
