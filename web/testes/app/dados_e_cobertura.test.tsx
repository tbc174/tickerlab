// @vitest-environment jsdom
// Dados e cobertura (linha 832): as tabelas que a API declara, por módulo, e nada além disso.
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { DadosECoberturaV1, TabelaDaCoberturaV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

function tabela(nome: string, modulo: string): TabelaDaCoberturaV1 {
  return {
    tabela: nome,
    modulo,
    frase: `Frase de ${nome}.`,
    fonte: `Fonte de ${nome}`,
    orgao: "Órgão X",
    licenca: "dado aberto",
    historico_desde: "2019",
    frequencia: "mensal",
    situacao_da_licenca: "licenciada",
    n_colunas: 4,
  };
}

const DADOS: DadosECoberturaV1 = {
  tabelas: [tabela("empresas", "Empresas"), tabela("socios", "Empresas"), tabela("multas", "Sanções")],
};
const ENDERECO = "/api/v1/dados-e-cobertura";

afterEach(cleanup);

describe("dados e cobertura", () => {
  it("agrupa por módulo, na ordem do catálogo, com fonte, licença, histórico e atualização", async () => {
    abrirApp("/dados-e-cobertura", {
      rotas: (endereco) => (endereco === ENDERECO ? respostaJson(200, DADOS) : undefined),
    });
    const grupos = await screen.findAllByRole("region", {}, { timeout: 5000 });
    expect(screen.getByText(/só as tabelas que já passaram na conferência de prontidão/)).toBeTruthy();
    expect(grupos.map((g) => g.getAttribute("aria-label"))).toEqual(["Empresas", "Sanções"]);
    const linhas = within(grupos[0]).getAllByRole("row");
    expect(linhas).toHaveLength(3); // cabeçalho + 2 tabelas
    expect(within(linhas[1]).getByText("empresas")).toBeTruthy();
    expect(within(linhas[1]).getByText("Fonte de empresas")).toBeTruthy();
    expect(within(linhas[1]).getByText("Órgão X: dado aberto")).toBeTruthy();
    expect(within(linhas[1]).getByText("2019")).toBeTruthy();
    expect(within(linhas[1]).getByText("mensal")).toBeTruthy();
  });

  it("sem nenhuma tabela: uma frase, não uma tabela vazia, e nenhuma promessa de cobertura", async () => {
    abrirApp("/dados-e-cobertura", {
      rotas: (endereco) => (endereco === ENDERECO ? respostaJson(200, { tabelas: [] }) : undefined),
    });
    expect(await screen.findByText(/nenhuma tabela para mostrar/, {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/cobertura de \d/i)).toBeNull();
  });

  it("a API fora do ar mostra o erro da tela", async () => {
    abrirApp("/dados-e-cobertura", {
      rotas: (endereco) => (endereco === ENDERECO ? respostaJson(500, { detail: "falhou" }) : undefined),
    });
    expect(await screen.findByRole("alert", {}, { timeout: 5000 })).toBeTruthy();
  });
});
