// @vitest-environment jsdom
// Risco, Retorno mensal e Comparar no app novo, com as respostas de exemplo do Python
// (tests/test_app_novo_mesmos_numeros.py): os números têm de sair como no Streamlit.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { conteudoDoApp } from "../../src/conteudo";
import { abrirApp, respostaJson } from "./ajudantes";
import comparacao from "./exemplos/comparacao.json";
import mensal from "./exemplos/retorno_mensal.json";
import risco from "./exemplos/risco.json";

function abrirCom(caminho: string, rota: string, resposta: () => Response) {
  return abrirApp(caminho, {
    rotas: (endereco) => (endereco.startsWith(`/api/v1/${rota}?`) ? resposta() : undefined),
  });
}
const enderecos = (buscar: ReturnType<typeof abrirApp>["buscar"]) => buscar.mock.calls.map(([e]) => String(e));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("risco", () => {
  it("a frase da pior queda e os dois gráficos (queda desde o topo e volatilidade móvel)", async () => {
    const { buscar } = abrirCom("/risco", "risco", () => respostaJson(200, risco.resposta));
    expect(await screen.findByText(risco.resposta.risco.frase_da_pior_queda)).toBeTruthy();
    expect(screen.getByRole("img", { name: /Queda desde o topo de PETR4$/ })).toBeTruthy();
    expect(screen.getByRole("img", { name: /Volatilidade móvel de 20 dias/ })).toBeTruthy();
    expect(enderecos(buscar)).toContain("/api/v1/risco?ticker=PETR4.SA&periodo=2y&janela=20");
  });

  it("janela maior que o período: o aviso no lugar do gráfico da volatilidade", async () => {
    abrirCom("/risco?periodo=6mo&janela=252", "risco", () => respostaJson(200, risco.curto));
    expect(await screen.findByText(risco.curto.risco.aviso_da_janela as string)).toBeTruthy();
    expect(screen.queryByRole("img", { name: /Volatilidade móvel/ })).toBeNull();
  });
});

describe("retorno mensal", () => {
  const abrir = () => abrirCom("/retorno-mensal", "retorno-mensal", () => respostaJson(200, mensal.resposta));

  it("os três cartões iguais aos do Streamlit", async () => {
    abrir();
    const painel = await screen.findByRole("region", { name: "Retorno por mês e ano" });
    for (const [rotulo, valor] of Object.entries(mensal.na_tela)) {
      const numero = within(painel).getByText(rotulo, { exact: true }).closest(".numero-do-painel");
      expect(numero, rotulo).not.toBeNull();
      expect(within(numero as HTMLElement).getByText(valor, { exact: true }), rotulo).toBeTruthy();
    }
  });

  it("o mapa: um ano por linha, os 12 meses, o ano inteiro e a média de cada mês", async () => {
    abrir();
    const mapa = await screen.findByRole("table", { name: /Retorno de cada mês/ });
    const linhas = within(mapa).getAllByRole("row");
    // cabeçalho + anos + média
    expect(linhas).toHaveLength(1 + mensal.resposta.retorno_mensal.tabela.length + 1);
    expect(within(linhas[0]).getAllByRole("columnheader")).toHaveLength(1 + 12 + 1);
    expect(within(linhas[linhas.length - 1]).getByText("Média do mês")).toBeTruthy();
    expect(screen.getByText(conteudoDoApp.retorno_mensal.legenda, { exact: true })).toBeTruthy();
  });
});

describe("comparar", () => {
  const abrir = (caminho = "/comparar") =>
    abrirCom(caminho, "comparacao", () => respostaJson(200, comparacao.resposta));

  it("pede o ativo do topo contra os atalhos padrão (Ibovespa e S&P 500)", async () => {
    const { buscar } = abrir();
    await screen.findByRole("table", { name: "Números no mesmo período" });
    expect(enderecos(buscar)).toContain(
      "/api/v1/comparacao?ticker=PETR4.SA&com=%5EBVSP&com=%5EGSPC&periodo=2y",
    );
  });

  it("a tabela mostra cada ativo com os números do Streamlit", async () => {
    abrir();
    const tabela = await screen.findByRole("table", { name: "Números no mesmo período" });
    // o Streamlit ainda mostra "PETR4.SA"; o app novo mostra o código (PETR4)
    const codigos = Object.fromEntries(
      (comparacao.resposta.comparacao.tabela ?? []).map((l) => [l.ticker, l.codigo]),
    );
    for (const [nome, colunas] of Object.entries(comparacao.na_tela)) {
      const linha = within(tabela).getByText(codigos[nome] ?? nome, { exact: true }).closest("tr") as HTMLElement;
      for (const [coluna, valor] of Object.entries(colunas)) {
        expect(within(linha).getByText(valor, { exact: true }), `${nome} ${coluna}`).toBeTruthy();
      }
    }
    expect(screen.getByText(comparacao.resposta.comparacao.nota as string)).toBeTruthy();
  });

  it("o gráfico em base 100 com uma linha e uma legenda por ativo", async () => {
    abrir();
    const grafico = await screen.findByRole("img", { name: /em base 100/ });
    expect(grafico.querySelectorAll("path.grafico-linha")).toHaveLength(3);
    const legenda = screen.getByRole("list", { name: "Legenda" }).textContent ?? "";
    for (const nome of ["PETR4", "Ibovespa", "S&P 500"]) expect(legenda).toContain(nome);
  });

  it("desmarcar um atalho e digitar outro ativo muda o pedido", async () => {
    const { buscar } = abrir();
    await screen.findByRole("table", { name: "Números no mesmo período" });
    fireEvent.click(screen.getByRole("checkbox", { name: "S&P 500" }));
    fireEvent.change(screen.getByLabelText(/Outros tickers/), { target: { value: "VALE3, AAPL" } });
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    await waitFor(() =>
      expect(enderecos(buscar)).toContain(
        "/api/v1/comparacao?ticker=PETR4.SA&com=%5EBVSP&com=VALE3&com=AAPL&periodo=2y",
      ),
    );
  });

  it("mais de 5 ativos: avisa quem ficou de fora e pede só os 4 primeiros", async () => {
    const { buscar } = abrir("/comparar?com=%5EBVSP&com=%5EGSPC&com=VALE3&com=AAPL&com=ITUB4");
    expect(await screen.findByText(/Ficaram de fora: ITUB4/)).toBeTruthy();
    // o aviso sai da URL antes do pedido à API: espere o pedido (sem isso o teste falha às vezes)
    await waitFor(() =>
      expect(enderecos(buscar)).toContain(
        "/api/v1/comparacao?ticker=PETR4.SA&com=%5EBVSP&com=%5EGSPC&com=VALE3&com=AAPL&periodo=2y",
      ),
    );
  });

  it("poucos dias em comum: o aviso da API no lugar do gráfico", async () => {
    const curta = structuredClone(comparacao.resposta) as typeof comparacao.resposta & {
      comparacao: { curvas: null; tabela: null; nota: null; aviso: string };
    };
    Object.assign(curta.comparacao, { curvas: null, tabela: null, nota: null, aviso: "Só há 8 dias em comum." });
    abrirCom("/comparar", "comparacao", () => respostaJson(200, curta));
    expect(await screen.findByText("Só há 8 dias em comum.")).toBeTruthy();
    expect(screen.queryByRole("img", { name: /em base 100/ })).toBeNull();
  });
});
