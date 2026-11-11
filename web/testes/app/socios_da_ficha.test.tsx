// @vitest-environment jsdom
// Sócios pessoa física na ficha (linha 808; ADR 0128, Emenda 1): a lista só aparece quando a API a
// devolve, e a API só a devolve para a organização com a permissão `pessoa_na_tela`. Para as outras
// contas a rota responde o 404 de um endereço que não existe, e a tela não mostra nada: nem a seção,
// nem um aviso. Os nomes aqui são inventados.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SociosDaEmpresaV1 } from "../../src/app/telas/SociosDaFicha";
import type { FichaDaEmpresaV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA_DA_FICHA = "/api/v1/analista/ficha";
const ROTA_DOS_SOCIOS = "/api/v1/analista/ficha/pessoas";
const SECAO = "Sócios pessoa física";

const FICHA: FichaDaEmpresaV1 = {
  estado: "pronta",
  ficha: {
    cnpj: "02429144000193",
    como_era_em: "2026-11-10",
    cadastro_na_receita: {
      razao_social: { valor: "EMPRESA MODELO S.A.", fonte: "rfb-cnpj", publico_em: "2026-09-30", visto_em: null },
    },
    entregas: null,
  },
  fontes: [],
  limites: ["Nada aqui é recomendação de investimento."],
  o_que_vem: [],
};
const NAO_LIBERADA: FichaDaEmpresaV1 = { ...FICHA, estado: "nao_liberada", ficha: null };

const SOCIOS: SociosDaEmpresaV1 = {
  estado: "pronta",
  socios: [
    { nome: "FULANA EXEMPLO DE TESTE", qualificacao: "Sócio-Administrador", entrou_em: "2005-11-03" },
    { nome: "BELTRANO EXEMPLO DE TESTE", qualificacao: "Sócio", entrou_em: null },
  ],
  total: 2,
  fonte: { fonte: "rfb-cnpj", atribuicao: "Receita Federal, dados abertos do CNPJ", mes_do_retrato: "2026-10" },
  limites: ["Só adultos.", "Sem CPF."],
};
const SEM_SOCIOS: SociosDaEmpresaV1 = { ...SOCIOS, estado: "sem_socios", socios: [], total: 0 };
const CORTADA: SociosDaEmpresaV1 = { ...SOCIOS, total: 140 };

function abrir(socios: () => Response, ficha: FichaDaEmpresaV1 = FICHA) {
  return abrirApp("/ficha-da-empresa", {
    rotas: (endereco) => {
      if (endereco === ROTA_DA_FICHA) return respostaJson(200, ficha);
      if (endereco === ROTA_DOS_SOCIOS) return socios();
      return undefined;
    },
  });
}

async function verFicha() {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
  fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
  await screen.findByRole("region", { name: "Cadastro na Receita" });
}

const pedidosDosSocios = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.filter(([e]) => String(e) === ROTA_DOS_SOCIOS);

afterEach(() => {
  cleanup();
});

describe("sócios pessoa física na ficha", () => {
  it("com a permissão: nome, qualificação e data de entrada, com a fonte, o mês e os limites", async () => {
    const { buscar } = abrir(() => respostaJson(200, SOCIOS));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    const fulana = within(secao).getByRole("row", { name: /FULANA EXEMPLO DE TESTE/ });
    expect(within(fulana).getByText("Sócio-Administrador")).toBeTruthy();
    expect(within(fulana).getByText("03/11/2005")).toBeTruthy();
    expect(within(secao).getByRole("row", { name: /BELTRANO EXEMPLO DE TESTE/ }).textContent).toContain("—");
    expect(within(secao).getByText(/Receita Federal, dados abertos do CNPJ/)).toBeTruthy();
    expect(within(secao).getByText(/10\/2026/)).toBeTruthy();
    expect(within(secao).getByText("Sem CPF.")).toBeTruthy();
    const [[, pedido]] = pedidosDosSocios(buscar);
    expect(pedido?.method).toBe("POST");
    expect(JSON.parse(String(pedido?.body))).toEqual({ cnpj: CNPJ }); // o CNPJ no corpo, nunca no endereço
  });

  it.each([
    ["sem a permissão (404, igual ao de uma rota que não existe)", 404],
    ["plano sem a ficha (403)", 403],
    ["muitos pedidos (429)", 429],
    ["servidor fora do ar (503)", 503],
  ])("%s: nada aparece, nem a seção nem um aviso", async (_caso, status) => {
    const { buscar } = abrir(() => respostaJson(status, { detail: "Not Found" }));
    await verFicha();
    await waitFor(() => expect(pedidosDosSocios(buscar)).toHaveLength(1));
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
    expect(screen.queryByText(/sócio/i)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("region", { name: "Cadastro na Receita" })).toBeTruthy(); // a ficha segue inteira
  });

  it("empresa sem sócio pessoa física adulto: a seção diz isso, com os limites", async () => {
    abrir(() => respostaJson(200, SEM_SOCIOS));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/Nenhum sócio pessoa física adulto/)).toBeTruthy();
    expect(within(secao).queryByRole("table")).toBeNull();
    expect(within(secao).getByText("Só adultos.")).toBeTruthy();
  });

  it("lista cortada: diz quantos aparecem e quantos são", async () => {
    abrir(() => respostaJson(200, CORTADA));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/2 de 140/)).toBeTruthy();
  });

  it("ficha ainda não liberada: a lista de sócios nem é pedida", async () => {
    const { buscar } = abrir(() => respostaJson(200, SOCIOS), NAO_LIBERADA);
    fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
    fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
    await screen.findByText(/Dado ainda não liberado/);
    expect(pedidosDosSocios(buscar)).toHaveLength(0);
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
  });
});
