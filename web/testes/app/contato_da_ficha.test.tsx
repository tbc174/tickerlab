// @vitest-environment jsdom
// Contato dos estabelecimentos na ficha (linha 808; ADR 0128, Emenda 1): a seção só aparece quando a API a
// devolve, e a API só a devolve para a organização com a permissão `pessoa_na_tela`. Para as outras contas a
// rota responde o 404 de um endereço que não existe, e a tela não mostra nada: nem a seção, nem um aviso.
// Todo endereço, telefone e e-mail aqui é inventado.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ContatoDaEmpresaV1 } from "../../src/app/telas/ContatoDaFicha";
import type { FichaDaEmpresaV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA_DA_FICHA = "/api/v1/analista/ficha";
const ROTA_DO_CONTATO = "/api/v1/analista/ficha/contato";
const SECAO = "Contato dos estabelecimentos";

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

const CONTATO: ContatoDaEmpresaV1 = {
  estado: "pronta",
  estabelecimentos: [
    {
      cnpj: "11222333000181",
      matriz: true,
      logradouro: "RUA EXEMPLO 100 SALA 2",
      bairro: "CENTRO",
      cep: "01000000",
      municipio: "SAO PAULO",
      uf: "SP",
      telefones: ["1130001000", "11988887777"],
      email: "contato@exemplo.com.br",
    },
    {
      cnpj: "11222333000262",
      matriz: false,
      logradouro: null,
      bairro: null,
      cep: null,
      municipio: null,
      uf: null,
      telefones: [],
      email: null,
    },
  ],
  total: 2,
  fonte: { fonte: "rfb-cnpj", atribuicao: "Receita Federal, dados abertos do CNPJ", mes_do_retrato: "2026-10" },
  limites: ["Use só para o contato profissional com a empresa."],
};
const SEM_CONTATO: ContatoDaEmpresaV1 = { ...CONTATO, estado: "sem_contato", estabelecimentos: [], total: 0 };
const CORTADA: ContatoDaEmpresaV1 = { ...CONTATO, total: 45 };

function abrir(contato: () => Response, ficha: FichaDaEmpresaV1 = FICHA) {
  return abrirApp("/ficha-da-empresa", {
    rotas: (endereco) => {
      if (endereco === ROTA_DA_FICHA) return respostaJson(200, ficha);
      if (endereco === ROTA_DO_CONTATO) return contato();
      return undefined;
    },
  });
}

async function verFicha() {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
  fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
  await screen.findByRole("region", { name: "Cadastro na Receita" });
}

const pedidosDoContato = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.filter(([e]) => String(e) === ROTA_DO_CONTATO);

afterEach(() => {
  cleanup();
});

describe("contato dos estabelecimentos na ficha", () => {
  it("com a permissão: endereço, telefones e e-mail formatados, com a fonte, o mês e os limites", async () => {
    const { buscar } = abrir(() => respostaJson(200, CONTATO));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    const matriz = within(secao).getByRole("row", { name: /11\.222\.333\/0001-81 \(matriz\)/ });
    expect(within(matriz).getByText(/RUA EXEMPLO 100 SALA 2, CENTRO, SAO PAULO\/SP, CEP 01000-000/)).toBeTruthy();
    expect(within(matriz).getByText("(11) 3000-1000 · (11) 98888-7777")).toBeTruthy();
    expect(within(matriz).getByText("contato@exemplo.com.br")).toBeTruthy();
    const filial = within(secao).getByRole("row", { name: /11\.222\.333\/0002-62 \(filial\)/ });
    expect(filial.textContent).toContain("—");
    expect(within(secao).getByText(/Receita Federal, dados abertos do CNPJ/)).toBeTruthy();
    expect(within(secao).getByText(/10\/2026/)).toBeTruthy();
    expect(within(secao).getByText("Use só para o contato profissional com a empresa.")).toBeTruthy();
    const [[, pedido]] = pedidosDoContato(buscar);
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
    await waitFor(() => expect(pedidosDoContato(buscar)).toHaveLength(1));
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
    expect(screen.queryByText(/estabelecimento/i)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("region", { name: "Cadastro na Receita" })).toBeTruthy(); // a ficha segue inteira
  });

  it("empresa sem estabelecimento ativo: a seção diz isso, com os limites", async () => {
    abrir(() => respostaJson(200, SEM_CONTATO));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/Nenhum estabelecimento ativo/)).toBeTruthy();
    expect(within(secao).queryByRole("table")).toBeNull();
  });

  it("lista cortada: diz quantos aparecem e quantos são", async () => {
    abrir(() => respostaJson(200, CORTADA));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/2 de 45/)).toBeTruthy();
  });

  it("ficha ainda não liberada: o contato nem é pedido", async () => {
    const { buscar } = abrir(() => respostaJson(200, CONTATO), NAO_LIBERADA);
    fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
    fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
    await screen.findByText(/Dado ainda não liberado/);
    expect(pedidosDoContato(buscar)).toHaveLength(0);
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
  });
});
