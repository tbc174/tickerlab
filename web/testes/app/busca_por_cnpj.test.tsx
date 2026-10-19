// @vitest-environment jsdom
// Busca por CNPJ no app novo (molde B, PR 3): os quatro estados da rota POST /v1/busca-por-cnpj, com
// dados de mentira. O CNPJ vai no corpo do pedido, nunca no endereço (ADR 0077, item 1).
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { BuscaPorCnpjV1, SecaoDoRelatorioV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "33.000.167/0001-01";
const LIMITES = [
  "Só as companhias abertas com ficha na base aparecem.",
  "Nada aqui é recomendação de investimento.",
];
const DESLIGADO = ["Empresas fechadas: o relatório delas espera a licença dos dados da Receita Federal."];

function secao(chave: string, titulo: string, trancada = false): SecaoDoRelatorioV1 {
  return {
    chave,
    titulo,
    itens: [],
    paragrafos: trancada ? ["Esta seção é do plano Pro."] : [`Texto de ${titulo}.`],
    tabelas: trancada
      ? []
      : [{ chave: `${chave}-t`, titulo: `Tabela de ${titulo}`, colunas: ["Empresa", "Fonte"], linhas: [["Empresa Alfa", "CVM"]] }],
    trancada,
  };
}

const ENCONTRADA: BuscaPorCnpjV1 = {
  situacao: "encontrada",
  cnpj: CNPJ,
  empresa: "Empresa Modelo S.A.",
  tickers: ["MODL3", "MODL4"],
  como_era_em: "2026-10-17",
  secoes: [secao("cadastro", "Cadastro"), secao("rede", "Rede de empresas")],
  fontes: ["CVM, cadastro das companhias abertas"],
  limites: LIMITES,
  desligado: DESLIGADO,
  avisos: [],
};
const FORA: BuscaPorCnpjV1 = {
  situacao: "fora_da_base_aberta",
  cnpj: "11.222.333/0001-81",
  empresa: "",
  tickers: [],
  como_era_em: null,
  secoes: [],
  fontes: [],
  limites: LIMITES,
  desligado: DESLIGADO,
  avisos: ["Este CNPJ ainda não está na base aberta do TickerLab."],
};
const TRANCADA: BuscaPorCnpjV1 = {
  ...ENCONTRADA,
  secoes: [secao("cadastro", "Cadastro"), secao("rede", "Rede de empresas", true), secao("fatos", "Fatos públicos", true)],
};

function abrir(resposta: () => Response) {
  return abrirApp("/busca-por-cnpj", {
    rotas: (endereco) => (endereco.startsWith("/api/v1/busca-por-cnpj") ? resposta() : undefined),
  });
}

const pedidos = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.filter(([e]) => String(e).startsWith("/api/v1/busca-por-cnpj"));

async function buscarPor(cnpj: string) {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: cnpj } });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
}

afterEach(() => {
  cleanup();
});

describe("busca por CNPJ", () => {
  it("não pede nada antes de a pessoa buscar, e já mostra os limites e o que está desligado", async () => {
    const { buscar } = abrir(() => respostaJson(200, ENCONTRADA));
    await screen.findByLabelText("CNPJ");
    expect(pedidos(buscar)).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Busca por CNPJ" })).toBeTruthy();
    expect(screen.getByText(/só as companhias abertas/i)).toBeTruthy();
  });

  it("encontrada: o CNPJ vai no corpo, nunca no endereço, e o relatório vem com fonte, limites e o desligado", async () => {
    const { buscar } = abrir(() => respostaJson(200, ENCONTRADA));
    await buscarPor(CNPJ);
    await screen.findByRole("heading", { name: "Rede de empresas" });
    const [[endereco, pedido]] = pedidos(buscar);
    expect(String(endereco)).toBe("/api/v1/busca-por-cnpj");
    expect(pedido?.method).toBe("POST");
    expect(JSON.parse(String(pedido?.body))).toEqual({ cnpj: CNPJ });
    expect(screen.getByText("Empresa Modelo S.A.")).toBeTruthy();
    expect(screen.getByText(/MODL3, MODL4/)).toBeTruthy();
    expect(screen.getByText(/17\/10\/2026/)).toBeTruthy();
    expect(screen.getByText("Tabela de Rede de empresas")).toBeTruthy();
    expect(screen.getByText(/CVM, cadastro das companhias abertas/)).toBeTruthy();
    const limites = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(limites).getByText(/recomendação de investimento/)).toBeTruthy();
    const desligado = screen.getByRole("region", { name: "O que ainda não aparece" });
    expect(within(desligado).getByText(/Receita Federal/)).toBeTruthy();
  });

  it("ainda não está na base aberta: a mensagem fixa, sem seções, e os limites continuam à vista", async () => {
    abrir(() => respostaJson(200, FORA));
    await buscarPor("11222333000181");
    expect(await screen.findByText(/ainda não está na base aberta/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Cadastro" })).toBeNull();
    expect(screen.getByRole("region", { name: "Limites e cuidados" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "O que ainda não aparece" })).toBeTruthy();
  });

  it("trancada pelo plano: só o título e o convite, com um único link para os Planos", async () => {
    abrir(() => respostaJson(200, TRANCADA));
    await buscarPor(CNPJ);
    await screen.findByRole("heading", { name: "Fatos públicos" });
    expect(screen.getAllByText("Esta seção é do plano Pro.")).toHaveLength(2);
    expect(screen.queryByText("Tabela de Rede de empresas")).toBeNull();
    expect(screen.getAllByRole("link", { name: "Conhecer o plano Pro" })).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Limites e cuidados" })).toBeTruthy();
  });

  it("CNPJ inválido (422): mostra a mensagem da API e não repete o que a pessoa digitou", async () => {
    abrir(() => respostaJson(422, { detail: "CNPJ inválido: confira os dígitos." }));
    await buscarPor("12.345.678/0001-00");
    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("CNPJ inválido: confira os dígitos.");
    expect(screen.queryByText("12.345.678/0001-00")).toBeNull();
  });
});
