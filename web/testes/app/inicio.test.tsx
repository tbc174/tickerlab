// @vitest-environment jsdom
// O Início do app novo (linha 903, PR E): uma pergunta (qual empresa?) com o campo de CNPJ, que abre a ficha
// sem pôr o CNPJ no endereço; os passos; "O que a base tem", com as contagens do catálogo; e "O que mudou",
// com as últimas entregas da mesma rota da tela. Os passos e o Workspace são de workspace.test.tsx.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { conteudoDoApp } from "../../src/conteudo";
import { abrirApp, respostaJson } from "./ajudantes";

// um CNPJ inventado, só com o formato certo
const CNPJ_DE_TESTE = "11.222.333/0001-81";
const ENTREGAS = [
  { data: "2026-11-13", titulo: "Início novo", o_que: "Uma pergunta e três passos.", url: "" },
  { data: "2026-11-12", titulo: "Comparar empresas", o_que: "Com nomes.", url: "comparar-empresas" },
  { data: "2026-11-11", titulo: "Encontrar empresas", o_que: "Com etiquetas.", url: "encontrar-empresas" },
  { data: "2026-11-10", titulo: "Dados e cobertura", o_que: "O catálogo.", url: "dados-e-cobertura" },
];
const SEM_PULSE = {
  janela: { inicio: "2026-11-06T23:00:00Z", fim: "2026-11-13T23:00:00Z", primeira_vez: true, texto: "" },
  estrategias: [],
  avisos: [],
  acontecimentos: [],
  variacoes: [],
  sem_variacao: [],
  avisos_dos_ativos: [],
  limites: { sem_ficha: 0, alem_do_maximo: 0, nao_conferidas: 0, alem_dos_ativos: 0 },
  sem_estrategias: "",
  notas: [],
};

// o estado do chat, para o clique de um atalho abrir o Perguntar de verdade
const CHAT_PRONTO = {
  situacao: "pronto",
  pode_perguntar: true,
  mensagem: null,
  perguntas_hoje: 0,
  perguntas_por_dia: 20,
  perguntas_no_mes: 0,
  perguntas_por_mes: 300,
  caracteres_da_pergunta: 2000,
  perguntas_no_historico: 4,
  caracteres_do_historico: 4000,
  como_funciona: "O modelo só lê a base.",
  exemplos: [],
  limites: [],
};

function abrir(oQueMudou: () => Response = () => respostaJson(200, { entregas: ENTREGAS })) {
  return abrirApp("/", {
    rotas: (endereco) => {
      if (endereco.startsWith("/api/v1/pulse")) return respostaJson(200, SEM_PULSE);
      if (endereco.startsWith("/api/v1/o-que-mudou")) return oQueMudou();
      if (endereco === "/api/v1/chat/estado") return respostaJson(200, CHAT_PRONTO);
      return undefined;
    },
  });
}
const titulo = () => screen.findByRole("heading", { level: 1, name: "Qual empresa você quer estudar?" }, { timeout: 5000 });
const formulario = () => screen.getByRole("form", { name: "Abrir a ficha de uma empresa" });
const campo = () => within(formulario()).getByLabelText("CNPJ da empresa") as HTMLInputElement;

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a pergunta do Início abre a ficha pelo CNPJ", () => {
  it("o CNPJ inteiro abre a ficha, e nunca vai para o endereço", async () => {
    const { buscar } = abrir();
    await titulo();
    fireEvent.change(campo(), { target: { value: CNPJ_DE_TESTE } });
    fireEvent.click(within(formulario()).getByRole("button", { name: "Abrir a ficha" }));
    await screen.findByRole("heading", { level: 1, name: "Ficha da empresa" });
    expect((screen.getByLabelText("CNPJ") as HTMLInputElement).value).toBe("11222333000181");
    await waitFor(() => expect(buscar.mock.calls.some(([pedido]) => String(pedido).includes("ficha"))).toBe(true));
    for (const [pedido] of buscar.mock.calls) expect(String(pedido)).not.toContain("11222333000181");
  });

  it("pedaço de CNPJ não sai do Início: avisa e continua na tela", async () => {
    abrir();
    await titulo();
    fireEvent.change(campo(), { target: { value: "11.222.333" } });
    fireEvent.submit(formulario());
    expect(within(formulario()).getByRole("alert").textContent).toContain("14 caracteres");
    expect(campo().getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Qual empresa você quer estudar?");
    fireEvent.change(campo(), { target: { value: "11.222.333/0" } }); // voltou a digitar: o aviso some
    expect(within(formulario()).queryByRole("alert")).toBeNull();
  });

  it("quem não tem o CNPJ vai para Encontrar empresas", async () => {
    abrir();
    await titulo();
    const link = within(formulario()).getByRole("link", { name: "Encontre empresas por setor e UF" });
    expect(link.getAttribute("href")).toBe("/encontrar-empresas");
  });
});

describe("os atalhos de pergunta do Início", () => {
  it("são quatro, em uma lista com nome, e nenhuma cita empresa ou pessoa", async () => {
    abrir();
    await titulo();
    const lista = screen.getByRole("list", { name: "Perguntas para começar" });
    const botoes = within(lista).getAllByRole("button");
    expect(botoes).toHaveLength(4);
    for (const botao of botoes) expect(botao.textContent).toMatch(/\?$|\.$/);
  });

  it("o clique abre o Perguntar com a pergunta na caixa, sem enviar e sem pôr o texto no endereço", async () => {
    const { buscar } = abrir();
    await titulo();
    const botao = within(screen.getByRole("list", { name: "Perguntas para começar" })).getAllByRole("button")[1];
    const pergunta = botao.textContent ?? "";
    expect(pergunta).not.toBe("");
    fireEvent.click(botao);
    const caixa = (await screen.findByRole("textbox", { name: "Sua pergunta" }, { timeout: 5000 })) as HTMLTextAreaElement;
    expect(caixa.value).toBe(pergunta);
    await new Promise((fim) => setTimeout(fim, 50));
    for (const [pedido] of buscar.mock.calls) {
      expect(String(pedido)).not.toContain(encodeURIComponent(pergunta));
      expect(String(pedido)).not.toContain(pergunta);
    }
    expect(buscar.mock.calls.some(([e]) => e === "/api/v1/chat")).toBe(false);
  });
});

describe("os painéis do Início", () => {
  it("o que a base tem: as contagens do catálogo, e o caminho para Dados e cobertura", async () => {
    abrir();
    await titulo();
    const painel = screen.getByRole("heading", { level: 2, name: "O que a base tem" }).parentElement!;
    const { tabelas, ligadas_pelo_cnpj, orgaos, fontes } = conteudoDoApp.base;
    const valores = Array.from(painel.querySelectorAll(".numero-valor")).map((v) => v.textContent);
    expect(valores).toEqual([tabelas, ligadas_pelo_cnpj, orgaos, fontes].map((n) => n.toLocaleString("pt-BR")));
    expect(ligadas_pelo_cnpj).toBeLessThanOrEqual(tabelas);
    expect(within(painel).getByText(/Contado do catálogo da base/)).toBeTruthy();
    expect(within(painel).getByRole("link", { name: "Ver dados e cobertura" }).getAttribute("href")).toBe(
      "/dados-e-cobertura",
    );
  });

  it("o que mudou: só as três entregas mais novas, com a data, e o link para a tela", async () => {
    abrir();
    await titulo();
    const lista = await screen.findByRole("list", { name: "Últimas entregas" });
    const itens = within(lista).getAllByRole("listitem");
    expect(itens.map((i) => within(i).getByRole("link").textContent)).toEqual(
      ENTREGAS.slice(0, 3).map((e) => e.titulo),
    );
    expect(within(itens[1]).getByRole("link").getAttribute("href")).toBe("/comparar-empresas");
    expect(itens[0].textContent).toContain("13/11");
    expect(screen.getByRole("link", { name: "O que mudou no app" }).getAttribute("href")).toBe("/o-que-mudou");
  });

  it("sem resposta de O que mudou, fica só o link (sem erro na tela)", async () => {
    abrir(() => respostaJson(503, { detail: "fora do ar" }));
    await titulo();
    await new Promise((pronto) => setTimeout(pronto, 0));
    expect(screen.queryByRole("list", { name: "Últimas entregas" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("link", { name: "O que mudou no app" })).toBeTruthy();
  });
});
