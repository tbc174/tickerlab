// @vitest-environment jsdom
// Aba "Quem já se mexeu" da tela do setor (linha 903, PR D): o setor vai no corpo do POST (nunca no endereço),
// cada linha leva fonte e data, o sinal que o portão não libera aparece como "não consultado", o que a rota não
// dá (contagem por UF, aberturas por ano) é dito à vista e o estado "não liberada" não vira "sem movimento".
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CompradoresDoSetorV1, PerfilDoSetorV1, SetoresV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const SETORES: SetoresV1 = { setores: [{ chave: "eletricas", nome: "Elétricas", empresas: 12, como_era_em: null }] };
const ROTA = "/api/v1/analista/setor/compradores";
const ROTA_DO_PERFIL = "/api/v1/analista/setor/perfil";

const PERFIL: PerfilDoSetorV1 = {
  estado: "pronta",
  cnae_principal: "6201501",
  como_era_em: "2026-11-12",
  data_do_retrato: "2026-10",
  publico_em: "2026-10-31",
  empresas_ativas: 12345,
  por_uf: [
    { uf: "SP", empresas_ativas: 8000 },
    { uf: "RJ", empresas_ativas: 1200 },
  ],
  aberturas_por_ano: [
    { ano: 2025, aberturas: 0 },
    { ano: 2026, aberturas: 70 },
  ],
  blocos_nao_disponiveis: [],
  fontes: [],
  limites: ["Só contagens."],
};

const campo = (valor: string) => ({ valor, fonte: "rfb-cnpj", publico_em: "2026-10-10", visto_em: null });

const PRONTA: CompradoresDoSetorV1 = {
  estado: "pronta",
  como_era_em: "2026-11-12",
  setor: { cnae_principal: "6201501", uf: "SP", anos: 5, desde: "2021-11-12", empresas_ativas: 3 },
  compradores: [
    {
      raiz_do_cnpj: "11111111",
      razao_social: campo("COMPRADORA S.A."),
      sinais: ["entrou_como_socio"],
      provas: {
        entrou_como_socio: {
          quantas: 2,
          exemplos: [
            {
              empresa_do_setor: { raiz_do_cnpj: "22222222", razao_social: campo("ALVO SP LTDA") },
              uf: "SP",
              ainda_socio: false,
              campos: { data_entrada: campo("2024-03-05") },
            },
          ],
        },
      },
    },
  ],
  total_de_compradores: 1,
  cortada: false,
  sinais_nao_disponiveis: ["controla_no_setor"],
  fontes: [{ fonte: "rfb-cnpj", licenca: "livre", atribuicao: "Receita Federal, CNPJ." }],
  limites: ["Movimento passado, não intenção de compra."],
};

function abrir(resposta: CompradoresDoSetorV1 | (() => Response), perfil: PerfilDoSetorV1 = PERFIL) {
  return abrirApp("/relatorio-do-setor?aba=quem-se-mexeu", {
    rotas: (endereco) => {
      if (endereco.startsWith("/api/v1/setores")) return respostaJson(200, SETORES);
      if (endereco === ROTA_DO_PERFIL) return respostaJson(200, perfil);
      if (endereco === ROTA) return typeof resposta === "function" ? resposta() : respostaJson(200, resposta);
      return undefined;
    },
  });
}

function preencher(cnae: string, uf = "", anos = "") {
  fireEvent.change(screen.getByLabelText("CNAE"), { target: { value: cnae } });
  fireEvent.change(screen.getByLabelText(/UF/), { target: { value: uf } });
  fireEvent.change(screen.getByLabelText(/Anos/), { target: { value: anos } });
  fireEvent.click(screen.getByRole("button", { name: "Ver quem já se mexeu" }));
}

const corpos = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.filter(([e]) => String(e) === ROTA).map(([, p]) => JSON.parse(String(p?.body)));

afterEach(() => cleanup());

describe("quem já se mexeu no setor", () => {
  it("sem pedido não busca nada e diz que é movimento passado", async () => {
    const { buscar } = abrir(PRONTA);
    await screen.findByLabelText("CNAE");
    expect(corpos(buscar)).toEqual([]);
    expect(screen.getByText(/não intenção de compra/)).toBeTruthy();
  });

  it("pronta: o setor vai no corpo, a linha traz nome, CNPJ parcial, data e fonte", async () => {
    const { buscar } = abrir(PRONTA);
    await screen.findByLabelText("CNAE");
    preencher("6201501", "sp", "5");
    const tabela = await screen.findByRole("region", { name: "Quem já se mexeu neste setor" });
    expect(corpos(buscar)).toEqual([{ cnae: "6201501", uf: "SP", anos: 5 }]);
    expect(buscar.mock.calls.every(([e]) => !String(e).includes("6201501"))).toBe(true);
    expect(within(tabela).getByText("COMPRADORA S.A.")).toBeTruthy();
    expect(within(tabela).getByText("CNPJ 11111111/…")).toBeTruthy();
    expect(within(tabela).getByText(/ALVO SP LTDA \(SP\) · já saiu/)).toBeTruthy();
    expect(within(tabela).getByText(/05\/03\/2024/)).toBeTruthy();
    expect(within(tabela).getByText(/Fonte: rfb-cnpj · dado de 10\/10\/2026/)).toBeTruthy();
    expect(screen.getByText(/Receita Federal, CNPJ\./)).toBeTruthy();
  });

  it("diz o sinal não consultado e o que a lista não traz, e mantém os limites", async () => {
    abrir(PRONTA);
    await screen.findByLabelText("CNAE");
    preencher("6201501");
    await screen.findByText(/Não consultados nesta base: Companhia aberta com controlada no setor/);
    expect(screen.getByRole("heading", { name: "O que não temos aqui" })).toBeTruthy();
    const limites = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(limites).getByText(/Movimento passado/)).toBeTruthy();
  });

  it("lista vazia usa a frase do vazio, sem tabela", async () => {
    abrir({ ...PRONTA, compradores: [], total_de_compradores: 0, sinais_nao_disponiveis: [] });
    await screen.findByLabelText("CNAE");
    preencher("6201501");
    await screen.findByText(/Nenhuma empresa com esse movimento/);
  });

  it("não liberada não vira 'sem movimento'", async () => {
    abrir({ ...PRONTA, estado: "nao_liberada", setor: null, compradores: [], total_de_compradores: 0 });
    await screen.findByLabelText("CNAE");
    preencher("6201501");
    await screen.findByText(/ainda não foi liberado/);
    expect(screen.queryByText(/Nenhuma empresa com esse movimento/)).toBeNull();
  });

  it.each([
    ["62", "", "", /CNAE com 5 ou 7/],
    ["6201501", "XYZ", "", /UF tem 2 letras/],
    ["6201501", "", "11", /de 1 a 10/],
  ])("pedido fora da forma não vai ao servidor: %s %s %s", async (cnae, uf, anos, aviso) => {
    const { buscar } = abrir(PRONTA);
    await screen.findByLabelText("CNAE");
    preencher(cnae, uf, anos);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(aviso));
    expect(corpos(buscar)).toEqual([]);
  });

  it("a aba das companhias abertas continua a primeira e a outra não busca antes de abrir", async () => {
    const { buscar } = abrirApp("/relatorio-do-setor", {
      rotas: (endereco) => (endereco.startsWith("/api/v1/setores") ? respostaJson(200, SETORES) : undefined),
    });
    await screen.findByRole("tab", { name: "Quem já se mexeu" });
    expect(screen.getByRole("tab", { name: "Companhias abertas" }).getAttribute("aria-selected")).toBe("true");
    expect(corpos(buscar)).toEqual([]);
  });

  it("os números do setor: total, UF e aberturas com fonte e data, o CNAE só no corpo e o limite do MEI", async () => {
    const { buscar } = abrir(PRONTA);
    await screen.findByLabelText("CNAE");
    preencher("6201501");
    const numeros = await screen.findByRole("region", { name: /Números do setor/ });
    expect(within(numeros).getByText("12.345")).toBeTruthy();
    const uf = within(numeros).getByRole("region", { name: "Empresas ativas do setor por UF" });
    expect(within(uf).getByText("8.000")).toBeTruthy();
    expect(within(numeros).getByRole("region", { name: "Aberturas de empresas do setor por ano" })).toBeTruthy();
    expect(within(numeros).getAllByText(/Receita Federal \(cadastro do CNPJ\) · dado de out\/2026/).length).toBeGreaterThan(0);
    expect(within(numeros).getByText(/MEI e empresário individual não entram/)).toBeTruthy();
    expect(within(numeros).getByText(/A soma das UFs pode passar do total/)).toBeTruthy();
    const pedidos = buscar.mock.calls.filter(([e]) => String(e) === ROTA_DO_PERFIL);
    expect(JSON.parse(String(pedidos[0][1]?.body))).toEqual({ cnae: "6201501" });
  });

  it("bloco não consultado diz 'Não consultado', nunca zero; não liberada não vira setor vazio", async () => {
    abrir(PRONTA, { ...PERFIL, por_uf: null, blocos_nao_disponiveis: ["por_uf"] });
    await screen.findByLabelText("CNAE");
    preencher("6201501");
    await screen.findByText(/Não consultado nesta base/);
    cleanup();
    abrir(PRONTA, { ...PERFIL, estado: "nao_liberada", empresas_ativas: null, por_uf: null, aberturas_por_ano: null });
    await screen.findByLabelText("CNAE");
    preencher("6201501");
    await screen.findByText(/ainda não foram liberados nesta base/);
  });
});
