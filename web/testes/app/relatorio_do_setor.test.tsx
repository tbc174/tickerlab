// @vitest-environment jsdom
// Relatório do setor no app novo (molde D, PR 4): as rotas GET /v1/setores e /v1/relatorio-setor, com
// dados de mentira. O setor vai no endereço (não é dado pessoal); "O que não temos" e os limites
// ficam sempre à vista.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RelatorioDoSetorV1, SecaoDoRelatorioV1, SetoresV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const SETORES: SetoresV1 = {
  setores: [
    { chave: "eletricas", nome: "Elétricas", empresas: 12, como_era_em: "2026-10-17" },
    { chave: "telecom", nome: "Telecom", empresas: 3, como_era_em: null },
  ],
};

function secao(chave: string, titulo: string, trancada = false): SecaoDoRelatorioV1 {
  return {
    chave,
    titulo,
    itens: [],
    paragrafos: trancada ? ["Esta seção é do plano Pro."] : [`Texto de ${titulo}.`],
    tabelas: trancada
      ? []
      : [
          {
            chave: `${chave}-t`,
            titulo: `Tabela de ${titulo}`,
            colunas: ["Ano", "HHI", "Faixa"],
            linhas: [["2025", "1.200", "não concentrado"]],
          },
        ],
    trancada,
  };
}

const RELATORIO: RelatorioDoSetorV1 = {
  setor: "eletricas",
  nome: "Elétricas",
  como_era_em: "2026-10-17",
  membros: [
    { cnpj: "02429144000193", empresa: "CPFL Energia S.A.", tickers: ["CPFE3"], motivo: "ligada à ANEEL por 2 entidades" },
  ],
  secoes: [secao("concentracao", "Concentração"), secao("lado_a_lado", "Lado a lado")],
  frases: [{ texto: "O HHI de 2025 ficou na faixa não concentrado.", ids: ["hhi_aneel_consumidores"] }],
  nao_temos: [{ kpi: "DEC e FEC", motivo: "a base não tem a série.", fonte: "ANEEL, indicadores de qualidade" }],
  fontes: ["ANEEL, SAMP"],
  limites: ["O mercado nacional não é o mercado relevante do CADE.", "Nada aqui é recomendação de investimento."],
  avisos: [],
};
const TRANCADO: RelatorioDoSetorV1 = {
  ...RELATORIO,
  secoes: [secao("concentracao", "Concentração", true), secao("lado_a_lado", "Lado a lado", true)],
  frases: [],
};

function abrir(relatorio: (endereco: string) => Response) {
  return abrirApp("/relatorio-do-setor", {
    rotas: (endereco) => {
      if (endereco.startsWith("/api/v1/setores")) return respostaJson(200, SETORES);
      if (endereco.startsWith("/api/v1/relatorio-setor")) return relatorio(endereco);
      return undefined;
    },
  });
}

afterEach(() => {
  cleanup();
});

describe("relatório do setor", () => {
  it("abre no primeiro setor, com membros, frases, seções, o que não temos, fontes e limites", async () => {
    const { buscar } = abrir(() => respostaJson(200, RELATORIO));
    await screen.findByRole("heading", { name: "Concentração" });
    const pedidos = buscar.mock.calls.filter(([e]) => String(e).startsWith("/api/v1/relatorio-setor"));
    expect(String(pedidos[0][0])).toBe("/api/v1/relatorio-setor?setor=eletricas");
    expect(screen.getByRole("heading", { name: /Quem está no setor \(1\)/ })).toBeTruthy();
    expect(screen.getByText("CPFL Energia S.A.")).toBeTruthy();
    expect(screen.getByText(/ligada à ANEEL por 2 entidades/)).toBeTruthy();
    expect(screen.getByText(/17\/10\/2026/)).toBeTruthy();
    expect(screen.getByText(/faixa não concentrado/)).toBeTruthy();
    expect(screen.getByText("Tabela de Concentração")).toBeTruthy();
    const naoTemos = screen.getByRole("region", { name: "O que não temos" });
    expect(within(naoTemos).getByText(/DEC e FEC/)).toBeTruthy();
    expect(within(naoTemos).getByText(/qualidade/)).toBeTruthy();
    expect(screen.getByText(/ANEEL, SAMP/)).toBeTruthy();
    const limites = screen.getByRole("region", { name: "Limites e cuidados" });
    expect(within(limites).getByText(/recomendação de investimento/)).toBeTruthy();
  });

  it("trocar o setor pede o relatório do outro setor", async () => {
    const { buscar } = abrir((endereco) =>
      respostaJson(
        200,
        endereco.includes("telecom") ? { ...RELATORIO, setor: "telecom", nome: "Telecom", membros: [] } : RELATORIO,
      ),
    );
    await screen.findByRole("heading", { name: "Concentração" });
    fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "telecom" } });
    await screen.findByText(/ainda não trouxe companhias abertas/);
    expect(buscar.mock.calls.some(([e]) => String(e) === "/api/v1/relatorio-setor?setor=telecom")).toBe(true);
  });

  it("trancado pelo plano: só os títulos e um único convite; o que não temos e os limites continuam", async () => {
    abrir(() => respostaJson(200, TRANCADO));
    await screen.findByRole("heading", { name: "Lado a lado" });
    expect(screen.getAllByText("Esta seção é do plano Pro.")).toHaveLength(2);
    expect(screen.queryByText("Tabela de Concentração")).toBeNull();
    expect(screen.getAllByRole("link", { name: "Conhecer o plano Pro" })).toHaveLength(1);
    expect(screen.getByRole("region", { name: "O que não temos" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Limites e cuidados" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "O que os dados mostram" })).toBeNull();
  });

  it("setor que a API não conhece (404): mostra a mensagem da API", async () => {
    abrir(() => respostaJson(404, { detail: "Setor fora da lista do relatório do setor (veja /v1/setores)." }));
    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("Setor fora da lista");
  });

  it("Baixar PDF: pede o PDF do setor escolhido por GET, com o setor no endereço, e entrega o arquivo", async () => {
    const criar = vi.fn(() => "blob:pdf");
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: vi.fn() });
    const clicar = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { buscar } = abrirApp("/relatorio-do-setor", {
      rotas: (endereco) => {
        if (endereco.startsWith("/api/v1/setores")) return respostaJson(200, SETORES);
        if (endereco.startsWith("/api/v1/relatorio-setor/pdf")) {
          return new Response("%PDF-1.7", { status: 200, headers: { "content-type": "application/pdf" } });
        }
        return endereco.startsWith("/api/v1/relatorio-setor") ? respostaJson(200, RELATORIO) : undefined;
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Baixar PDF" }));
    await waitFor(() => expect(clicar).toHaveBeenCalled());
    const [[endereco, pedido]] = buscar.mock.calls.filter(([e]) => String(e).includes("/pdf"));
    expect(String(endereco)).toBe("/api/v1/relatorio-setor/pdf?setor=eletricas");
    expect(pedido?.method).toBe("GET");
    expect(criar).toHaveBeenCalled();
    clicar.mockRestore();
  });

  it("Baixar PDF: se a API recusar, mostra a mensagem e não baixa nada", async () => {
    const clicar = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    abrirApp("/relatorio-do-setor", {
      rotas: (endereco) => {
        if (endereco.startsWith("/api/v1/setores")) return respostaJson(200, SETORES);
        if (endereco.startsWith("/api/v1/relatorio-setor/pdf")) {
          return respostaJson(404, { detail: "Setor fora da lista do relatório do setor (veja /v1/setores)." });
        }
        return endereco.startsWith("/api/v1/relatorio-setor") ? respostaJson(200, RELATORIO) : undefined;
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Baixar PDF" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Setor");
    expect(clicar).not.toHaveBeenCalled();
    clicar.mockRestore();
  });
});
