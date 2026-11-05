// @vitest-environment jsdom
// O painel de consulta da página Dados (site/ConsultaDaBase.tsx): o botão "Consultar" de uma linha da
// lista escolhe a tabela, o painel pede a amostra à API sem cookie e mostra linhas, total, fonte e
// licença; sem a API, diz que está indisponível. Virada de 5/11/2026, fase 1, PR 3.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import {
  ConsultaDaBase,
  LINHAS_DA_AMOSTRA,
  enderecoDaConsulta,
} from "../../src/site/ConsultaDaBase";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

const ROTA = "https://app.tickerlab.com.br/api/v1/base/tabelas";
const pagina = {
  tabela: "pgfn_divida",
  versao: "1.0.1",
  fonte: "PGFN: dados abertos da dívida ativa.",
  orgao: "PGFN",
  licenca: "Dados abertos da PGFN",
  total: 3,
  limite: LINHAS_DA_AMOSTRA,
  deslocamento: 0,
  como_era_em: null,
  colunas: ["cnpj", "tipo_divida", "ajuizado", "valor_consolidado", "publico_em"],
  linhas: [
    { cnpj: "02.429.144/0001-93", tipo_divida: "Previdenciário", ajuizado: false, valor_consolidado: 99.99, publico_em: "2025-01-31" },
    { cnpj: "11.222.333/0001-81", tipo_divida: "FGTS", ajuizado: true, valor_consolidado: null, publico_em: "2025-04-30" },
  ],
  aviso: "Nada aqui é recomendação de investimento.",
};

/** Um botão como o da lista de tabelas da página Dados, fora do painel. */
function botaoDaLista(tabela = "pgfn_divida") {
  const botao = document.createElement("button");
  botao.dataset.consultar = tabela;
  botao.textContent = "Ver";
  document.body.append(botao);
  return botao;
}

const responder = (corpo: unknown, status = 200) =>
  vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => corpo });

it("o botão da lista escolhe a tabela e o painel mostra linhas, total, fonte, licença e o CSV", async () => {
  const fetch = responder(pagina);
  vi.stubGlobal("fetch", fetch);
  render(<ConsultaDaBase />);
  fireEvent.click(botaoDaLista());
  expect(await screen.findByText("3 linhas")).toBeTruthy();
  expect(fetch.mock.calls[0][0]).toBe(`${ROTA}/pgfn_divida?limite=${LINHAS_DA_AMOSTRA}`);
  expect(fetch.mock.calls[0][1].credentials).toBe("omit");
  expect(screen.getByText(/mostrando as primeiras 2/)).toBeTruthy();
  expect(screen.getByText(/Fonte: PGFN: dados abertos da dívida ativa\./)).toBeTruthy();
  expect(screen.getByText(/Licença: Dados abertos da PGFN/)).toBeTruthy();
  expect(screen.getByText(/Consulta em \d{2}\/\d{2}\/\d{4}/)).toBeTruthy();
  expect(screen.getAllByRole("columnheader").map((c) => c.textContent)).toEqual(pagina.colunas);
  expect(screen.getByText("02.429.144/0001-93")).toBeTruthy();
  expect(screen.getByText("sim")).toBeTruthy(); // ajuizado = true, em português
  expect(screen.getByText("não")).toBeTruthy();
  expect(screen.getByText("Nada aqui é recomendação de investimento.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Baixar a tabela em CSV" }).getAttribute("href")).toBe(
    `${ROTA}/pgfn_divida.csv`,
  );
  expect(screen.getByText("pgfn_divida")).toBeTruthy(); // a tabela escolhida fica escrita no painel
});

it("o CNPJ digitado entra na consulta e no link do CSV; total de uma linha fica no singular", async () => {
  const fetch = responder({ ...pagina, total: 1, linhas: [pagina.linhas[0]] });
  vi.stubGlobal("fetch", fetch);
  render(<ConsultaDaBase />);
  fireEvent.change(screen.getByLabelText("CNPJ (opcional)"), { target: { value: " 02.429.144/0001-93 " } });
  fireEvent.click(botaoDaLista());
  expect(await screen.findByText("1 linha")).toBeTruthy();
  expect(fetch.mock.calls[0][0]).toBe(enderecoDaConsulta("pgfn_divida", "02.429.144/0001-93", "json"));
  expect(fetch.mock.calls[0][0]).toContain("&cnpj=02.429.144%2F0001-93");
  expect(screen.queryByText(/mostrando as primeiras/)).toBeNull();
  expect(screen.getByRole("link", { name: "Baixar a tabela em CSV" }).getAttribute("href")).toBe(
    `${ROTA}/pgfn_divida.csv?cnpj=02.429.144%2F0001-93`,
  );
});

it("sem linhas, diz que não há o que mostrar, e o CSV continua", async () => {
  vi.stubGlobal("fetch", responder({ ...pagina, total: 0, linhas: [] }));
  render(<ConsultaDaBase />);
  fireEvent.click(botaoDaLista());
  expect(await screen.findByText("0 linhas")).toBeTruthy();
  expect(screen.getByText("Nenhuma linha para mostrar.")).toBeTruthy();
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.getByRole("link", { name: "Baixar a tabela em CSV" })).toBeTruthy();
});

it("a recusa da API aparece com a mensagem dela", async () => {
  vi.stubGlobal(
    "fetch",
    responder({ detail: "cnpj: confira os 14 caracteres e os dígitos verificadores." }, 422),
  );
  render(<ConsultaDaBase />);
  fireEvent.click(botaoDaLista());
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    expect.stringContaining("dígitos verificadores"),
  );
});

it("API fora do ar ou desligada: o painel diz que está indisponível e deixa tentar de novo", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<ConsultaDaBase />);
  fireEvent.click(botaoDaLista());
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    expect.stringContaining("indisponível"),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Consultar" })).toHaveProperty("disabled", false),
  );
  // a API desligada em produção responde o "Not Found" do FastAPI: não é mensagem para quem lê
  vi.stubGlobal("fetch", responder({ detail: "Not Found" }, 404));
  fireEvent.click(screen.getByRole("button", { name: "Consultar" }));
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    expect.stringContaining("indisponível"),
  );
});

it("o HTML pronto só explica como usar: sem linhas, com o botão desligado até escolher a tabela", () => {
  const html = renderToStaticMarkup(<ConsultaDaBase />);
  expect(html).toContain("Escolha uma tabela");
  expect(html).not.toContain("<table");
  expect(html).toMatch(/<button[^>]*disabled=""/);
  expect(html).toContain('id="consulta-da-base"');
});
