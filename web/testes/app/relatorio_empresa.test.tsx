// @vitest-environment jsdom
// Relatório da empresa no app novo: seções, tabelas, seção trancada e convite para os Planos.
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RelatorioDaEmpresaV1, SecaoDoRelatorioV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const secao = (chave: string, titulo: string, resto: Partial<SecaoDoRelatorioV1> = {}): SecaoDoRelatorioV1 => ({
  chave,
  titulo,
  itens: [],
  paragrafos: [],
  tabelas: [],
  trancada: false,
  ...resto,
});

const CONVITE = "Esta seção faz parte do plano Pro.";

const relatorio = (trancado: boolean): RelatorioDaEmpresaV1 => ({
  empresa: "Petróleo Brasileiro S.A.",
  cnpj: "33.000.167/0001-01",
  ticker: "PETR4.SA",
  setor: "Petróleo",
  grupo: "Energia",
  em_conferencia: false,
  aviso_das_notas: "",
  fontes: ["CVM (demonstrações)", "CVM (fichas da base)"],
  secoes: [
    secao("resultado", "Resultado", {
      itens: [
        { chave: "receita", nome: "Receita", texto: "R$ 500,0 bi", valor: 5e11, unidade: "reais", base: "DFP 2025", motivo: "", nota: "A", nota_texto: "acima do setor" },
      ],
    }),
    secao("auditor", "Auditor e controladas", trancado
      ? { trancada: true, paragrafos: [CONVITE] }
      : {
          itens: [{ chave: "audit", nome: "Auditor atual", texto: "R$ 495,2 mi", valor: 4.9e8, unidade: "reais", base: "", motivo: "", nota: null, nota_texto: "" }],
          paragrafos: ["Dados da base de 17/10."],
          tabelas: [{ chave: "trocas", titulo: "Trocas de auditor", colunas: ["Ano", "Auditor"], linhas: [["2022", "Auditoria Exemplo"]] }],
        }),
    secao("ofertas", "Ofertas e fundos", trancado ? { trancada: true, paragrafos: [CONVITE] } : {}),
    secao("limites", "Limites e cuidados", { paragrafos: ["Nada aqui é recomendação."] }),
  ],
});

function abrir(corpo: RelatorioDaEmpresaV1 | null, status = 200) {
  return abrirApp("/relatorio-empresa?ticker=PETR4.SA", {
    rotas: (endereco) =>
      endereco.startsWith("/api/v1/relatorio-empresa")
        ? respostaJson(status, corpo ?? { detail: "O relatório completo é só das empresas da B3." })
        : undefined,
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("relatório da empresa", () => {
  it("pede o ticker à API e mostra as seções, os números e as tabelas do Pro", async () => {
    const { buscar } = abrir(relatorio(false));
    expect(await screen.findByRole("heading", { name: "Auditor e controladas" })).toBeTruthy();
    expect(buscar.mock.calls.map(([e]) => String(e))).toContain("/api/v1/relatorio-empresa?ticker=PETR4.SA");
    expect(screen.getByText("R$ 500,0 bi")).toBeTruthy();
    expect(screen.getByText(/Nota:/).textContent).toContain("acima do setor");
    expect(screen.getByText("R$ 495,2 mi")).toBeTruthy();
    expect(screen.getByText("Dados da base de 17/10.")).toBeTruthy();
    const tabela = screen.getByRole("table", { name: "Trocas de auditor", hidden: true });
    expect(within(tabela).getByText("Auditoria Exemplo")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Conhecer o plano Pro" })).toBeNull();
  });

  it("seções trancadas: só o convite e um único link para os Planos", async () => {
    abrir(relatorio(true));
    expect(await screen.findByRole("heading", { name: "Ofertas e fundos" })).toBeTruthy();
    expect(screen.getAllByText(CONVITE)).toHaveLength(2);
    expect(screen.queryByText("R$ 495,2 mi")).toBeNull();
    const links = screen.getAllByRole("link", { name: "Conhecer o plano Pro" });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/planos");
  });

  it("mostra o aviso de conferência e as fontes", async () => {
    abrir({ ...relatorio(false), em_conferencia: true });
    expect(await screen.findByText(/em conferência pelas regras de qualidade/)).toBeTruthy();
    expect(screen.getByText(/Fontes: CVM \(demonstrações\); CVM \(fichas da base\)\. Nada aqui é recomendação/)).toBeTruthy();
  });

  it("empresa que não é da B3: a mensagem da API", async () => {
    abrir(null, 404);
    expect(await screen.findByText(/só das empresas da B3/)).toBeTruthy();
  });
});
