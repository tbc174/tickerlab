// @vitest-environment jsdom
// Mapa do café no app novo, com a resposta de exemplo gerada pelo Python
// (tests/test_app_novo_mesmos_numeros.py: o arábica em novembro, 5 municípios, só Linhares na malha).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pedir } from "../../src/app/api";
import type { MapaDoCafeV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";
import mapa from "./exemplos/mapa_do_cafe.json";

const LINHARES = "3203205";
const PATOS_DE_MINAS = "3148004";
// o JSON importado vira tipos literais (cada sem_dado com as suas chaves); o teste do OpenAPI abaixo
// confere que o formato é mesmo o MapaDoCafeV1
const resposta = mapa.resposta as unknown as MapaDoCafeV1;

function abrir(responder = () => respostaJson(200, resposta)) {
  return abrirApp("/mapa-do-cafe", {
    rotas: (endereco) => (endereco.startsWith("/api/v1/commodities/cafe/mapa") ? responder() : undefined),
  });
}

// a 1ª pintura do mapa (a malha e os 5 municípios) passa de 1 s quando a máquina está carregada
function esperarOMapa(nome: RegExp = /Produção/) {
  return screen.findByRole("img", { name: nome }, { timeout: 5000 });
}

function contorno(codigo: string) {
  return document.querySelector(`path[data-codigo="${codigo}"]`) as SVGPathElement;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("mapa do café", () => {
  it("pinta de cinza, com o motivo, o município sem o café do tipo", async () => {
    abrir();
    await esperarOMapa(/Produção de café arábica/);
    const linhares = contorno(LINHARES);
    expect(linhares.classList.contains("sem-dado")).toBe(true);
    expect(linhares.textContent).toContain("a PAM não registra café arábica neste município em 2025");
    const caixa = screen.getByRole("region", { name: resposta.camadas[0].titulo });
    expect(within(caixa).getByText(resposta.camadas[0].fonte)).toBeTruthy();
  });

  it("a camada de chuva pinta pela região, com a normal na legenda", async () => {
    abrir();
    await esperarOMapa();
    fireEvent.change(screen.getByLabelText("Camada"), { target: { value: "chuva" } });
    expect(await screen.findByRole("img", { name: /Chuva dos últimos 3 meses/ })).toBeTruthy();
    expect(contorno(LINHARES).classList.contains("sem-dado")).toBe(false);
    expect(contorno(LINHARES).textContent).toContain("75,00% da normal");
    expect(within(screen.getByRole("list", { name: "Legenda do mapa" })).getByText("na normal")).toBeTruthy();
  });

  it("escolher o município abre a ficha com a PAM, o clima e a fase do mês", async () => {
    abrir();
    await esperarOMapa();
    fireEvent.change(screen.getByLabelText("Município"), { target: { value: PATOS_DE_MINAS } });
    const ficha = screen.getByRole("region", { name: "Ficha de Patos de Minas" });
    expect(within(ficha).getByText("15.253 t")).toBeTruthy();
    const cerrado = resposta.regioes.find((r) => r.id === "cerrado-mineiro");
    expect(within(ficha).getByText(cerrado?.chuva.texto ?? "?")).toBeTruthy();
    expect(within(ficha).getByText(cerrado?.fase ?? "?")).toBeTruthy();
    expect(within(ficha).getByText("O que o mercado olha na florada")).toBeTruthy();
  });

  it("clicar no contorno também escolhe o município", async () => {
    abrir();
    await esperarOMapa();
    fireEvent.click(contorno(LINHARES));
    expect(screen.getByRole("region", { name: "Ficha de Linhares" })).toBeTruthy();
    expect(contorno(LINHARES).classList.contains("escolhido")).toBe(true);
  });

  it("trocar para conilon pede o mapa do conilon", async () => {
    const { buscar } = abrir();
    await esperarOMapa();
    fireEvent.click(screen.getByLabelText("Conilon (robusta)"));
    await waitFor(() =>
      expect(buscar.mock.calls.some(([endereco]) => String(endereco).includes("tipo=conilon"))).toBe(true),
    );
  });

  it("diz a data do pacote e que não é previsão", async () => {
    abrir();
    await esperarOMapa();
    expect(screen.getByText(/Dados como estavam em 05\/11\/2026/).textContent).toContain("não previsão");
  });

  it("sem pacote no servidor: a mensagem da API", async () => {
    abrir(() => respostaJson(503, { detail: "O mapa do café ainda não foi montado neste servidor." }));
    expect(await screen.findByText(/ainda não foi montado/)).toBeTruthy();
  });

  it("o tipo da resposta bate com o OpenAPI", () => {
    const esquemas = JSON.parse(
      readFileSync(join(process.cwd(), "..", "docs", "api", "openapi-v1.json"), "utf8"),
    ).components.schemas;
    const campos = (nome: string) => Object.keys(esquemas[nome].properties).sort();
    expect(Object.keys(resposta).sort()).toEqual(campos("MapaDoCafeV1"));
    expect(Object.keys(resposta.camadas[0]).sort()).toEqual(campos("CamadaDoMapaV1"));
    expect(Object.keys(resposta.municipios[0]).sort()).toEqual(campos("MunicipioDoMapaV1"));
    expect(Object.keys(resposta.regioes[0]).sort()).toEqual(campos("RegiaoDoMapaV1"));
    expect(Object.keys(resposta.regioes[0].chuva).sort()).toEqual(campos("IndiceDoMapaV1"));
    expect(Object.keys(resposta.regioes[0].o_que_o_mercado_olha[0]).sort()).toEqual(campos("ItemDoMesV1"));
  });
});

describe("rotas da v1 com mais de um pedaço", () => {
  it("o cliente aceita /v1/commodities/cafe/mapa e continua recusando o que sai da v1", async () => {
    for (const rota of ["/v1/commodities/../eu", "/v1/commodities/cafe/", "/v1//mapa", "/v2/mapa", "//outro.site/v1/a"]) {
      await expect(pedir(rota, "token"), rota).rejects.toThrow("rota fora da API v1");
    }
    vi.stubGlobal("fetch", vi.fn(async () => respostaJson(200, resposta)));
    await expect(pedir("/v1/commodities/cafe/mapa", "token")).resolves.toEqual(resposta);
  });
});
