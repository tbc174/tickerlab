// @vitest-environment jsdom
// Vínculos da empresa na ficha (linha 798, PR 5): controle, coligação, participação e auditoria, com a fonte
// e o dia de cada um. Sem dado liberado ou sem vínculos é uma frase da tela, nunca erro; se o pedido falha,
// a ficha segue sem a seção.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FichaDaEmpresaV1, VinculosDaEmpresaV1 } from "../../src/app/tipos";
import { abrirAba, abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA_DA_FICHA = "/api/v1/analista/ficha";
const ROTA_DOS_VINCULOS = "/api/v1/analista/ficha/vinculos";
const SECAO = "Vínculos com outras empresas";

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

const campo = (valor: string, fonte: string, publico_em: string) => ({ valor, fonte, publico_em, visto_em: null });
const nome = (valor: string) => campo(valor, "rfb-cnpj", "2026-09-30");
const CONTROLADA = {
  salto: 1,
  de: { raiz_do_cnpj: "02429144", razao_social: nome("EMPRESA MODELO S.A.") },
  para: { raiz_do_cnpj: "11222333", razao_social: nome("HOLDING UM S.A.") },
  campos: {
    tipo: campo("subsidiary_of", "cvm-hist-fre", "2025-06-30"),
    participacao_no_capital: campo("60", "cvm-hist-fre", "2025-06-30"),
    aconteceu_em: campo("2024-03-01", "cvm-hist-fre", "2025-06-30"),
  },
};
const AUDITORIA = {
  salto: 1,
  de: { raiz_do_cnpj: "44555666", razao_social: null },
  para: { raiz_do_cnpj: "02429144", razao_social: nome("EMPRESA MODELO S.A.") },
  campos: { tipo: campo("audits", "cvm-hist-fca", "2025-05-31") },
};
const PAGINA: VinculosDaEmpresaV1 = {
  estado: "pronta",
  como_era_em: "2026-11-10",
  vinculos: [CONTROLADA, AUDITORIA],
  cortada: false,
  fontes: [{ fonte: "cvm-hist-fre", licenca: "CC-BY", atribuicao: "CVM, dados abertos" }],
  limites: ["Só o que a companhia declara à CVM."],
};

afterEach(cleanup);

function abrir(vinculos: () => Response) {
  return abrirApp("/ficha-da-empresa", {
    rotas: (endereco) => {
      if (endereco === ROTA_DA_FICHA) return respostaJson(200, FICHA);
      if (endereco === ROTA_DOS_VINCULOS) return vinculos();
      return undefined;
    },
  });
}

async function verFicha() {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
  fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
  await abrirAba("Vínculos");
}

describe("vínculos da ficha", () => {
  it("mostra cada vínculo com os dois lados, a fonte e o dia", async () => {
    abrir(() => respostaJson(200, PAGINA));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText("Controlada de")).toBeTruthy();
    expect(within(secao).getByText("Auditora de")).toBeTruthy();
    expect(within(secao).getByText("HOLDING UM S.A. (CNPJ 11222333/…)")).toBeTruthy();
    expect(within(secao).getByText("CNPJ 44555666/…")).toBeTruthy();
    expect(within(secao).getByText("60%")).toBeTruthy();
    expect(within(secao).getByText("01/03/2024")).toBeTruthy();
    expect(within(secao).getByText("Só o que a companhia declara à CVM.")).toBeTruthy();
    expect(within(secao).getByText(/CVM, dados abertos \(cvm-hist-fre\)/)).toBeTruthy();
  });

  it("avisa quando a lista foi cortada", async () => {
    abrir(() => respostaJson(200, { ...PAGINA, cortada: true }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/cortada no limite/)).toBeTruthy();
  });

  it("dado não liberado é uma frase da tela", async () => {
    abrir(() => respostaJson(200, { ...PAGINA, estado: "nao_liberada", vinculos: [], fontes: [] }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/Dado ainda não liberado/)).toBeTruthy();
  });

  it("sem vínculos diz isso em uma frase", async () => {
    abrir(() => respostaJson(200, { ...PAGINA, estado: "nao_disponivel", vinculos: [], fontes: [] }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/Sem vínculos desta empresa/)).toBeTruthy();
  });

  it("tipo não liberado não vira 'sem vínculos' (linha 889)", async () => {
    abrir(() =>
      respostaJson(200, { ...PAGINA, vinculos: [], fontes: [], tipos_de_vinculo_nao_disponiveis: ["audits"] }),
    );
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).queryByText(/Sem vínculos desta empresa/)).toBeNull();
    expect(within(secao).getByText("Nenhum vínculo dos tipos consultados.")).toBeTruthy();
    // um tipo só: a frase concorda
    expect(
      within(secao).getByText(
        "Não consultados, por ainda não estarem liberados para a tela: os vínculos de auditoria. A falta deles aqui não quer dizer que a empresa não tenha.",
      ),
    ).toBeTruthy();
  });

  it("com um tipo não liberado, a lista que vem leva o aviso do outro", async () => {
    abrir(() =>
      respostaJson(200, {
        ...PAGINA,
        vinculos: [CONTROLADA],
        tipos_de_vinculo_nao_disponiveis: ["subsidiary_of", "affiliate_of", "investee_of"],
      }),
    );
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByRole("table")).toBeTruthy();
    // vários tipos: a mesma frase concorda
    expect(
      within(secao).getByText(
        /liberados para a tela: os vínculos de controle e os vínculos de coligação e os vínculos de participação\./,
      ),
    ).toBeTruthy();
  });

  it("tudo consultado: nenhum aviso de tipo de fora", async () => {
    abrir(() => respostaJson(200, { ...PAGINA, tipos_de_vinculo_nao_disponiveis: [] }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).queryByText(/Não consultados/)).toBeNull();
  });

  it("se o pedido falha, a ficha segue sem a seção", async () => {
    abrir(() => respostaJson(503, { detail: "A base não está disponível agora." }));
    await verFicha();
    expect(screen.getByRole("tablist")).toBeTruthy();
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
  });
});
