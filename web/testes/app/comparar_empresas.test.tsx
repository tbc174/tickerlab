// @vitest-environment jsdom
// Comparar empresas (tela do analista, linha 798): os estados da rota POST /v1/analista/comparar, com dados de
// mentira, o Excel e a ida da ficha para a comparação. Os CNPJs vão no corpo do pedido (e, vindos da ficha, pelo
// estado da navegação), nunca no endereço; "sem prontidão" é um estado da tela, nunca um erro.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  CampoComFonteV1,
  ComparacaoDeEmpresasV1,
  EmpresaComparadaV1,
  FichaDaEmpresaV1,
} from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const ROTA = "/api/v1/analista/comparar";
const EMPRESA = "02429144000193";
const OUTRA = "11222333000181";
const LIMITES = [
  "Capital social e número de estabelecimentos ativos são só uma aproximação do tamanho.",
  "Nada aqui é recomendação de investimento.",
];

function campo(valor: CampoComFonteV1["valor"], fonte = "rfb-cnpj", publico_em = "2026-10-31"): CampoComFonteV1 {
  return { valor, fonte, publico_em, visto_em: null };
}

const NAO_DISPONIVEL = (cnpj: string): EmpresaComparadaV1 => ({
  cnpj,
  estado: "nao_disponivel",
  razao_social: null,
  situacao_cadastral: null,
  data_situacao_cadastral: null,
  motivo_situacao: null,
  natureza_juridica: null,
  matriz: null,
  mes_do_retrato: null,
  optante_simples: null,
  data_opcao_simples: null,
  data_exclusao_simples: null,
  porte: null,
  data_inicio_atividade: null,
  cnae_principal: null,
  uf: null,
  municipio: null,
  capital_social: null,
  n_estabelecimentos: null,
  porte_descricao: null,
  cnae_descricao: null,
  municipio_nome: null,
  ultima_entrega_documento: null,
  ultima_entrega_referencia: null,
  ultima_entrega_situacao: null,
  entregas_conhecidas: null,
  entregas_com_atraso: null,
});

const MODELO: EmpresaComparadaV1 = {
  ...NAO_DISPONIVEL(EMPRESA),
  estado: "pronta",
  razao_social: campo("EMPRESA MODELO S.A.", "rfb-cnpj", "2026-09-30"),
  situacao_cadastral: campo("02"),
  porte: campo("other", "rfb-cnpj-busca"),
  porte_descricao: "Demais",
  data_inicio_atividade: campo("2010-05-01", "rfb-cnpj-busca"),
  cnae_principal: campo("3514000", "rfb-cnpj-busca"),
  cnae_descricao: "Distribuição de energia elétrica",
  uf: campo("MG", "rfb-cnpj-busca"),
  municipio: campo("4123", "rfb-cnpj-busca"),
  municipio_nome: "BELO HORIZONTE",
  capital_social: campo(6000000, "rfb-cnpj-busca"),
  n_estabelecimentos: campo(3, "rfb-cnpj-busca"),
  ultima_entrega_documento: campo("DFP", "cvm-hist-dfp", "2026-03-20"),
  ultima_entrega_situacao: campo("severely_late", "cvm-hist-dfp", "2026-03-20"),
  entregas_conhecidas: 9,
  entregas_com_atraso: 2,
};

const PRONTA: ComparacaoDeEmpresasV1 = {
  estado: "pronta",
  como_era_em: "2026-11-10",
  empresas: [MODELO, NAO_DISPONIVEL(OUTRA)],
  fontes: [{ fonte: "rfb-cnpj", licenca: "CC BY 4.0", atribuicao: "Receita Federal do Brasil" }],
  limites: LIMITES,
};
const NAO_LIBERADA: ComparacaoDeEmpresasV1 = {
  estado: "nao_liberada",
  como_era_em: null,
  empresas: [],
  fontes: [],
  limites: LIMITES,
};

function abrir(resposta: () => Response, endereco = "/comparar-empresas") {
  return abrirApp(endereco, {
    rotas: (pedido) => (pedido === ROTA ? resposta() : undefined),
  });
}

const pedidos = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.filter(([e]) => String(e).startsWith("/api/v1/analista"));

async function comparar(...cnpjs: string[]) {
  await screen.findByLabelText("CNPJ 1");
  for (let i = 2; i < cnpjs.length; i++) fireEvent.click(screen.getByRole("button", { name: "Mais uma empresa" }));
  cnpjs.forEach((cnpj, i) => fireEvent.change(screen.getByLabelText(`CNPJ ${i + 1}`), { target: { value: cnpj } }));
  fireEvent.click(screen.getByRole("button", { name: "Comparar" }));
}

afterEach(() => {
  cleanup();
});

describe("comparar empresas", () => {
  it("abre com dois campos e não pede nada antes de a pessoa comparar", async () => {
    const { buscar } = abrir(() => respostaJson(200, PRONTA));
    await screen.findByLabelText("CNPJ 1");
    expect(screen.getByLabelText("CNPJ 2")).toBeTruthy();
    expect(screen.queryByLabelText("CNPJ 3")).toBeNull();
    expect(pedidos(buscar)).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Comparar empresas" })).toBeTruthy();
    expect(screen.getByText(/Pessoa física, MEI e empresário individual não aparecem/)).toBeTruthy();
  });

  it("até cinco campos; com mais de dois, cada um pode sair", async () => {
    abrir(() => respostaJson(200, PRONTA));
    await screen.findByLabelText("CNPJ 1");
    expect(screen.queryByRole("button", { name: /Tirar/ })).toBeNull();
    for (let i = 0; i < 3; i++) fireEvent.click(screen.getByRole("button", { name: "Mais uma empresa" }));
    expect(screen.getByLabelText("CNPJ 5")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mais uma empresa" })).toBeNull();
    fireEvent.change(screen.getByLabelText("CNPJ 5"), { target: { value: "quinto" } });
    fireEvent.click(screen.getByRole("button", { name: "Tirar o CNPJ 1" }));
    expect(screen.queryByLabelText("CNPJ 5")).toBeNull();
    expect((screen.getByLabelText("CNPJ 4") as HTMLInputElement).value).toBe("quinto");
  });

  it("duas empresas prontas: o que uma não tem é dito na célula, e a coluna traz o nome", async () => {
    const SEM_UF: EmpresaComparadaV1 = { ...MODELO, cnpj: OUTRA, razao_social: campo("OUTRA EMPRESA LTDA"), uf: null, entregas_conhecidas: null, entregas_com_atraso: null };
    abrir(() => respostaJson(200, { ...PRONTA, empresas: [MODELO, SEM_UF] }));
    await comparar(EMPRESA, OUTRA);
    const linha = await screen.findByRole("row", { name: /^UF/ });
    expect(linha.textContent).toContain("MG");
    expect(linha.textContent).toContain("Não temos");
    expect(linha.textContent).not.toContain("—");
    expect(screen.getByRole("columnheader", { name: /OUTRA EMPRESA LTDA/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Encontre empresas/ })).toBeTruthy();
  });

  it("pronta: os CNPJs vão no corpo, uma coluna por empresa, cada valor com a fonte e a data", async () => {
    const { buscar } = abrir(() => respostaJson(200, PRONTA));
    await comparar("02.429.144/0001-93", OUTRA);
    const tabela = await screen.findByRole("region", { name: "Lado a lado" });
    const [[endereco, pedido]] = pedidos(buscar);
    expect(String(endereco)).toBe(ROTA);
    expect(pedido?.method).toBe("POST");
    expect(JSON.parse(String(pedido?.body))).toEqual({ cnpjs: ["02.429.144/0001-93", OUTRA] });
    const cabecalhos = within(tabela).getAllByRole("columnheader").map((c) => c.textContent);
    expect(cabecalhos).toEqual(["Campo", "EMPRESA MODELO S.A.02.429.144/0001-93", "11.222.333/0001-81 · não disponível"]);
    const razao = within(tabela).getByRole("row", { name: /Razão social/ });
    expect(razao.textContent).toContain("EMPRESA MODELO S.A.");
    expect(razao.textContent).toContain("rfb-cnpj · 30/09/2026");
    expect(razao.textContent).toContain("Não disponível"); // a empresa fora da base diz que não está disponível, sem motivo
    const linha = (nome: RegExp) => within(tabela).getByRole("row", { name: nome }).textContent ?? "";
    expect(linha(/Situação cadastral/)).toContain("Ativa");
    expect(linha(/Porte/)).toContain("Demais");
    expect(linha(/Abertura/)).toContain("01/05/2010");
    expect(linha(/Atividade principal/)).toContain("3514000 · Distribuição de energia elétrica");
    expect(linha(/Município/)).toContain("BELO HORIZONTE");
    expect(linha(/Capital social declarado \(aproximação do tamanho\)/)).toMatch(/R\$\s6\.000\.000/);
    expect(linha(/Estabelecimentos ativos \(aproximação do tamanho\)/)).toContain("3");
    expect(linha(/Situação da última entrega/)).toContain("Atraso grave");
    expect(linha(/Entregas à CVM com atraso/)).toContain("2 de 9");
    // campo sem valor em nenhuma empresa não vira linha
    expect(within(tabela).queryByRole("row", { name: /Saiu do Simples/ })).toBeNull();
    expect(screen.getByText(/Como a base conhecia em 10\/11\/2026/)).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Fontes" })).getByText(/Receita Federal do Brasil/)).toBeTruthy();
    const limites = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(limites).getByText(/aproximação do tamanho/)).toBeTruthy();
  });

  it("dado ainda não liberado: estado da tela, sem alerta, sem Excel e com os limites à vista", async () => {
    abrir(() => respostaJson(200, NAO_LIBERADA));
    await comparar(EMPRESA, OUTRA);
    expect((await screen.findByRole("note")).textContent).toMatch(/Dado ainda não liberado/);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Baixar em Excel" })).toBeNull();
    expect(screen.getByRole("region", { name: "Limites e cuidados" })).toBeTruthy();
  });

  it("nenhuma disponível: sem Excel e uma frase só, sem dizer o motivo", async () => {
    const nenhuma = { ...PRONTA, empresas: [NAO_DISPONIVEL(EMPRESA), NAO_DISPONIVEL(OUTRA)], fontes: [] };
    abrir(() => respostaJson(200, nenhuma));
    await comparar(EMPRESA, OUTRA);
    expect((await screen.findByRole("note")).textContent).toBe("Nenhuma das empresas pedidas está disponível na base.");
    expect(screen.queryByRole("button", { name: "Baixar em Excel" })).toBeNull();
  });

  it("pedido fora da regra (422): mostra a mensagem da API", async () => {
    abrir(() => respostaJson(422, { detail: "Escolha de 2 a 5 CNPJs diferentes, cada um com 14 caracteres." }));
    await comparar(EMPRESA, EMPRESA);
    expect((await screen.findByRole("alert")).textContent).toContain("Escolha de 2 a 5 CNPJs diferentes");
  });

  it("Baixar em Excel: pede a planilha por POST com os mesmos CNPJs no corpo", async () => {
    const criar = vi.fn(() => "blob:xlsx");
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: vi.fn() });
    const clicar = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { buscar } = abrirApp("/comparar-empresas", {
      rotas: (endereco) => {
        if (endereco === `${ROTA}/planilha`) return new Response("PK", { status: 200 });
        return endereco === ROTA ? respostaJson(200, PRONTA) : undefined;
      },
    });
    await comparar(EMPRESA, OUTRA);
    fireEvent.click(await screen.findByRole("button", { name: "Baixar em Excel" }));
    await waitFor(() => expect(clicar).toHaveBeenCalled());
    const [[endereco, pedido]] = buscar.mock.calls.filter(([e]) => String(e).endsWith("/planilha"));
    expect(String(endereco)).toBe(`${ROTA}/planilha`);
    expect(pedido?.method).toBe("POST");
    expect(JSON.parse(String(pedido?.body))).toEqual({ cnpjs: [EMPRESA, OUTRA] });
    clicar.mockRestore();
  });

  it("da ficha: 'Pôr na comparação' leva o CNPJ pelo estado da navegação, sem pedir nada ainda", async () => {
    const ficha: FichaDaEmpresaV1 = {
      estado: "pronta",
      ficha: {
        cnpj: EMPRESA,
        como_era_em: "2026-11-10",
        cadastro_na_receita: { razao_social: campo("EMPRESA MODELO S.A.") },
        entregas: null,
      },
      fontes: [],
      limites: LIMITES,
      o_que_vem: [],
    };
    const { buscar } = abrirApp("/ficha-da-empresa", {
      rotas: (endereco) => {
        if (endereco === "/api/v1/analista/ficha") return respostaJson(200, ficha);
        return endereco === ROTA ? respostaJson(200, PRONTA) : undefined;
      },
    });
    fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: EMPRESA } });
    fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
    const link = await screen.findByRole("link", { name: "Pôr na comparação" });
    expect(link.getAttribute("href")).toBe("/comparar-empresas"); // o CNPJ não vai no endereço
    fireEvent.click(link);
    expect(((await screen.findByLabelText("CNPJ 1")) as HTMLInputElement).value).toBe(EMPRESA);
    expect((screen.getByLabelText("CNPJ 2") as HTMLInputElement).value).toBe("");
    expect(buscar.mock.calls.filter(([e]) => String(e) === ROTA)).toHaveLength(0);
  });
});

describe("tipos da comparação", () => {
  const esquemas = JSON.parse(
    readFileSync(join(process.cwd(), "..", "docs", "api", "openapi-v1.json"), "utf8"),
  ).components.schemas;
  const campos = (nome: string) => Object.keys(esquemas[nome].properties).sort();

  it("ComparacaoDeEmpresasV1 e EmpresaComparadaV1 batem com o OpenAPI", () => {
    expect(Object.keys(PRONTA).sort()).toEqual(campos("ComparacaoDeEmpresasV1"));
    expect(Object.keys(MODELO).sort()).toEqual(campos("EmpresaComparadaV1"));
  });
});
