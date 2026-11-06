// @vitest-environment jsdom
// Relatório da empresa no app novo: seções, tabelas, seção trancada e convite para os Planos.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type {
  AnaliseDaEmpresaV1,
  RastroDoNumeroV1,
  RelatorioDaEmpresaV1,
  SecaoDoRelatorioV1,
} from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const secao = (
  chave: string,
  titulo: string,
  resto: Partial<SecaoDoRelatorioV1> = {},
): SecaoDoRelatorioV1 => ({
  chave,
  titulo,
  itens: [],
  paragrafos: [],
  tabelas: [],
  trancada: false,
  ...resto,
});

const CONVITE = "Esta seção faz parte do plano Pro.";

const DFP = "https://www.rad.cvm.gov.br/exemplo";
const RASTRO: RastroDoNumeroV1 = {
  formula: "receita de vendas (12 meses)",
  versao_do_calculo: "fundamentos 2",
  fonte_id: "cvm",
  publicado_em: "2026-02-25",
  documentos: [{ nome: "DFP de 31/12/2025, versão 1", publicado_em: "2026-02-25", url: DFP }],
  outras_fontes: [],
  entradas: [
    {
      conta: "receita",
      codigo: "3.01",
      nome: "Receita de Venda de Bens e/ou Serviços",
      valor: 40804110000,
      periodo: "exercicio",
      documento: "DFP",
      referencia: "2025-12-31",
      versao: 1,
      publicado_em: "2026-02-25",
    },
  ],
  linhas: [
    { rotulo: "Fórmula", texto: "receita de vendas (12 meses)", url: "" },
    { rotulo: "Versão do cálculo", texto: "fundamentos 2", url: "" },
    { rotulo: "Fonte", texto: "cvm", url: "" },
    { rotulo: "Publicado em", texto: "25/02/2026", url: "" },
    {
      rotulo: "Documento",
      texto: "DFP de 31/12/2025, versão 1, publicado em 25/02/2026",
      url: DFP,
    },
  ],
};

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
        {
          chave: "receita",
          nome: "Receita",
          texto: "R$ 500,0 bi",
          valor: 5e11,
          unidade: "reais",
          base: "DFP 2025",
          motivo: "",
          nota: "A",
          nota_texto: "acima do setor",
          fonte: "DFP",
          comparacao: null,
          sem_comparacao: "",
          rastro: RASTRO,
        },
      ],
    }),
    // na ordem do molde A as seções da base ficam em dois blocos: capital e governança, depois negócios
    secao(
      "ofertas",
      "Ofertas e fundos",
      trancado ? { trancada: true, paragrafos: [CONVITE] } : {},
    ),
    secao(
      "auditor",
      "Auditor e controladas",
      trancado
        ? { trancada: true, paragrafos: [CONVITE] }
        : {
            itens: [
              {
                chave: "audit",
                nome: "Auditor atual",
                texto: "R$ 495,2 mi",
                valor: 4.9e8,
                unidade: "reais",
                base: "",
                motivo: "",
                nota: null,
                nota_texto: "",
                fonte: "FRE",
                comparacao: null,
                sem_comparacao: "",
              },
            ],
            paragrafos: ["Dados da base de 17/10."],
            tabelas: [
              {
                chave: "trocas",
                titulo: "Trocas de auditor",
                colunas: ["Ano", "Auditor"],
                linhas: [["2022", "Auditoria Exemplo"]],
              },
            ],
          },
    ),
    secao("pares", "Pares do mesmo setor", {
      paragrafos: ["Sem pares para comparar."],
    }),
    secao(
      "negocios",
      "Negócios e eventos",
      trancado ? { trancada: true, paragrafos: [CONVITE] } : {},
    ),
    secao("metodologia", "Metodologia e fontes", {
      paragrafos: ["Fórmulas na metodologia."],
      recolhida: true,
    }),
    secao("limites", "Limites e perguntas em aberto", {
      paragrafos: ["Nada aqui é recomendação."],
    }),
  ],
});

function abrir(corpo: RelatorioDaEmpresaV1 | null, status = 200) {
  return abrirApp("/relatorio-empresa?ticker=PETR4.SA", {
    rotas: (endereco) =>
      endereco.startsWith("/api/v1/relatorio-empresa")
        ? respostaJson(
            status,
            corpo ?? {
              detail: "O relatório completo é só das empresas da B3.",
            },
          )
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
    expect(
      await screen.findByRole("heading", { name: "Auditor e controladas" }),
    ).toBeTruthy();
    expect(buscar.mock.calls.map(([e]) => String(e))).toContain(
      "/api/v1/relatorio-empresa?ticker=PETR4.SA",
    );
    expect(screen.getByText("R$ 500,0 bi")).toBeTruthy();
    expect(screen.getByText(/Nota:/).textContent).not.toContain(
      "acima do setor",
    );
    // a explicação da nota e a metodologia ficam recolhidas (o corpo fica sóbrio)
    expect(
      screen.getByText("Como ler a nota").closest("details")?.textContent,
    ).toContain("acima do setor");
    const metodologia = screen.getByText("Ver a explicação").closest("details");
    expect(metodologia?.open).toBe(false);
    expect(metodologia?.textContent).toContain("Fórmulas na metodologia.");
    expect(screen.getByText("R$ 495,2 mi")).toBeTruthy();
    expect(screen.getByText("Dados da base de 17/10.")).toBeTruthy();
    const tabela = screen.getByRole("table", {
      name: "Trocas de auditor",
      hidden: true,
    });
    expect(within(tabela).getByText("Auditoria Exemplo")).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Conhecer o plano Pro" }),
    ).toBeNull();
  });

  it("seções trancadas em dois blocos: só o convite e um único link, depois do 1º bloco", async () => {
    abrir(relatorio(true));
    expect(
      await screen.findByRole("heading", { name: "Ofertas e fundos" }),
    ).toBeTruthy();
    expect(screen.getAllByText(CONVITE)).toHaveLength(3);
    expect(screen.queryByText("R$ 495,2 mi")).toBeNull();
    const links = screen.getAllByRole("link", { name: "Conhecer o plano Pro" });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/planos");
    const pares = screen.getByRole("heading", { name: "Pares do mesmo setor" });
    const antesDosPares =
      links[0].compareDocumentPosition(pares) &
      Node.DOCUMENT_POSITION_FOLLOWING;
    expect(antesDosPares).toBeTruthy();
  });

  it("cada número diz como foi calculado, com o link do documento original", async () => {
    abrir(relatorio(false));
    const resumo = await screen.findByText("Como foi calculado");
    const rastro = resumo.closest("details");
    expect(rastro?.open).toBe(false); // um clique abre
    expect(rastro?.textContent).toContain("Fórmula: receita de vendas (12 meses)");
    expect(rastro?.textContent).toContain("Versão do cálculo: fundamentos 2");
    expect(rastro?.textContent).toContain("Publicado em: 25/02/2026");
    const link = within(rastro as HTMLElement).getByRole("link", {
      name: "abrir o original",
      hidden: true,
    });
    expect(link.getAttribute("href")).toBe(DFP);
    // só o número com rastro: o auditor (frase da base, sem rastro) não ganha o "como foi calculado"
    expect(screen.getAllByText("Como foi calculado")).toHaveLength(1);
  });

  it("o rastro tem os mesmos campos do esquema da API", () => {
    const esquemas = JSON.parse(
      readFileSync(join(process.cwd(), "..", "docs", "api", "openapi-v1.json"), "utf8"),
    ).components.schemas;
    const campos = (nome: string) => Object.keys(esquemas[nome].properties).sort();
    expect(Object.keys(RASTRO).sort()).toEqual(campos("RastroDoNumeroV1"));
    expect(Object.keys(RASTRO.linhas[0]).sort()).toEqual(campos("LinhaDoRastroV1"));
    expect(Object.keys(RASTRO.documentos[0]).sort()).toEqual(campos("DocumentoUsadoV1"));
    expect(Object.keys(RASTRO.entradas[0]).sort()).toEqual(campos("EntradaDoNumeroV1"));
  });

  it("mostra o aviso de conferência e as fontes", async () => {
    abrir({ ...relatorio(false), em_conferencia: true });
    expect(
      await screen.findByText(/em conferência pelas regras de qualidade/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Fontes: CVM \(demonstrações\); CVM \(fichas da base\)\. Nada aqui é recomendação/,
      ),
    ).toBeTruthy();
  });

  it("empresa que não é da B3: a mensagem da API", async () => {
    abrir(null, 404);
    expect(await screen.findByText(/só das empresas da B3/)).toBeTruthy();
  });
});

const analiseDeExemplo = (
  motivo: string | null = null,
): AnaliseDaEmpresaV1 => ({
  aviso:
    "Análise escrita por modelo de linguagem. Não é recomendação de investimento.",
  motivo,
  notas: [
    {
      numero: 1,
      id: "retorno.roe",
      nome: "ROE",
      texto: "26,4%",
      medido_em: "DFP de 2025",
      fonte: "DFP (CVM)",
      comparacao: "Contra a mediana do setor: 11,8%",
    },
    {
      numero: 2,
      id: "resultado.receita",
      nome: "Receita",
      texto: "R$ 500,0 bi",
      medido_em: "DFP de 2025",
      fonte: "DFP (CVM)",
      comparacao: "",
    },
  ],
  partes: [
    {
      chave: "o_que_os_numeros_mostram",
      titulo: "O que os números mostram",
      origem: "modelo",
      paragrafos: [
        {
          tipo: "fato",
          rotulo: "",
          frases: [
            { texto: "O ROE é 26,4%.", notas: [1] },
            { texto: "A receita foi de R$ 500,0 bi.", notas: [2] },
          ],
        },
        {
          tipo: "leitura",
          rotulo: "Leitura",
          frases: [
            {
              texto: "Os dois juntos mostram escala com retorno.",
              notas: [1, 2],
            },
          ],
        },
      ],
    },
  ],
});

describe("a análise escrita no relatório", () => {
  it("mostra a análise antes dos dados, com o rótulo da leitura e o aviso", async () => {
    abrir({ ...relatorio(false), analise: analiseDeExemplo() });
    const analise = await screen.findByRole("heading", { name: "A análise" });
    expect(screen.getByText(/Não é recomendação de investimento/)).toBeTruthy();
    expect(screen.getByText(/O ROE é 26,4%\./)).toBeTruthy();
    expect(screen.getByText("Leitura:")).toBeTruthy();
    const dados = screen.getByRole("heading", { name: "Os dados" });
    expect(
      analise.compareDocumentPosition(dados) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    const resultado = screen.getByRole("heading", { name: "Resultado" });
    expect(
      dados.compareDocumentPosition(resultado) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("a nota é um botão que abre o número: nome, valor, medido em, fonte e comparação", async () => {
    abrir({ ...relatorio(false), analise: analiseDeExemplo() });
    await screen.findByRole("heading", { name: "A análise" });
    expect(document.getElementById("nota-1")).toBeNull();
    const botoes = screen.getAllByRole("button", { name: "Nota 1" });
    expect(botoes[0].getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(botoes[0]);
    const aberta = document.getElementById("nota-1");
    expect(aberta?.textContent).toContain("ROE");
    expect(aberta?.textContent).toContain("26,4%");
    expect(aberta?.textContent).toContain("Medido em DFP de 2025");
    expect(aberta?.textContent).toContain("Fonte: DFP (CVM)");
    expect(aberta?.textContent).toContain("Contra a mediana do setor: 11,8%");
    expect(
      screen
        .getAllByRole("button", { name: "Nota 1" })[0]
        .getAttribute("aria-expanded"),
    ).toBe("true");
    fireEvent.click(screen.getAllByRole("button", { name: "Nota 1" })[0]);
    expect(document.getElementById("nota-1")).toBeNull();
  });

  it("ficha nova: o texto de reserva diz que a análise está sendo reescrita", async () => {
    abrir({
      ...relatorio(false),
      analise: analiseDeExemplo("análise sendo reescrita com os números novos"),
    });
    expect(
      await screen.findByText(/análise sendo reescrita com os números novos/),
    ).toBeTruthy();
  });

  it("sem análise gerada, o relatório fica como hoje, sem erro", async () => {
    abrir({ ...relatorio(false), analise: null });
    expect(
      await screen.findByRole("heading", { name: "Resultado" }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "A análise" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Os dados" })).toBeNull();
  });

  it("Baixar deck (PPT): pede a apresentação da ficha em pptx pelo ticker e entrega o arquivo", async () => {
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:ppt"), revokeObjectURL: vi.fn() });
    const clicar = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { buscar } = abrirApp("/relatorio-empresa?ticker=PETR4.SA", {
      rotas: (endereco) => {
        if (endereco.startsWith("/api/v1/relatorio-empresa/apresentacao")) return new Response("PK", { status: 200 });
        return endereco.startsWith("/api/v1/relatorio-empresa") ? respostaJson(200, relatorio(false)) : undefined;
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Baixar deck (PPT)" }));
    await vi.waitFor(() => expect(clicar).toHaveBeenCalled());
    const [[endereco]] = buscar.mock.calls.filter(([e]) => String(e).includes("/apresentacao"));
    expect(String(endereco)).toBe("/api/v1/relatorio-empresa/apresentacao?ticker=PETR4.SA&formato=pptx");
    clicar.mockRestore();
  });
});
