// O cliente da API de leitura: endereço, token, parâmetros e o que fazer com cada erro.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErroDaApi, pedir } from "../../src/app/api";
import type {
  BacktestDoAtivoV1,
  ComparacaoDoAtivoV1,
  EuV1,
  RetornoMensalDoAtivoV1,
  RiscoDoAtivoV1,
  JurosEInflacaoV1,
  LinhaDoTempoDoAtivoV1,
  VisaoGeralV1,
} from "../../src/app/tipos";
import backtest from "./exemplos/backtest.json";
import comparacao from "./exemplos/comparacao.json";
import juros from "./exemplos/juros_e_inflacao.json";
import linha from "./exemplos/linha_do_tempo.json";
import mensal from "./exemplos/retorno_mensal.json";
import risco from "./exemplos/risco.json";
import exemplo from "./exemplos/visao_geral.json";

function respostaJson(status: number, corpo: unknown, cabecalhos: Record<string, string> = {}) {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json", ...cabecalhos },
  });
}

function comResposta(resposta: Response | Error) {
  const buscar = vi.fn(async () => {
    if (resposta instanceof Error) throw resposta;
    return resposta;
  });
  vi.stubGlobal("fetch", buscar);
  return buscar;
}

async function erroDe(promessa: Promise<unknown>): Promise<ErroDaApi> {
  try {
    await promessa;
  } catch (erro) {
    if (erro instanceof ErroDaApi) return erro;
    throw erro;
  }
  throw new Error("o pedido não falhou");
}

afterEach(() => vi.unstubAllGlobals());

describe("pedir", () => {
  it("chama /api/v1 no próprio endereço, com o token e os parâmetros", async () => {
    const buscar = comResposta(respostaJson(200, { ok: true }));
    await pedir("/v1/comparacao", "tok", { ticker: "PETR4", com: ["VALE3", "AAPL"], taxa: undefined });
    expect(buscar).toHaveBeenCalledWith("/api/v1/comparacao?ticker=PETR4&com=VALE3&com=AAPL", {
      method: "GET",
      headers: { Authorization: "Bearer tok" },
    });
  });

  it("POST manda o corpo em JSON", async () => {
    const buscar = comResposta(respostaJson(200, {}));
    await pedir("/v1/backtest", "tok", {}, { ticker: "PETR4" });
    expect(buscar).toHaveBeenCalledWith("/api/v1/backtest", {
      method: "POST",
      headers: { Authorization: "Bearer tok", "Content-Type": "application/json" },
      body: '{"ticker":"PETR4"}',
    });
  });

  it("recusa rota que não seja da API v1 (o token nunca sai para outro endereço)", async () => {
    const buscar = comResposta(respostaJson(200, {}));
    for (const rota of ["https://outro.com/v1/eu", "//outro.com/v1/eu", "/v1/../../x", "/saude"]) {
      await expect(pedir(rota, "tok")).rejects.toThrow(/rota/);
    }
    expect(buscar).not.toHaveBeenCalled();
  });
});

describe("erros", () => {
  it.each([
    [401, "token-invalido", "sessao-vencida"],
    [401, "sem-token", "sessao-vencida"],
    [401, "conta-nova", "conta-nova"],
    [403, "termos", "termos"],
  ])("%i com motivo %s vira %s", async (status, motivo, tipo) => {
    comResposta(respostaJson(status, { detail: "Texto da API." }, { "X-TickerLab-Motivo": motivo }));
    const erro = await erroDe(pedir("/v1/eu", "tok"));
    expect(erro.tipo).toBe(tipo);
    expect(erro.message).toBe("Texto da API.");
  });

  it.each([
    [404, "nao-encontrado"],
    [429, "limite"],
    [503, "indisponivel"],
    [500, "indisponivel"],
  ])("%i vira %s com a mensagem da API", async (status, tipo) => {
    comResposta(respostaJson(status, { detail: "Mensagem em português." }));
    const erro = await erroDe(pedir("/v1/visao-geral", "tok"));
    expect(erro.tipo).toBe(tipo);
    expect(erro.message).toBe("Mensagem em português.");
  });

  it("422 de validação (lista de campos) vira uma frase só", async () => {
    comResposta(respostaJson(422, { detail: [{ loc: ["query", "janela"], msg: "too big" }] }));
    const erro = await erroDe(pedir("/v1/risco", "tok"));
    expect(erro.tipo).toBe("pedido-invalido");
    expect(erro.message).toMatch(/fora dos limites/);
  });

  it("422 com texto (período curto) mostra o texto", async () => {
    comResposta(respostaJson(422, { detail: "Só há 10 dias de dados." }));
    expect((await erroDe(pedir("/v1/risco", "tok"))).message).toBe("Só há 10 dias de dados.");
  });

  it("sem rede vira um aviso simples", async () => {
    comResposta(new TypeError("Failed to fetch"));
    const erro = await erroDe(pedir("/v1/eu", "tok"));
    expect(erro.tipo).toBe("rede");
    expect(erro.message).toMatch(/conexão/);
  });
});

describe("tipos das respostas", () => {
  // o TypeScript confere que o exemplo tem exatamente os campos da interface; o teste confere que
  // a interface tem exatamente os campos do esquema publicado da API
  const esquemas = JSON.parse(
    readFileSync(join(process.cwd(), "..", "docs", "api", "openapi-v1.json"), "utf8"),
  ).components.schemas;
  const campos = (nome: string) => Object.keys(esquemas[nome].properties).sort();

  it("EuV1 e LimitesV1 batem com o OpenAPI", () => {
    const eu: EuV1 = {
      nome: "Ana",
      plano: "gratuito",
      administrador: false,
      limites: {
        simulacoes: 5,
        favoritos: 3,
        ativos_na_carteira: 4,
        relatorios_por_dia: 3,
        recursos: [],
      },
    };
    expect(Object.keys(eu).sort()).toEqual(campos("EuV1"));
    expect(Object.keys(eu.limites).sort()).toEqual(campos("LimitesV1"));
  });

  it("VisaoGeralV1 (a resposta de exemplo do Python) bate com o OpenAPI", () => {
    const resposta: VisaoGeralV1 = exemplo.resposta;
    expect(Object.keys(resposta).sort()).toEqual(campos("VisaoGeralV1"));
    expect(Object.keys(resposta.ativo).sort()).toEqual(campos("AtivoV1"));
    expect(Object.keys(resposta.painel).sort()).toEqual(campos("PainelDeNumerosV1"));
    expect(Object.keys(resposta.curva).sort()).toEqual(campos("CurvaV1"));
  });

  it("Juros e inflação e Linha do tempo (exemplos do Python) batem com o OpenAPI", () => {
    const j: JurosEInflacaoV1 = juros.resposta;
    expect(Object.keys(j).sort()).toEqual(campos("JurosEInflacaoV1"));
    expect(Object.keys(j.numeros[0]).sort()).toEqual(campos("NumeroDeJurosV1"));
    expect(Object.keys(j.expectativas[0]).sort()).toEqual(campos("ExpectativaV1"));
    expect(Object.keys(j.historico[0]).sort()).toEqual(campos("PontoMensalV1"));
    const l: LinhaDoTempoDoAtivoV1 = linha.resposta;
    expect(Object.keys(l).sort()).toEqual(campos("LinhaDoTempoDoAtivoV1"));
    expect(Object.keys(l.linha_do_tempo).sort()).toEqual(campos("LinhaDoTempoV1"));
    expect(Object.keys(l.linha_do_tempo.marcos[0]).sort()).toEqual(campos("MarcoV1"));
  });

  it("Risco, Retorno mensal e Comparação (exemplos do Python) batem com o OpenAPI", () => {
    const r: RiscoDoAtivoV1 = risco.resposta;
    expect(Object.keys(r.risco).sort()).toEqual(campos("RiscoV1"));
    expect(Object.keys(r.risco.pior_queda).sort()).toEqual(campos("PiorQuedaV1"));
    const m: RetornoMensalDoAtivoV1 = mensal.resposta;
    expect(Object.keys(m.retorno_mensal).sort()).toEqual(campos("RetornoMensalV1"));
    expect(Object.keys(m.retorno_mensal.tabela[0]).sort()).toEqual(campos("AnoV1"));
    const c: ComparacaoDoAtivoV1 = comparacao.resposta;
    expect(Object.keys(c).sort()).toEqual(campos("ComparacaoDoAtivoV1"));
    expect(Object.keys(c.comparacao).sort()).toEqual(campos("ComparacaoV1"));
    expect(Object.keys(c.comparacao.tabela?.[0] ?? {}).sort()).toEqual(campos("LinhaDaComparacaoV1"));
  });

  it("Backtest (exemplo do Python) bate com o OpenAPI", () => {
    const b: BacktestDoAtivoV1 = backtest.resposta;
    expect(Object.keys(b).sort()).toEqual(campos("BacktestDoAtivoV1"));
    expect(Object.keys(b.backtest).sort()).toEqual(campos("BacktestV1"));
  });
});
