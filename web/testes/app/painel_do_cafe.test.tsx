// @vitest-environment jsdom
// Painel do café no app novo, com a resposta de exemplo gerada pelo Python
// (tests/test_painel_do_cafe.py: o painel "como estava" em 01/05/2026, dados semeados à mão).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PainelDoCafeV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";
import exemplo from "./exemplos/painel_do_cafe.json";

const resposta: PainelDoCafeV1 = exemplo.resposta;
const CHAVES_DOS_BLOCOS = [
  "preco_de_referencia",
  "cambio",
  "fundos",
  "exportacoes",
  "balanco",
  "safra",
  "termometro",
  "bienalidade",
  "clima",
  "calendario",
  "contrapartes",
] as const;

function abrir(caminho = "/painel-do-cafe", corpo: () => Response = () => respostaJson(200, resposta)) {
  return abrirApp(caminho, {
    rotas: (endereco) => (endereco.startsWith("/api/v1/painel-do-cafe") ? corpo() : undefined),
  });
}

/** O valor de um número do painel, achado pelo rótulo dentro da caixa. */
function valorDo(caixa: HTMLElement, rotulo: string) {
  const numero = within(caixa).getByText(rotulo, { exact: true }).closest(".numero-do-painel") as HTMLElement;
  return numero.querySelector(".numero-valor")?.textContent;
}

const pedidos = (buscar: ReturnType<typeof vi.fn>) =>
  buscar.mock.calls.map(([e]) => String(e)).filter((e) => e.startsWith("/api/v1/painel-do-cafe"));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("painel do café", () => {
  it("pede o arábica por padrão e mostra o aviso do preço mensal", async () => {
    const { buscar } = abrir();
    await screen.findByRole("region", { name: resposta.preco_de_referencia.titulo });
    expect(pedidos(buscar)).toContain("/api/v1/painel-do-cafe?tipo=arabica");
    // o aviso fica fixo na tela (até antes da resposta) e é o mesmo texto do Python
    expect(screen.getByText(resposta.aviso_diario).closest('[role="note"]')).not.toBeNull();
  });

  it("cada caixa tem o que é, a fonte e a data do número mais novo", async () => {
    abrir();
    await screen.findByRole("region", { name: resposta.preco_de_referencia.titulo });
    for (const chave of CHAVES_DOS_BLOCOS) {
      const bloco = resposta[chave];
      const caixa = screen.getByRole("region", { name: bloco.titulo });
      expect(within(caixa).getByText(bloco.o_que_e), chave).toBeTruthy();
      expect(caixa.querySelector(".fonte-do-bloco")?.textContent, chave).toContain(bloco.fonte);
      if (bloco.data) {
        const [ano, mes, dia] = bloco.data.split("-");
        expect(caixa.querySelector(".fonte-do-bloco")?.textContent, chave).toContain(`${dia}/${mes}/${ano}`);
      }
    }
  });

  it("os números com vírgula e ponto de milhar, e os gráficos de preço, câmbio e fundos", async () => {
    abrir();
    const preco = await screen.findByRole("region", { name: resposta.preco_de_referencia.titulo });
    expect(valorDo(preco, `${resposta.preco_de_referencia.conteudo?.item.nome} (US$/kg)`)).toBe("8,59");
    expect(within(preco).getByRole("img", { name: /média mensal/ })).toBeTruthy();
    expect(within(preco).getByRole("img", { name: /Spread arábica menos robusta/ })).toBeTruthy();
    const fundos = screen.getByRole("region", { name: resposta.fundos.titulo });
    expect(valorDo(fundos, "Posição líquida (lotes)")).toBe("40.000");
    expect(valorDo(fundos, "Em sacas de 60 kg")).toBe("11.339.809");
    expect(valorDo(fundos, "Fatia do interesse aberto")).toBe("20,00%");
    expect(within(fundos).getByText(resposta.fundos.conteudo?.legenda ?? "")).toBeTruthy();
  });

  it("o termômetro mostra o erro de cada safra fechada, com sinal", async () => {
    abrir();
    const caixa = await screen.findByRole("region", { name: resposta.termometro.titulo });
    const tabela = within(caixa).getByRole("table");
    const linha = within(tabela).getByText("2018").closest("tr") as HTMLElement;
    expect(within(linha).getByText("+4,17%")).toBeTruthy();
    expect(within(linha).getByText("2.000")).toBeTruthy();
  });

  it("as contrapartes só com fatos datados, o link da fonte e o que não sabemos", async () => {
    abrir();
    const caixa = await screen.findByRole("region", { name: resposta.contrapartes.titulo });
    const ficha = resposta.contrapartes.conteudo?.fichas[0];
    if (!ficha) throw new Error("o exemplo tem contrapartes");
    const artigo = within(caixa).getByRole("article", { name: ficha.nome });
    const link = within(artigo).getAllByRole("link")[0];
    expect(link.getAttribute("href")).toBe(ficha.fatos[0].fonte);
    expect(within(artigo).getByText(ficha.o_que_nao_sabemos[0])).toBeTruthy();
    // sem nota, selo nem recomendação até a ADR da confiança da contraparte (PR 13)
    expect(caixa.querySelectorAll(".selo, .nota-da-contraparte")).toHaveLength(0);
    expect(caixa.textContent).not.toMatch(/recomend|confiável|seguro/i);
  });

  it("trocar para conilon pede o conilon e volta à região padrão", async () => {
    const { buscar } = abrir("/painel-do-cafe?tipo=arabica&regiao=cerrado-mineiro");
    await screen.findByRole("region", { name: resposta.preco_de_referencia.titulo });
    fireEvent.click(screen.getByRole("button", { name: "Conilon (robusta)" }));
    await waitFor(() => expect(pedidos(buscar)).toContain("/api/v1/painel-do-cafe?tipo=conilon"));
  });

  it("a região é escolhida pelo nome, na lista que a API manda", async () => {
    const { buscar } = abrir();
    const seletor = await screen.findByRole("combobox", { name: /Região do clima/ });
    expect(within(seletor).getAllByRole("option")).toHaveLength(resposta.regioes.length);
    fireEvent.change(seletor, { target: { value: "cerrado-mineiro" } });
    await waitFor(() =>
      expect(pedidos(buscar)).toContain("/api/v1/painel-do-cafe?tipo=arabica&regiao=cerrado-mineiro"),
    );
  });

  it("caixa sem dado diz 'Sem dado' com o motivo", async () => {
    const motivo = "A tabela `cftc_cot_agro` ainda não chega à base deste servidor.";
    const semFundos = { ...resposta, fundos: { ...resposta.fundos, data: null, conteudo: null, motivo_sem_dado: motivo } };
    abrir("/painel-do-cafe", () => respostaJson(200, semFundos));
    const caixa = await screen.findByRole("region", { name: resposta.fundos.titulo });
    expect(caixa.querySelector(".sem-dado-do-cafe")?.textContent).toBe(`Sem dado. ${motivo}`);
  });

  it("erro da API: a mensagem dela", async () => {
    abrir("/painel-do-cafe", () => respostaJson(422, { detail: "Região de café desconhecida: x." }));
    expect(await screen.findByText(/Região de café desconhecida/)).toBeTruthy();
  });
});
