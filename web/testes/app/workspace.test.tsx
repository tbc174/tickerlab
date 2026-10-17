// @vitest-environment jsdom
// O Início do app novo é o Workspace (ADR 0062; Workspace, PRs 2 e 3): os cartões "Acontecimentos novos",
// "Variação do preço" e "Estratégias acompanhadas", todos de um pedido só ao Pulse, a janela que o F5 não
// encolhe e a lista de telas embaixo. Os acontecimentos e as variações vêm de exemplos/pulse.json, gravado
// por tests/test_app_novo_mesmos_numeros.py com as funções da API (os mesmos números do app atual).
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";
import exemplo from "./exemplos/pulse.json";

const JANELA = {
  inicio: "2026-10-02T23:00:00Z",
  fim: "2026-10-09T23:00:00Z",
  primeira_vez: true,
  texto: "Primeira visita: o que aconteceu nos últimos 7 dias.",
};
const MUDOU = {
  id: "11111111-1111-1111-1111-111111111111",
  nome: "Médias 10/40 na Petrobras",
  ticker: "PETR4.SA",
  antes: "passou",
  agora: "não passou",
  mudou: true,
  conferido_em: "2026-10-09T23:00:00Z",
  tese_ligada: "Sua tese sobre PETR4 em 08/10/2026: “Dividendos <b>altos</b>”",
  endereco: "/backtest?ticker=PETR4.SA&periodo=2y",
};
const IGUAL = {
  ...MUDOU,
  id: "22222222-2222-2222-2222-222222222222",
  nome: "Vale no app atual",
  ticker: "VALE3.SA",
  antes: "passou",
  agora: "passou",
  mudou: false,
  tese_ligada: "Sua tese sobre VALE3 em 01/10/2026: “Minério”",
  endereco: null,
};
const SEM_CONFERIR = {
  ...IGUAL,
  id: "33333333-3333-3333-3333-333333333333",
  nome: "Sem dados hoje",
  agora: null,
  conferido_em: null,
  tese_ligada: null,
};
const PARTE_2 = exemplo.resposta;
const PULSE = {
  ...PARTE_2,
  janela: JANELA,
  estrategias: [MUDOU, IGUAL, SEM_CONFERIR],
  limites: { sem_ficha: 1, alem_do_maximo: 0, nao_conferidas: 1, alem_dos_ativos: 3 },
  avisos: ["Não deu para conferir agora: Sem dados hoje."],
  sem_estrategias: "Salve um backtest para acompanhar: o Pulse refaz a ficha com os preços de hoje.",
  notas: ["O Pulse mostra o que mudou, não o que fazer: nada aqui é recomendação de investimento."],
};

function abrir(resposta: Response | (() => Response) = () => respostaJson(200, PULSE)) {
  return abrirApp("/", {
    rotas: (endereco) =>
      endereco.startsWith("/api/v1/pulse") ? (typeof resposta === "function" ? resposta() : resposta) : undefined,
  });
}

const cartao = (nome = "Estratégias acompanhadas") => screen.findByRole("region", { name: nome }, { timeout: 5000 });
const acontecimentos = () => cartao("Acontecimentos novos");
const variacao = () => cartao("Variação do preço");
// só os itens de cima: cada um tem a lista do "por que aparece" dentro
const itensDe = (c: HTMLElement) =>
  Array.from(within(c).getByRole("list", { name: "Acontecimentos" }).children) as HTMLElement[];
const pedidosDoPulse = (buscar: ReturnType<typeof abrir>["buscar"]) =>
  buscar.mock.calls.map(([e]) => String(e)).filter((e) => e.startsWith("/api/v1/pulse"));

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("o Início é o Workspace", () => {
  it("pede o Pulse uma vez e mostra o texto da janela", async () => {
    const { buscar } = abrir();
    await cartao();
    expect(screen.getByText(JANELA.texto)).toBeTruthy(); // a janela vale para os três cartões
    expect(pedidosDoPulse(buscar)).toEqual(["/api/v1/pulse"]);
  });

  it("guarda o início da janela na aba e o reenvia no F5", async () => {
    abrir();
    await screen.findByText(JANELA.texto, {}, { timeout: 5000 });
    cleanup();
    vi.unstubAllGlobals();
    const { buscar } = abrir(); // o F5: a mesma aba (o sessionStorage continua)
    await screen.findByText(JANELA.texto, {}, { timeout: 5000 });
    const [pedido] = pedidosDoPulse(buscar);
    expect(new URL(pedido, "http://app").searchParams.get("desde")).toBe(JANELA.inicio);
  });

  it("o que mudou vem primeiro, com o selo de antes e agora, a data, a tese e o backtest", async () => {
    abrir();
    const c = await cartao();
    const lista = await within(c).findByRole("list", { name: "Estratégias" });
    const [mudou, igual, semConferir] = within(lista).getAllByRole("listitem");
    expect(within(mudou).getByText(MUDOU.nome)).toBeTruthy();
    expect(within(mudou).getByText("passou → não passou · 09/10")).toBeTruthy();
    // o texto da tese é da pessoa: aparece como texto, sem virar HTML
    expect(within(mudou).getByText(MUDOU.tese_ligada)).toBeTruthy();
    expect(within(mudou).getByRole("link", { name: /Abrir o backtest/ }).getAttribute("href")).toBe(MUDOU.endereco);
    expect(within(igual).getByText(IGUAL.nome)).toBeTruthy();
    expect(within(igual).getByText(/sem mudança/)).toBeTruthy();
    expect(within(igual).queryByText(IGUAL.tese_ligada)).toBeNull(); // a tese só junto do que mudou
    expect(within(igual).getByRole("link", { name: /app atual/ }).getAttribute("href")).toBe(
      "https://app.tickerlab.com.br/simulacoes",
    );
    expect(within(semConferir).getByText(/Não deu para conferir agora/)).toBeTruthy();
    expect(within(c).getByText(PULSE.avisos[0])).toBeTruthy();
    expect(within(c).getByText(PULSE.notas[0])).toBeTruthy();
  });

  it("sem estratégias salvas, a frase da API e o caminho para o backtest", async () => {
    abrir(() => respostaJson(200, { ...PULSE, estrategias: [], avisos: [] }));
    const c = await cartao();
    expect(await within(c).findByText(PULSE.sem_estrategias)).toBeTruthy();
    expect(within(c).getByRole("link", { name: "Rodar um backtest" }).getAttribute("href")).toBe("/backtest");
  });

  it("a lista de telas continua embaixo do cartão, e o Pulse não aparece nela", async () => {
    abrir();
    const c = await cartao();
    const telas = await screen.findByRole("list", { name: "Telas novas" });
    expect(c.compareDocumentPosition(telas) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(telas).getByRole("link", { name: "Visão geral" })).toBeTruthy();
    expect(within(telas).queryByRole("link", { name: "Pulse" })).toBeNull();
  });

  it("se o Pulse falha, um erro só no lugar dos cartões, e as telas continuam", async () => {
    abrir(() => respostaJson(503, { detail: "fora do ar" }));
    const c = await cartao("O que mudou");
    expect(await within(c).findByRole("alert")).toBeTruthy();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "Estratégias acompanhadas" })).toBeNull();
    expect(screen.getByRole("list", { name: "Telas novas" })).toBeTruthy();
  });

  it("os cartões vêm na ordem: acontecimentos, variação, estratégias", async () => {
    abrir();
    const [a, v, e] = [await acontecimentos(), await variacao(), await cartao()];
    expect(a.compareDocumentPosition(v) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(v.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("Acontecimentos novos (Workspace, PR 3)", () => {
  it("na ordem da API, com o ativo, o tipo, a data, o título e a empresa", async () => {
    abrir();
    const itens = itensDe(await acontecimentos());
    expect(itens).toHaveLength(PARTE_2.acontecimentos.length);
    PARTE_2.acontecimentos.forEach((a, i) => {
      expect(within(itens[i]).getByText(a.titulo)).toBeTruthy();
      expect(within(itens[i]).getByText(`${a.ticker} · ${a.tipo}`, { exact: false })).toBeTruthy();
    });
    expect(within(itens[0]).getByText("PETR4 · Fato Relevante · 08/10/2026 · Petrobras")).toBeTruthy();
  });

  it("cada acontecimento abre o documento original em nova aba; sem link, avisa", async () => {
    abrir();
    const [comLink, semLink] = itensDe(await acontecimentos());
    const link = within(comLink).getByRole("link", { name: /Abrir o documento na CVM/ });
    expect(link.getAttribute("href")).toBe(PARTE_2.acontecimentos[0].link_do_original);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(within(semLink).queryByRole("link")).toBeNull();
    expect(within(semLink).getByText(/sem link para o documento/)).toBeTruthy();
  });

  it("um link que não é http(s) não vira link", async () => {
    const [primeiro, ...resto] = PARTE_2.acontecimentos;
    abrir(() =>
      respostaJson(200, { ...PULSE, acontecimentos: [{ ...primeiro, link_do_original: "javascript:alert(1)" }, ...resto] }),
    );
    const [ruim] = itensDe(await acontecimentos());
    expect(within(ruim).queryByRole("link")).toBeNull();
    expect(within(ruim).getByText(/sem link para o documento/)).toBeTruthy();
  });

  it("por que aparece fica à mão, num detalhe que abre", async () => {
    abrir();
    const [primeiro] = itensDe(await acontecimentos());
    expect(within(primeiro).getByText("Por que aparece")).toBeTruthy();
    expect(within(primeiro).getByText(PARTE_2.acontecimentos[0].por_que_aparece[0])).toBeTruthy();
  });

  it("“nenhum acontecimento novo” quando a lista vem vazia", async () => {
    abrir(() => respostaJson(200, { ...PULSE, acontecimentos: [] }));
    const c = await acontecimentos();
    expect(within(c).getByText(/Nenhum acontecimento novo/)).toBeTruthy();
  });

  it("se a leitura falhou (null), avisa que a visita não foi marcada; o resto aparece", async () => {
    abrir(() => respostaJson(200, { ...PULSE, acontecimentos: null }));
    const c = await acontecimentos();
    expect(within(c).getByText(/Não deu para ler os acontecimentos agora/)).toBeTruthy();
    expect(within(c).getByText(/aparecem na próxima visita/)).toBeTruthy();
    expect(await variacao()).toBeTruthy();
  });

  it("sem nenhum ativo guardado, a frase da API diz de onde vêm os ativos", async () => {
    abrir(() =>
      respostaJson(200, { ...PULSE, acontecimentos: [], variacoes: [], sem_variacao: [], avisos_dos_ativos: [] }),
    );
    const c = await acontecimentos();
    expect(within(c).getByText(PULSE.sem_ativos)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Variação do preço" })).toBeNull();
  });
});

describe("Variação do preço (Workspace, PR 3)", () => {
  it("na ordem da API (pulse.ordenar_variacoes: a maior mudança primeiro), com o sinal e as datas", async () => {
    abrir();
    const c = await variacao();
    const linhas = within(c).getAllByRole("row").slice(1); // a 1ª é o cabeçalho
    expect(linhas.map((l) => within(l).getAllByRole("cell")[0].textContent)).toEqual(
      PARTE_2.variacoes.map((v) => v.ticker),
    );
    expect(within(linhas[0]).getByText("-4,90%")).toBeTruthy(); // VALE3, -0,049…
    expect(within(linhas[1]).getByText("+2,00%")).toBeTruthy(); // ITUB4
    expect(within(linhas[0]).getByText("05/10/2026 → 09/10/2026")).toBeTruthy();
    expect(within(linhas[1]).getByText("Minha carteira")).toBeTruthy();
  });

  it("os sem preço, a nota de como a conta é feita e o aviso dos ativos de fora", async () => {
    abrir();
    const c = await variacao();
    expect(within(c).getByText(/Sem preço para comparar: ZZZZ3/)).toBeTruthy();
    expect(within(c).getByText(PARTE_2.nota_da_variacao)).toBeTruthy();
    expect(within(c).getByText(PARTE_2.avisos_dos_ativos[0])).toBeTruthy();
  });
});

describe("os textos novos só mostram o que mudou", () => {
  // nada de compra ou venda, e nenhum adjetivo que julgue a mudança: o número fala sozinho
  const PROIBIDAS = [
    "compre",
    "venda",
    "oportunidade",
    "preço-alvo",
    "recomend",
    "positiv",
    "negativ",
    "forte",
    "fraco",
    "excelente",
    "preocupante",
    "ótim",
    "ruim",
    "expressiv",
  ];

  it("nenhuma palavra de recomendação nem adjetivo nos cartões de acontecimentos e variação", async () => {
    abrir();
    for (const c of [await acontecimentos(), await variacao()]) {
      const texto = (c.textContent ?? "").toLowerCase();
      for (const palavra of PROIBIDAS) expect(texto, palavra).not.toContain(palavra);
    }
  });
});
