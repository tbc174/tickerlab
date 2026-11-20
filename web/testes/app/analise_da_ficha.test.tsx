// @vitest-environment jsdom
// A análise completa na ficha (19/11/2026): a frase do topo, cada bloco com o título e cada valor com a fonte e
// o dia, a linha do tempo, as leituras à parte (dedução), o que não foi achado e o que a tela não consulta.
// Não liberada ou não disponível é uma frase da tela, nunca "não existe". Dados de mentira, sem pessoa real.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AnaliseCompletaV1, FichaDaEmpresaV1 } from "../../src/app/tipos";
import { abrirAba, abrirApp, respostaJson } from "./ajudantes";

const CNPJ = "02.429.144/0001-93";
const ROTA_DA_FICHA = "/api/v1/analista/ficha";
const ROTA_DA_ANALISE = "/api/v1/analista/ficha/analise";
const ABA = "Análise completa";

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

const campo = (valor: string | number | boolean, fonte: string, publico_em: string) => ({
  valor,
  fonte,
  publico_em,
  visto_em: null,
});
const receita = (valor: string | number | boolean) => campo(valor, "rfb-cnpj", "2026-09-30");
const FONTES = [
  { fonte: "rfb-cnpj", licenca: "CC BY", atribuicao: "Fonte: Receita Federal, dados abertos do CNPJ (CC BY)" },
  { fonte: "cvm-hist-dfp", licenca: "ODbL", atribuicao: "Fonte: CVM, Portal de Dados Abertos (ODbL)" },
];
const AINDA_NAO_TRAZ = [
  "Fatos de crédito (dívida e pagamentos ao poder público): não disponível nesta tela",
  "Sanções e impedimentos de contratar com o governo (CGU): não disponível nesta tela",
  "Pessoas físicas (sócio pessoa física, administradores)",
];

const PRONTA: AnaliseCompletaV1 = {
  estado: "pronta",
  cnpj: "02429144000193",
  como_era_em: "2026-11-10",
  frase: { texto: "EMPRESA MODELO S.A.; situação ativa na Receita.", tipo: "fact", a_partir_de: ["cadastro"] },
  blocos: [
    {
      nome: "cadastro",
      titulo: "Cadastro",
      o_que_traz: "Receita Federal: razão social, situação, atividade, sede e início.",
      corpo: {
        cadastro_na_receita: { razao_social: receita("EMPRESA MODELO S.A."), uf: receita("SP") },
        entregas: [
          {
            documento: campo("DFP", "cvm-hist-dfp", "2026-03-20"),
            referencia: campo("2025-12-31", "cvm-hist-dfp", "2026-03-20"),
          },
        ],
        entregas_nao_disponiveis: [],
      },
    },
    {
      nome: "socios_pj",
      titulo: "Grupo e sócios pessoa jurídica",
      o_que_traz: "Receita Federal: as empresas sócias desta e as de que esta é sócia.",
      corpo: {
        socias_pj: [{ raiz_do_cnpj: "11222333", razao_social: campo("HOLDING UM S.A.", "rfb-cnpj", "2025-08-31") }],
        participacoes_pj: [],
        cortada: true,
      },
    },
  ],
  linha_do_tempo: [
    {
      dia: "2010-05-01",
      o_que: "Início da atividade (Receita)",
      bloco: "cadastro",
      titulo_do_bloco: "Cadastro",
      fonte: "rfb-cnpj",
      publico_em: "2026-09-30",
    },
  ],
  leituras: [
    { texto: "Cerca de 16 anos de atividade no dia pedido.", tipo: "inference", a_partir_de: ["cadastro"] },
  ],
  nao_encontrado: [
    {
      bloco: "vinculos",
      titulo: "Controle, coligação e auditoria",
      por_que: "O bloco não trouxe dado desta empresa no dia: não achado não quer dizer que não existe.",
    },
  ],
  nao_respondeu_a_tempo: [],
  ainda_nao_traz: AINDA_NAO_TRAZ,
  fontes: FONTES,
  limites: ["As leituras são dedução do TickerLab; nada aqui é recomendação de investimento."],
};

const SEM_ANALISE = (estado: "nao_liberada" | "nao_disponivel"): AnaliseCompletaV1 => ({
  estado,
  blocos: [],
  linha_do_tempo: [],
  leituras: [],
  nao_encontrado: [],
  nao_respondeu_a_tempo: [],
  ainda_nao_traz: [],
  fontes: [],
  limites: ["Pessoa natural (MEI, empresário individual) não é servida."],
});

afterEach(cleanup);

function abrir(analise: () => Response) {
  const pedidos: { endereco: string; corpo: unknown }[] = [];
  abrirApp("/ficha-da-empresa", {
    rotas: (endereco, opcoes) => {
      if (endereco === ROTA_DA_FICHA) return respostaJson(200, FICHA);
      if (endereco === ROTA_DA_ANALISE) {
        pedidos.push({ endereco, corpo: opcoes?.body ? JSON.parse(String(opcoes.body)) : null });
        return analise();
      }
      return undefined;
    },
  });
  return pedidos;
}

async function verAnalise() {
  fireEvent.change(await screen.findByLabelText("CNPJ"), { target: { value: CNPJ } });
  fireEvent.click(screen.getByRole("button", { name: "Ver a ficha" }));
  await abrirAba(ABA);
  await screen.findByRole("heading", { name: ABA });
  // a análise chega depois do título: espera a resposta sair do esqueleto
  await waitFor(() => expect(screen.queryByLabelText("Montando a análise completa")).toBeNull());
}

describe("análise completa da ficha", () => {
  it("pede a análise com o CNPJ no corpo, nunca no endereço", async () => {
    const pedidos = abrir(() => respostaJson(200, PRONTA));
    await verAnalise();
    expect(pedidos).toHaveLength(1);
    expect(pedidos[0].corpo).toEqual({ cnpj: expect.stringMatching(/02\.?429\.?144/) });
  });

  it("mostra a frase, cada bloco com o título e cada valor com a fonte e o dia", async () => {
    abrir(() => respostaJson(200, PRONTA));
    await verAnalise();
    expect(screen.getByText("EMPRESA MODELO S.A.; situação ativa na Receita.")).toBeTruthy();
    const cadastro = screen.getByRole("region", { name: "Cadastro" });
    expect(within(cadastro).getAllByText("EMPRESA MODELO S.A.").length).toBeGreaterThan(0);
    expect(within(cadastro).getAllByText("Receita Federal, dados abertos do CNPJ (CC BY)").length).toBeGreaterThan(0);
    expect(within(cadastro).getAllByText("30/09/2026").length).toBeGreaterThan(0);
    expect(within(cadastro).getByText("CVM, Portal de Dados Abertos (ODbL)")).toBeTruthy();
    const socios = screen.getByRole("region", { name: "Grupo e sócios pessoa jurídica" });
    expect(within(socios).getByText("HOLDING UM S.A.")).toBeTruthy();
    expect(within(socios).getByText("31/08/2025")).toBeTruthy();
    expect(within(socios).getByText(/parou no limite/)).toBeTruthy();
  });

  it("separa as leituras (dedução) dos fatos e traz a linha do tempo com a fonte", async () => {
    abrir(() => respostaJson(200, PRONTA));
    await verAnalise();
    const leituras = screen.getByRole("region", { name: /Leituras \(dedução do TickerLab/ });
    expect(within(leituras).getByText(/16 anos de atividade/)).toBeTruthy();
    const tempo = screen.getByRole("region", { name: "Linha do tempo" });
    expect(within(tempo).getByText("01/05/2010")).toBeTruthy();
    expect(within(tempo).getByText("Início da atividade (Receita)")).toBeTruthy();
    expect(within(tempo).getByText("Receita Federal, dados abertos do CNPJ (CC BY)")).toBeTruthy();
  });

  it("diz o que não foi achado e o que a tela não consulta, sem dizer que não existe", async () => {
    abrir(() => respostaJson(200, PRONTA));
    await verAnalise();
    const falta = screen.getByRole("region", { name: /não foi achado ou não foi consultado/ });
    expect(within(falta).getByText(/não achado não quer dizer que não existe/)).toBeTruthy();
    for (const texto of AINDA_NAO_TRAZ) expect(within(falta).getByText(texto)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Fontes" })).toBeTruthy();
  });

  it.each([
    ["nao_liberada", /ainda não foram liberados/],
    ["nao_disponivel", /Análise não disponível para este CNPJ/],
  ] as const)("%s é uma frase da tela, com os limites", async (estado, frase) => {
    abrir(() => respostaJson(200, SEM_ANALISE(estado)));
    await verAnalise();
    expect(screen.getByText(frase)).toBeTruthy();
    expect(screen.queryByText(/não existe/)).toBeNull();
    expect(screen.getByText("Pessoa natural (MEI, empresário individual) não é servida.")).toBeTruthy();
  });

  it("o aviso de piloto vai junto com a análise", async () => {
    const aviso = "Dado de piloto: passou na qualidade automática, mas ainda não na conferência cruzada.";
    abrir(() => respostaJson(200, { ...PRONTA, aviso_de_piloto: aviso }));
    await verAnalise();
    expect(screen.getByText(aviso)).toBeTruthy();
  });

  it("uma falha do pedido vira o aviso de erro, sem derrubar a ficha", async () => {
    abrir(() => respostaJson(503, { detail: "Base indisponível." }));
    await verAnalise();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Resumo" })).toBeTruthy();
  });
});
