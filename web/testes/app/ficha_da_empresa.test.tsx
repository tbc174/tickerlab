// @vitest-environment jsdom
// Ficha da empresa (tela do analista, linha 798): os três estados da rota POST /v1/analista/ficha, com
// dados de mentira, e o Excel. O CNPJ vai no corpo do pedido, nunca no endereço; "sem prontidão" é um
// estado da tela ("dado ainda não liberado"), nunca um erro.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CampoComFonteV1, FichaDaEmpresaV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA = "/api/v1/analista/ficha";
const LIMITES = [
  "Pessoa natural (MEI, empresário individual) não é servida.",
  "Nada aqui é recomendação de investimento.",
];

function campo(valor: CampoComFonteV1["valor"], fonte = "rfb-cnpj", publico_em = "2026-10-31"): CampoComFonteV1 {
  return { valor, fonte, publico_em, visto_em: null };
}

const PRONTA: FichaDaEmpresaV1 = {
  estado: "pronta",
  ficha: {
    cnpj: "02429144000193",
    como_era_em: "2026-11-10",
    cadastro_na_receita: {
      razao_social: campo("EMPRESA MODELO S.A.", "rfb-cnpj", "2026-09-30"),
      situacao_cadastral: campo("02"),
      matriz: campo(true),
      data_situacao_cadastral: campo("2005-11-03"),
    },
    entregas: [
      {
        documento: campo("DFP", "cvm-hist-dfp", "2026-03-20"),
        prazo: campo("2026-03-31", "cvm-hist-dfp", "2026-03-20"),
        situacao_da_entrega: campo("on_time", "cvm-hist-dfp", "2026-03-20"),
      },
    ],
  },
  fontes: [
    { fonte: "rfb-cnpj", licenca: "CC BY 4.0", atribuicao: "Receita Federal do Brasil" },
    { fonte: "cvm-hist-dfp", licenca: "ODbL", atribuicao: "Comissão de Valores Mobiliários" },
  ],
  limites: LIMITES,
};
const SEM_ENTREGAS: FichaDaEmpresaV1 = { ...PRONTA, ficha: { ...PRONTA.ficha!, entregas: null } };
const NAO_LIBERADA: FichaDaEmpresaV1 = { estado: "nao_liberada", ficha: null, fontes: [], limites: LIMITES };
const NAO_DISPONIVEL: FichaDaEmpresaV1 = { estado: "nao_disponivel", ficha: null, fontes: [], limites: LIMITES };

function abrir(resposta: () => Response) {
  return abrirApp("/ficha-da-empresa", {
    rotas: (endereco) => (endereco === ROTA ? resposta() : undefined),
  });
}

const pedidos = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.filter(([e]) => String(e).startsWith("/api/v1/analista"));

async function verFicha(cnpj: string) {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: cnpj } });
  fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
}

afterEach(() => {
  cleanup();
});

describe("ficha da empresa", () => {
  it("não pede nada antes de a pessoa buscar", async () => {
    const { buscar } = abrir(() => respostaJson(200, PRONTA));
    await screen.findByLabelText("CNPJ");
    expect(pedidos(buscar)).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Ficha da empresa" })).toBeTruthy();
    expect(screen.getByText(/Pessoa física, MEI e empresário individual não aparecem/)).toBeTruthy();
  });

  it("pronta: o CNPJ vai no corpo, e cada campo vem com o valor legível, a fonte e a data", async () => {
    const { buscar } = abrir(() => respostaJson(200, PRONTA));
    await verFicha(CNPJ);
    const cadastro = await screen.findByRole("region", { name: "Cadastro na Receita" });
    const [[endereco, pedido]] = pedidos(buscar);
    expect(String(endereco)).toBe(ROTA);
    expect(pedido?.method).toBe("POST");
    expect(JSON.parse(String(pedido?.body))).toEqual({ cnpj: CNPJ });
    const razao = within(cadastro).getByRole("row", { name: /Razão social/ });
    expect(within(razao).getByText("EMPRESA MODELO S.A.")).toBeTruthy();
    expect(within(razao).getByText("rfb-cnpj")).toBeTruthy();
    expect(within(razao).getByText("30/09/2026")).toBeTruthy();
    expect(within(cadastro).getByRole("row", { name: /Situação cadastral/ }).textContent).toContain("Ativa");
    expect(within(cadastro).getByRole("row", { name: /Matriz/ }).textContent).toContain("Sim");
    expect(within(cadastro).getByRole("row", { name: /Data da situação/ }).textContent).toContain("03/11/2005");
    const entregas = screen.getByRole("region", { name: "Entregas de balanço à CVM" });
    expect(within(entregas).getByText("No prazo")).toBeTruthy();
    expect(within(entregas).getByText("cvm-hist-dfp")).toBeTruthy();
    const fontes = screen.getByRole("region", { name: "Fontes" });
    expect(within(fontes).getByText(/Receita Federal do Brasil/)).toBeTruthy();
    const limites = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(limites).getByText(/recomendação de investimento/)).toBeTruthy();
    expect(screen.getByText(/como a base conhecia em 10\/11\/2026/)).toBeTruthy();
  });

  it("sem entregas: a frase fixa no lugar da tabela", async () => {
    abrir(() => respostaJson(200, SEM_ENTREGAS));
    await verFicha(CNPJ);
    const entregas = await screen.findByRole("region", { name: "Entregas de balanço à CVM" });
    expect(within(entregas).queryByRole("table")).toBeNull();
    expect(within(entregas).getByText(/Sem entregas nesta ficha/)).toBeTruthy();
  });

  it("dado ainda não liberado: é estado da tela, sem alerta de erro e com os limites à vista", async () => {
    abrir(() => respostaJson(200, NAO_LIBERADA));
    await verFicha(CNPJ);
    expect(await screen.findByText(/Dado ainda não liberado/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Baixar em Excel" })).toBeNull();
    expect(screen.getByRole("region", { name: "Limites e cuidados" })).toBeTruthy();
  });

  it("não disponível: uma frase só, sem dizer o motivo nem repetir o CNPJ", async () => {
    abrir(() => respostaJson(200, NAO_DISPONIVEL));
    await verFicha("11.222.333/0001-81");
    expect((await screen.findByRole("note")).textContent).toBe("Ficha não disponível para este CNPJ.");
    expect(screen.queryByText(/11\.222\.333/)).toBeNull();
    expect(screen.queryByRole("region", { name: "Cadastro na Receita" })).toBeNull();
  });

  it("CNPJ inválido (422): mostra a mensagem da API", async () => {
    abrir(() => respostaJson(422, { detail: "CNPJ inválido: confira os 14 caracteres." }));
    await verFicha("123");
    expect((await screen.findByRole("alert")).textContent).toContain("CNPJ inválido");
  });

  it("Baixar em Excel: pede a planilha por POST com o CNPJ no corpo e entrega o arquivo", async () => {
    const criar = vi.fn(() => "blob:xlsx");
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: vi.fn() });
    const clicar = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { buscar } = abrirApp("/ficha-da-empresa", {
      rotas: (endereco) => {
        if (endereco === `${ROTA}/planilha`) return new Response("PK", { status: 200 });
        return endereco === ROTA ? respostaJson(200, PRONTA) : undefined;
      },
    });
    await verFicha(CNPJ);
    fireEvent.click(await screen.findByRole("button", { name: "Baixar em Excel" }));
    await waitFor(() => expect(clicar).toHaveBeenCalled());
    const [[endereco, pedido]] = buscar.mock.calls.filter(([e]) => String(e).endsWith("/planilha"));
    expect(String(endereco)).toBe(`${ROTA}/planilha`);
    expect(pedido?.method).toBe("POST");
    expect(JSON.parse(String(pedido?.body))).toEqual({ cnpj: CNPJ });
    expect(criar).toHaveBeenCalled();
    clicar.mockRestore();
  });
});
