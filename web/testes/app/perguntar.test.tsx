// @vitest-environment jsdom
// Perguntar (linha 903): o estado vem de GET /v1/chat/estado; a resposta chega em linhas (NDJSON) do POST
// /v1/chat, com o "Como cheguei aqui" e as fontes montados pelo servidor.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErroDaApi, SESSAO, pedirEmLinhas } from "../../src/app/api";
import {
  cnpjsDaConversa,
  comEvento,
  eventoDaLinha,
  fontesDaConversa,
  formatarDuracao,
  historicoParaEnviar,
  separarLacunas,
  trocaNova,
} from "../../src/app/chat";
import { blocosDoMarkdown } from "../../src/app/Markdown";
import type { EstadoDoChatV1, EventoDoChat } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const ROTA_DO_ESTADO = "/api/v1/chat/estado";
const ROTA_DA_PERGUNTA = "/api/v1/chat";

const PRONTO: EstadoDoChatV1 = {
  situacao: "pronto",
  pode_perguntar: true,
  mensagem: null,
  perguntas_hoje: 2,
  perguntas_por_dia: 20,
  perguntas_no_mes: 5,
  perguntas_por_mes: 300,
  caracteres_da_pergunta: 2000,
  perguntas_no_historico: 4,
  caracteres_do_historico: 4000,
  como_funciona: "O modelo só lê a base.",
  exemplos: ["Exemplo de pergunta 1?", "Exemplo de pergunta 2?"],
  limites: ["Limite do chat 1."],
};
const DESLIGADO: EstadoDoChatV1 = {
  ...PRONTO,
  situacao: "desligado",
  pode_perguntar: false,
  mensagem: "O chat de IA ainda não foi ligado.",
};

const FIM: EventoDoChat = {
  tipo: "fim",
  como_cheguei_aqui: [
    {
      nome: "prospectar",
      titulo: "Prospectar empresas",
      filtros: { uf: "SC", cnpj: "12.345.678/0001-90" },
      ok: true,
      duracao_ms: 1840,
      fontes: [{ fonte: "rfb_cnpj", atribuicao: "Receita Federal", licenca: null, publicado_em: "2026-10-12" }],
    },
  ],
  avisos: [],
  aviso_final: "Resposta escrita por IA com os dados do TickerLab.",
};

function linhas(eventos: unknown[]): Response {
  return new Response(eventos.map((e) => JSON.stringify(e)).join("\n"), {
    status: 200,
    headers: { "content-type": "application/x-ndjson" },
  });
}

function abrirChat(estado: EstadoDoChatV1, responder?: (corpo: unknown) => Response) {
  return abrirApp("/perguntar", {
    rotas: (endereco, pedido) => {
      if (endereco === ROTA_DO_ESTADO) return respostaJson(200, estado);
      if (endereco === ROTA_DA_PERGUNTA && responder) return responder(JSON.parse(String(pedido?.body)));
      return undefined;
    },
  });
}

async function perguntar(texto: string) {
  const caixa = await screen.findByRole("textbox", { name: "Sua pergunta" }, { timeout: 5000 });
  fireEvent.change(caixa, { target: { value: texto } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("tela Perguntar", () => {
  it("desligado: diz que ainda não foi ligado, mostra o que vai fazer e trava a caixa", async () => {
    const { buscar } = abrirChat(DESLIGADO);
    const parado = await screen.findByRole("region", { name: "O chat agora" }, { timeout: 5000 });
    expect(within(parado).getByText("O chat ainda não está ligado")).toBeTruthy();
    expect(within(parado).getByText("O chat de IA ainda não foi ligado.")).toBeTruthy();
    expect(within(parado).getByText("Exemplo de pergunta 1?")).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Sua pergunta" }) as HTMLTextAreaElement).disabled).toBe(true);
    expect(screen.getByText("Limite do chat 1.")).toBeTruthy();
    expect(buscar.mock.calls.some(([e]) => e === ROTA_DA_PERGUNTA)).toBe(false);
  });

  it("pronto: o exemplo preenche a caixa, e a cota e o teto ficam à vista", async () => {
    abrirChat(PRONTO);
    fireEvent.click(await screen.findByRole("button", { name: "Exemplo de pergunta 2?" }, { timeout: 5000 }));
    expect((screen.getByRole("textbox", { name: "Sua pergunta" }) as HTMLTextAreaElement).value).toBe(
      "Exemplo de pergunta 2?",
    );
    const cota = screen.getByLabelText("Cota e teto");
    expect(cota.textContent).toContain("Hoje: 2 de 20");
    expect(cota.textContent).toContain("No mês: 5 de 300");
    expect(cota.textContent).toContain("dentro do limite");
    expect(cota.textContent).not.toMatch(/US\$|R\$/); // o gasto em dinheiro não aparece
  });

  it("a resposta chega com a fonte, a consulta feita e o que a base não tem", async () => {
    let corpo: unknown = null;
    abrirChat(PRONTO, (c) => {
      corpo = c;
      return linhas([
        { tipo: "ferramenta", nome: "prospectar", titulo: "Prospectar empresas", filtros: { uf: "SC" } },
        { tipo: "texto", texto: "Achei **três** empresas.\n\nNão temos o faturamento de empresa fechada." },
        FIM,
      ]);
    });
    await perguntar("Quem fabrica embalagens em SC?");
    const resposta = await screen.findByRole("article", { name: "Resposta" }, { timeout: 5000 });
    await waitFor(() => expect(resposta.getAttribute("aria-busy")).toBe("false"));
    expect(corpo).toEqual({ pergunta: "Quem fabrica embalagens em SC?", historico: [] });
    expect(within(resposta).getByText("três").tagName).toBe("STRONG");
    expect(within(resposta).getByText("Fonte: Receita Federal · dado de 12/10/2026")).toBeTruthy();
    const como = within(resposta).getByRole("region", { name: "Como cheguei aqui" });
    expect(within(como).getByText("prospectar")).toBeTruthy();
    expect(como.textContent).toContain("uf: SC");
    expect(como.textContent).toContain("1,8 s");
    const lacunas = within(resposta).getByRole("region", { name: "O que a base não tem" });
    expect(within(lacunas).getByText("Não temos o faturamento de empresa fechada.")).toBeTruthy();
    // a lacuna sai do corpo da resposta: aparece uma vez só
    expect(within(resposta).getAllByText("Não temos o faturamento de empresa fechada.")).toHaveLength(1);
    expect(within(resposta).getByText("Resposta escrita por IA com os dados do TickerLab.")).toBeTruthy();
    const lateral = screen.getByRole("complementary", { name: "Nesta conversa" });
    expect(lateral.textContent).toContain("Receita Federal");
    expect(lateral.textContent).toContain("Prospectar empresas × 1");
    expect(lateral.textContent).toContain("12345678000190");
    expect(screen.getByLabelText("Cota e teto").textContent).toContain("Hoje: 3 de 20");
  });

  it("a segunda pergunta leva a primeira troca como histórico", async () => {
    const corpos: unknown[] = [];
    abrirChat(PRONTO, (c) => {
      corpos.push(c);
      return linhas([{ tipo: "texto", texto: `Resposta ${corpos.length}.` }, FIM]);
    });
    await perguntar("Primeira?");
    await screen.findByText("Resposta 1.", {}, { timeout: 5000 });
    await perguntar("Segunda?");
    await screen.findByText("Resposta 2.", {}, { timeout: 5000 });
    expect(corpos[1]).toEqual({
      pergunta: "Segunda?",
      historico: [{ pergunta: "Primeira?", resposta: "Resposta 1." }],
    });
  });

  it("o recomeço descarta só o texto da volta que recomeçou", async () => {
    abrirChat(PRONTO, () =>
      linhas([
        { tipo: "texto", texto: "Vou consultar." },
        { tipo: "ferramenta", nome: "prospectar", titulo: "Prospectar empresas", filtros: {} },
        { tipo: "texto", texto: "Texto que não vale" },
        { tipo: "recomeco" },
        { tipo: "texto", texto: "Texto que vale." },
        FIM,
      ]),
    );
    await perguntar("Pergunta?");
    await screen.findByText("Texto que vale.", {}, { timeout: 5000 });
    expect(screen.getByText("Vou consultar.")).toBeTruthy();
    expect(screen.queryByText(/Texto que não vale/)).toBeNull();
  });

  it("cota acabada (429): mostra a recusa e trava a caixa", async () => {
    abrirChat(PRONTO, () =>
      respostaJson(429, { detail: "Você chegou ao limite de perguntas de hoje; ele volta amanhã." }),
    );
    await perguntar("Pergunta?");
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0), { timeout: 5000 });
    expect(screen.getAllByText("Você chegou ao limite de perguntas de hoje; ele volta amanhã.").length).toBeGreaterThan(0);
    expect((screen.getByRole("textbox", { name: "Sua pergunta" }) as HTMLTextAreaElement).disabled).toBe(true);
    // a pergunta recusada não conta na cota da tela
    expect(screen.getByLabelText("Cota e teto").textContent).toContain("Hoje: 2 de 20");
  });

  it("chat desligado na hora da pergunta (503): mostra a mensagem do servidor", async () => {
    abrirChat(PRONTO, () => respostaJson(503, { detail: "Chat não disponível." }));
    await perguntar("Pergunta?");
    expect(await screen.findByText("Chat não disponível.", {}, { timeout: 5000 })).toBeTruthy();
  });

  it("o erro no meio da resposta aparece como alerta", async () => {
    abrirChat(PRONTO, () =>
      linhas([{ tipo: "texto", texto: "Começo." }, { tipo: "erro", mensagem: "O chat falhou no meio." }]),
    );
    await perguntar("Pergunta?");
    const alerta = await screen.findByText("O chat falhou no meio.", {}, { timeout: 5000 });
    expect(alerta.getAttribute("role")).toBe("alert");
  });

  it("HTML no texto do modelo aparece como texto, nunca como elemento", async () => {
    abrirChat(PRONTO, () =>
      linhas([{ tipo: "texto", texto: 'Veja <img src=x onerror="alert(1)"> e [link](https://exemplo.test).' }, FIM]),
    );
    await perguntar("Pergunta?");
    const resposta = await screen.findByRole("article", { name: "Resposta" }, { timeout: 5000 });
    await waitFor(() => expect(resposta.textContent).toContain("<img src=x"));
    expect(resposta.querySelector("img")).toBeNull();
    expect(resposta.querySelector("a")).toBeNull();
  });

  it("o estado fora do ar mostra o erro da tela", async () => {
    abrirApp("/perguntar", {
      rotas: (e) => (e === ROTA_DO_ESTADO ? respostaJson(500, { detail: "falhou" }) : undefined),
    });
    expect(await screen.findByRole("alert", {}, { timeout: 5000 })).toBeTruthy();
  });
});

describe("conta do chat (chat.ts)", () => {
  it("linha estranha é ignorada", () => {
    expect(eventoDaLinha(null)).toBeNull();
    expect(eventoDaLinha({ tipo: "outro" })).toBeNull();
    expect(eventoDaLinha({ tipo: "texto", texto: "a" })).toEqual({ tipo: "texto", texto: "a" });
  });

  it("a ferramenta abre parágrafo novo e o recomeço volta só até ele", () => {
    let t = trocaNova(1, "p");
    t = comEvento(t, { tipo: "texto", texto: "Antes." });
    t = comEvento(t, { tipo: "ferramenta", nome: "n", titulo: "T", filtros: {} });
    t = comEvento(t, { tipo: "texto", texto: "parcial" });
    t = comEvento(t, { tipo: "recomeco" });
    expect(t.texto).toBe("Antes.\n\n");
    expect(t.consultando).toEqual([{ nome: "n", titulo: "T" }]);
    t = comEvento(t, FIM);
    expect(t.situacao).toBe("pronta");
    expect(t.consultando).toEqual([]);
  });

  it("separa a seção e os parágrafos do que a base não tem", () => {
    const { corpo, lacunas } = separarLacunas(
      "Corpo.\n\nNão temos A.\n\n### O que a base não tem\n\n- B\n- C\n\n## Outra\n\nFim.",
    );
    expect(lacunas).toEqual(["Não temos A.", "B", "C"]);
    expect(corpo.map((b) => b.tipo)).toEqual(["paragrafo", "titulo", "paragrafo"]);
  });

  it("o histórico leva só as trocas prontas, as últimas, cortadas no tamanho", () => {
    const pronta = (id: number, texto: string) => ({ ...trocaNova(id, `p${id}`), texto, situacao: "pronta" as const });
    const trocas = [pronta(1, "um"), pronta(2, "dois"), { ...trocaNova(3, "p3"), situacao: "erro" as const }];
    expect(historicoParaEnviar(trocas, 1, 10, 2)).toEqual([{ pergunta: "p2", resposta: "do" }]);
    expect(historicoParaEnviar(trocas, 0, 10, 10)).toEqual([]);
  });

  it("junta as fontes com a data mais nova e acha os CNPJs dos filtros", () => {
    const consulta = FIM.tipo === "fim" ? FIM.como_cheguei_aqui[0] : null;
    if (consulta === null) throw new Error("exemplo sem consulta");
    const outra = { ...consulta, filtros: { cnpj_raiz: "12345678", uf: "SC" }, fontes: [{ ...consulta.fontes[0], publicado_em: "2026-11-01" }] };
    const trocas = [{ ...trocaNova(1, "p"), comoChegueiAqui: [consulta, outra] }];
    expect(fontesDaConversa(trocas)).toEqual([
      { fonte: "rfb_cnpj", atribuicao: "Receita Federal", licenca: null, publicado_em: "2026-11-01" },
    ]);
    expect(cnpjsDaConversa(trocas)).toEqual(["12345678000190", "12345678"]);
  });

  it("formata a duração", () => {
    expect(formatarDuracao(420)).toBe("420 ms");
    expect(formatarDuracao(1840)).toBe("1,8 s");
  });

  it("o Markdown lê títulos, listas e tabelas", () => {
    expect(blocosDoMarkdown("# T\n\n1. a\n2. b\n\n| x | y |\n|---|---|\n| 1 | 2 |")).toEqual([
      { tipo: "titulo", nivel: 2, texto: "T" },
      { tipo: "lista", ordenada: true, itens: ["a", "b"] },
      { tipo: "tabela", cabecalho: ["x", "y"], linhas: [["1", "2"]] },
    ]);
  });
});

describe("contrato do chat", () => {
  it("EstadoDoChatV1 bate com o OpenAPI", () => {
    const esquemas = JSON.parse(
      readFileSync(join(process.cwd(), "..", "docs", "api", "openapi-v1.json"), "utf8"),
    ).components.schemas;
    expect(Object.keys(PRONTO).sort()).toEqual(Object.keys(esquemas.EstadoDoChatV1.properties).sort());
  });

  it("pedirEmLinhas junta a linha que chegou partida em dois pedaços", async () => {
    const pedacos = ['{"tipo":"texto","te', 'xto":"a"}\n{"tipo":"recomeco"}\n'];
    const corpo = new ReadableStream<Uint8Array>({
      start(controle) {
        for (const p of pedacos) controle.enqueue(new TextEncoder().encode(p));
        controle.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(corpo, { status: 200 })));
    const eventos: unknown[] = [];
    await pedirEmLinhas("/v1/chat", SESSAO, { pergunta: "p" }, (e) => eventos.push(e));
    expect(eventos).toEqual([{ tipo: "texto", texto: "a" }, { tipo: "recomeco" }]);
  });

  it("pedirEmLinhas: linha que não é JSON vira erro da API", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("não é json\n", { status: 200 })));
    await expect(pedirEmLinhas("/v1/chat", SESSAO, {}, () => {})).rejects.toBeInstanceOf(ErroDaApi);
  });

  it("pedirEmLinhas recusa rota fora da v1", async () => {
    await expect(pedirEmLinhas("https://fora.test/x", SESSAO, {}, () => {})).rejects.toThrow(/fora da API v1/);
  });
});
