// @vitest-environment jsdom
// Ficha da empresa (tela do analista, linha 798): os três estados da rota POST /v1/analista/ficha, com
// dados de mentira, e o Excel. O CNPJ vai no corpo do pedido, nunca no endereço; "sem prontidão" é um
// estado da tela ("dado ainda não liberado"), nunca um erro.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CampoComFonteV1, FichaDaEmpresaV1 } from "../../src/app/tipos";
import { abrirAba, abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA = "/api/v1/analista/ficha";
const LIMITES = [
  "Pessoa natural (MEI, empresário individual) não é servida.",
  "Nada aqui é recomendação de investimento.",
];

const O_QUE_VEM = [
  { titulo: "Cadastro na Receita Federal", fonte: "Receita Federal", o_que_traz: "Razão social e situação." },
  { titulo: "Entregas de balanço à CVM", fonte: "CVM", o_que_traz: "Só da companhia aberta." },
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
      mes_do_retrato: campo("2026-09"),
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
  o_que_vem: O_QUE_VEM,
};
const SEM_ENTREGAS: FichaDaEmpresaV1 = { ...PRONTA, ficha: { ...PRONTA.ficha!, entregas: null } };
const NAO_LIBERADA: FichaDaEmpresaV1 = {
  estado: "nao_liberada",
  ficha: null,
  fontes: [],
  limites: LIMITES,
  o_que_vem: O_QUE_VEM,
};
const NAO_DISPONIVEL: FichaDaEmpresaV1 = { ...NAO_LIBERADA, estado: "nao_disponivel" };

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
    await abrirAba("Cadastro");
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
    await abrirAba("Sinais");
    const entregas = screen.getByRole("region", { name: "Entregas de balanço à CVM" });
    expect(within(entregas).getByText("No prazo")).toBeTruthy();
    expect(within(entregas).getByText("cvm-hist-dfp")).toBeTruthy();
    await abrirAba("Fontes e limites");
    const fontes = screen.getByRole("region", { name: "Fontes" });
    expect(within(fontes).getByText(/Receita Federal do Brasil/)).toBeTruthy();
    const limites = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(limites).getByText(/recomendação de investimento/)).toBeTruthy();
    expect(screen.getByText(/como a base conhecia em 10\/11\/2026/)).toBeTruthy();
    expect(screen.getByText(/^CNPJ 02\.429\.144\/0001-93/)).toBeTruthy();
    expect(within(cadastro).getByRole("row", { name: /Mês do cadastro/ }).textContent).toContain("09/2026");
  });

  it("em abas: o nome da empresa é o título, o Resumo abre primeiro com a frase e os números, cada um com fonte e data", async () => {
    abrir(() => respostaJson(200, PRONTA));
    await verFicha(CNPJ);
    expect(await screen.findByRole("heading", { level: 1, name: "EMPRESA MODELO S.A." })).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 1, name: "Ficha da empresa" })).toBeNull();
    expect(screen.getAllByRole("tab").map((aba) => aba.textContent)).toEqual([
      "Resumo", "Cadastro", "Quem controla", "Sinais", "Eventos", "Vínculos", "Fontes e limites",
    ]);
    expect(screen.getByRole("tab", { name: "Resumo" }).getAttribute("aria-selected")).toBe("true");
    const resumo = screen.getByRole("region", { name: "Resumo da ficha" });
    expect(within(resumo).getByText(/consta como ativa na Receita desde 03\/11\/2005; é a matriz\./)).toBeTruthy();
    expect(within(resumo).getByText("Situação cadastral").closest(".numero-do-painel")?.textContent).toContain("Ativa");
    expect(within(resumo).getAllByText(/Fonte: rfb-cnpj · dado de 31\/10\/2026/).length).toBeGreaterThan(0);
    // o que a ficha não traz é dito, nunca um zero
    expect(within(resumo).getByText("Optante pelo Simples").closest(".numero-do-painel")?.textContent).toContain("Não temos");
  });

  it("só a aba aberta busca dado: os eventos só são pedidos quando a pessoa abre a aba", async () => {
    const { buscar } = abrir(() => respostaJson(200, PRONTA));
    await verFicha(CNPJ);
    await screen.findByRole("region", { name: "Resumo da ficha" });
    const dosEventos = () => buscar.mock.calls.filter(([e]) => String(e) === `${ROTA}/eventos`);
    expect(dosEventos()).toHaveLength(0);
    await abrirAba("Eventos");
    await waitFor(() => expect(dosEventos()).toHaveLength(1));
  });

  it("sem entregas: a frase fixa no lugar da tabela", async () => {
    abrir(() => respostaJson(200, SEM_ENTREGAS));
    await verFicha(CNPJ);
    await abrirAba("Sinais");
    const entregas = await screen.findByRole("region", { name: "Entregas de balanço à CVM" });
    expect(within(entregas).queryByRole("table")).toBeNull();
    expect(within(entregas).getByText(/Sem entregas nesta ficha/)).toBeTruthy();
  });

  it("documento não liberado não vira 'sem entregas' (linha 897)", async () => {
    abrir(() =>
      respostaJson(200, {
        ...PRONTA,
        ficha: { ...PRONTA.ficha!, entregas: [], entregas_nao_disponiveis: ["DFP", "ITR"] },
      }),
    );
    await verFicha(CNPJ);
    await abrirAba("Sinais");
    const entregas = await screen.findByRole("region", { name: "Entregas de balanço à CVM" });
    expect(within(entregas).queryByText(/Sem entregas nesta ficha/)).toBeNull();
    expect(within(entregas).getByText("Nenhuma entrega dos documentos consultados.")).toBeTruthy();
    // dois documentos
    expect(
      within(entregas).getByText(
        "Não consultados, por ainda não estarem liberados para a tela: os documentos DFP e os documentos ITR. A falta deles aqui não quer dizer que a empresa não os tenha entregado.",
      ),
    ).toBeTruthy();
  });

  it("com um documento não liberado, a tabela que vem leva o aviso do outro", async () => {
    abrir(() => respostaJson(200, { ...PRONTA, ficha: { ...PRONTA.ficha!, entregas_nao_disponiveis: ["ITR"] } }));
    await verFicha(CNPJ);
    await abrirAba("Sinais");
    const entregas = await screen.findByRole("region", { name: "Entregas de balanço à CVM" });
    expect(within(entregas).getByRole("table")).toBeTruthy();
    // um documento só: a frase concorda
    expect(within(entregas).getByText(/liberados para a tela: os documentos ITR\. A falta deles/)).toBeTruthy();
  });

  it("campo do cadastro não liberado aparece na seção, pelo nome da tela (linha 899)", async () => {
    abrir(() =>
      respostaJson(200, {
        ...PRONTA,
        ficha: {
          ...PRONTA.ficha!,
          campos_do_cadastro_nao_disponiveis: ["simples_nacional", "simples_nacional_since", "legal_name"],
        },
      }),
    );
    await verFicha(CNPJ);
    await abrirAba("Cadastro");
    const cadastro = await screen.findByRole("region", { name: "Cadastro na Receita" });
    // vários campos
    expect(
      within(cadastro).getByText(
        "Não consultados, por ainda não estarem liberados para a tela: os dados dos campos “Optante pelo Simples”, “Entrou no Simples em” e “Razão social”. A falta deles aqui não quer dizer que a empresa não tenha.",
      ),
    ).toBeTruthy();
  });

  it("com um campo do cadastro não liberado, a frase concorda; campo sem nome na tela aparece como veio", async () => {
    abrir(() =>
      respostaJson(200, {
        ...PRONTA,
        ficha: { ...PRONTA.ficha!, campos_do_cadastro_nao_disponiveis: ["registration_status_reason"] },
      }),
    );
    await verFicha(CNPJ);
    await abrirAba("Cadastro");
    const cadastro = await screen.findByRole("region", { name: "Cadastro na Receita" });
    expect(
      within(cadastro).getByText(
        "Não consultados, por ainda não estarem liberados para a tela: os dados do campo “Motivo da situação (código da Receita)”. A falta deles aqui não quer dizer que a empresa não tenha.",
      ),
    ).toBeTruthy();
    cleanup();
    abrir(() =>
      respostaJson(200, { ...PRONTA, ficha: { ...PRONTA.ficha!, campos_do_cadastro_nao_disponiveis: ["campo_novo"] } }),
    );
    await verFicha(CNPJ);
    await abrirAba("Cadastro");
    const outro = await screen.findByRole("region", { name: "Cadastro na Receita" });
    expect(within(outro).getByText(/liberados para a tela: os dados do campo “campo_novo”\./)).toBeTruthy();
  });

  it("o mês do retrato do cadastro tem nome na tela, na linha 'Não consultados' (linha 899)", async () => {
    abrir(() =>
      respostaJson(200, {
        ...PRONTA,
        ficha: { ...PRONTA.ficha!, campos_do_cadastro_nao_disponiveis: ["registry_snapshot_month"] },
      }),
    );
    await verFicha(CNPJ);
    await abrirAba("Cadastro");
    const cadastro = await screen.findByRole("region", { name: "Cadastro na Receita" });
    expect(
      within(cadastro).getByText(
        "Não consultados, por ainda não estarem liberados para a tela: os dados do campo “Mês do retrato do cadastro”. A falta deles aqui não quer dizer que a empresa não tenha.",
      ),
    ).toBeTruthy();
  });

  it("o mês do retrato do cadastro tem nome na tabela", async () => {
    abrir(() =>
      respostaJson(200, {
        ...PRONTA,
        ficha: {
          ...PRONTA.ficha!,
          cadastro_na_receita: {
            ...PRONTA.ficha!.cadastro_na_receita,
            mes_do_retrato_do_cadastro: campo("2026-08", "rfb-cnpj", "2026-09-30"),
          },
        },
      }),
    );
    await verFicha(CNPJ);
    await abrirAba("Cadastro");
    const cadastro = await screen.findByRole("region", { name: "Cadastro na Receita" });
    expect(within(cadastro).getByRole("row", { name: /Mês do retrato do cadastro/ }).textContent).toContain("08/2026");
    expect(within(cadastro).queryByText("mes_do_retrato_do_cadastro")).toBeNull();
  });

  it("cadastro todo consultado não leva a linha 'Não consultados'", async () => {
    abrir(() => respostaJson(200, { ...PRONTA, ficha: { ...PRONTA.ficha!, campos_do_cadastro_nao_disponiveis: [] } }));
    await verFicha(CNPJ);
    await abrirAba("Cadastro");
    const cadastro = await screen.findByRole("region", { name: "Cadastro na Receita" });
    expect(within(cadastro).queryByText(/Não consultados/)).toBeNull();
  });

  it("dado ainda não liberado: é estado da tela, sem alerta de erro e com os limites à vista", async () => {
    abrir(() => respostaJson(200, NAO_LIBERADA));
    await verFicha(CNPJ);
    expect(await screen.findByText(/Dado ainda não liberado/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    // o que a ficha vai trazer, com a fonte de cada bloco (Diretoria, 10/11): sem data nem número
    const vem = screen.getByRole("region", { name: "O que a ficha vai trazer" });
    const itens = within(vem).getAllByRole("listitem");
    expect(itens.map((i) => i.textContent)).toEqual([
      "Cadastro na Receita FederalRazão social e situação.Fonte: Receita Federal",
      "Entregas de balanço à CVMSó da companhia aberta.Fonte: CVM",
    ]);
    expect(screen.queryByRole("button", { name: "Baixar em Excel" })).toBeNull();
    expect(screen.getByRole("region", { name: "Limites e cuidados" })).toBeTruthy();
  });

  it("não disponível: uma frase só, sem dizer o motivo nem repetir o CNPJ", async () => {
    abrir(() => respostaJson(200, NAO_DISPONIVEL));
    await verFicha("11.222.333/0001-81");
    expect((await screen.findByRole("note")).textContent).toBe("Ficha não disponível para este CNPJ.");
    expect(screen.queryByRole("region", { name: "O que a ficha vai trazer" })).toBeNull();
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
