// @vitest-environment jsdom
// Eventos da empresa na ficha (linha 798, PR 4): documentos à CVM e trocas de auditor, do mais novo ao
// mais velho, com a fonte e o dia de cada um, e "Carregar mais" com o cursor. Sem dado liberado ou sem
// eventos é uma frase da tela, nunca erro; se o pedido falha, a ficha segue sem a seção.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EventosDaEmpresaV1, FichaDaEmpresaV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA_DA_FICHA = "/api/v1/analista/ficha";
const ROTA_DOS_EVENTOS = "/api/v1/analista/ficha/eventos";
const SECAO = "Documentos à CVM e trocas de auditor";

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
const DOCUMENTO = {
  tipo: "ipe_filing",
  campos: {
    categoria: campo("Fato Relevante", "cvm-hist-ipe", "2025-05-02"),
    referencia: campo("2025-05-02", "cvm-hist-ipe", "2025-05-02"),
    link: campo("https://www.rad.cvm.gov.br/documento", "cvm-hist-ipe", "2025-05-02"),
  },
};
const TROCA = {
  tipo: "auditor_change",
  campos: {
    anterior: campo("AUDITORA UM", "cvm-hist-fca", "2025-05-31"),
    novo: campo("AUDITORA DOIS", "cvm-hist-fca", "2025-05-31"),
    efetiva_em: campo("2025-01-01", "cvm-hist-fca", "2025-05-31"),
  },
};
const PAGINA: EventosDaEmpresaV1 = {
  estado: "pronta",
  como_era_em: "2026-11-10",
  eventos: [DOCUMENTO, TROCA],
  cortada: false,
  proximo_cursor: null,
  fontes: [{ fonte: "cvm-hist-ipe", licenca: "CC-BY", atribuicao: "CVM, dados abertos" }],
  limites: ["Só o que a CVM classifica."],
};

afterEach(cleanup);

function abrir(eventos: (corpo: unknown) => Response) {
  return abrirApp("/ficha-da-empresa", {
    rotas: (endereco, init) => {
      if (endereco === ROTA_DA_FICHA) return respostaJson(200, FICHA);
      if (endereco === ROTA_DOS_EVENTOS) return eventos(JSON.parse(String(init?.body ?? "{}")));
      return undefined;
    },
  });
}

async function verFicha() {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
  fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
  await screen.findByRole("region", { name: "Cadastro na Receita" });
}

describe("eventos da ficha", () => {
  it("mostra os eventos com tipo, data, descrição, fonte e dia", async () => {
    abrir(() => respostaJson(200, PAGINA));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText("Documento à CVM")).toBeTruthy();
    expect(within(secao).getByText("Fato Relevante")).toBeTruthy();
    expect(within(secao).getByText("Troca de auditor")).toBeTruthy();
    expect(within(secao).getByText("AUDITORA UM → AUDITORA DOIS")).toBeTruthy();
    expect(within(secao).getByText("01/01/2025")).toBeTruthy();
    expect(within(secao).getByText("Só o que a CVM classifica.")).toBeTruthy();
    expect(within(secao).getByRole("link", { name: "abrir" }).getAttribute("href")).toBe(
      "https://www.rad.cvm.gov.br/documento",
    );
    expect(within(secao).queryByRole("button", { name: "Carregar mais" })).toBeNull();
  });

  it("não faz link de endereço que não seja https", async () => {
    const perigoso = { ...DOCUMENTO, campos: { ...DOCUMENTO.campos, link: campo("javascript:alert(1)", "x", "2025-05-02") } };
    abrir(() => respostaJson(200, { ...PAGINA, eventos: [perigoso] }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).queryByRole("link")).toBeNull();
  });

  it("carrega a página seguinte com o cursor e junta no fim da lista", async () => {
    const pedidos: unknown[] = [];
    abrir((corpo) => {
      pedidos.push(corpo);
      const cursor = (corpo as { cursor?: string }).cursor;
      return respostaJson(200, cursor ? { ...PAGINA, eventos: [TROCA], proximo_cursor: null } : { ...PAGINA, eventos: [DOCUMENTO], proximo_cursor: "abc" });
    });
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    fireEvent.click(await within(secao).findByRole("button", { name: "Carregar mais" }));
    await waitFor(() => expect(within(secao).getByText("Troca de auditor")).toBeTruthy());
    expect(within(secao).getByText("Documento à CVM")).toBeTruthy();
    expect(within(secao).queryByRole("button", { name: "Carregar mais" })).toBeNull();
    expect(pedidos[1]).toEqual({ cnpj: CNPJ, cursor: "abc" });
  });

  it("dado não liberado é uma frase da tela", async () => {
    abrir(() => respostaJson(200, { ...PAGINA, estado: "nao_liberada", eventos: [], fontes: [] }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/Dado ainda não liberado/)).toBeTruthy();
  });

  it("sem eventos diz isso em uma frase", async () => {
    abrir(() => respostaJson(200, { ...PAGINA, estado: "nao_disponivel", eventos: [], fontes: [] }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText(/Sem eventos desta empresa/)).toBeTruthy();
  });

  it("tipo não liberado não vira 'sem eventos' (linha 878)", async () => {
    abrir(() =>
      respostaJson(200, { ...PAGINA, eventos: [], fontes: [], tipos_nao_disponiveis: ["ipe_filing"] }),
    );
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).queryByText(/Sem eventos desta empresa/)).toBeNull();
    expect(within(secao).getByText("Nenhum evento dos tipos consultados.")).toBeTruthy();
    expect(within(secao).getByText(/os documentos à CVM ainda não estão liberados/)).toBeTruthy();
  });

  it("com um tipo não liberado, a lista que vem leva o aviso do outro", async () => {
    abrir(() => respostaJson(200, { ...PAGINA, eventos: [TROCA], tipos_nao_disponiveis: ["ipe_filing"] }));
    await verFicha();
    const secao = await screen.findByRole("region", { name: SECAO });
    expect(within(secao).getByText("Troca de auditor")).toBeTruthy();
    expect(within(secao).getByText(/os documentos à CVM ainda não estão liberados/)).toBeTruthy();
  });

  it("se o pedido falha, a ficha segue sem a seção", async () => {
    abrir(() => respostaJson(503, { detail: "A base não está disponível agora." }));
    await verFicha();
    expect(screen.getByRole("region", { name: "Cadastro na Receita" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: SECAO })).toBeNull();
  });
});
