// @vitest-environment jsdom
// Titular do empresário individual e do MEI na ficha (linha 808; ADR 0128, Emenda 1): o nome só aparece
// quando a API o devolve, e a API só o devolve para a organização com a permissão `pessoa_na_tela`. Para as
// outras contas a rota responde o 404 de um endereço que não existe, e a tela não mostra nada: nem a seção,
// nem um aviso. Empresa que não é individual também não ganha seção. Os nomes aqui são inventados.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FichaDaEmpresaV1 } from "../../src/app/tipos";
import type { TitularDaEmpresaV1 } from "../../src/app/telas/TitularDaFicha";
import { abrirAba, abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA_DA_FICHA = "/api/v1/analista/ficha";
const ROTA_DO_TITULAR = "/api/v1/analista/ficha/titular";
const SECAO = "Titular (empresário individual ou MEI)";

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

const TITULAR: TitularDaEmpresaV1 = {
  estado: "pronta",
  titulares: [{ nome: "BELTRANO EXEMPLO DE TESTE" }],
  total: 1,
  fonte: { fonte: "rfb-cnpj", atribuicao: "Receita Federal, dados abertos do CNPJ", mes_do_retrato: "2026-10" },
  limites: ["Sem CPF."],
};
const SEM_TITULAR: TitularDaEmpresaV1 = { ...TITULAR, estado: "sem_titular", titulares: [], total: 0 };

function abrir(titular: () => Response) {
  return abrirApp("/ficha-da-empresa", {
    rotas: (endereco) => {
      if (endereco === ROTA_DA_FICHA) return respostaJson(200, FICHA);
      if (endereco === ROTA_DO_TITULAR) return titular();
      return undefined;
    },
  });
}

async function verFicha() {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
  fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
  await abrirAba("Quem controla");
}

const pedidosDoTitular = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.filter(([e]) => String(e) === ROTA_DO_TITULAR);

afterEach(() => {
  cleanup();
});

describe("titular do individual e do MEI na ficha", () => {
  it("com a permissão: o nome, a fonte, o mês e os limites; o CNPJ vai no corpo", async () => {
    const { buscar } = abrir(() => respostaJson(200, TITULAR));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText("BELTRANO EXEMPLO DE TESTE")).toBeTruthy();
    expect(within(secao).getByText(/Receita Federal, dados abertos do CNPJ/)).toBeTruthy();
    expect(within(secao).getByText(/10\/2026/)).toBeTruthy();
    expect(within(secao).getByText("Sem CPF.")).toBeTruthy();
    const [[, pedido]] = pedidosDoTitular(buscar);
    expect(pedido?.method).toBe("POST");
    expect(JSON.parse(String(pedido?.body))).toEqual({ cnpj: CNPJ });
  });

  it.each([
    ["sem a permissão (404, igual ao de uma rota que não existe)", 404],
    ["plano sem a ficha (403)", 403],
    ["muitos pedidos (429)", 429],
    ["servidor fora do ar (503)", 503],
  ])("%s: nada aparece, nem a seção nem um aviso", async (_caso, status) => {
    const { buscar } = abrir(() => respostaJson(status, { detail: "Not Found" }));
    await verFicha();
    await waitFor(() => expect(pedidosDoTitular(buscar)).toHaveLength(1));
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
    expect(screen.queryByText(/titular/i)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("tablist")).toBeTruthy(); // a ficha segue inteira
  });

  it("empresa que não é individual: sem seção e sem aviso", async () => {
    const { buscar } = abrir(() => respostaJson(200, SEM_TITULAR));
    await verFicha();
    await waitFor(() => expect(pedidosDoTitular(buscar)).toHaveLength(1));
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
    expect(screen.queryByText(/titular/i)).toBeNull();
  });
});
