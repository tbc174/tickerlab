// @vitest-environment jsdom
// A renda fixa v2: o Tesouro Prefixado e o IPCA+ com a taxa de hoje (o título que vence mais perto
// do prazo), o CDI parado ou seguindo o Focus, o ponto de empate entre LCI/LCA e CDB, o gráfico de
// barras e a tabela com IR, IOF e custódia. Ordem fixa: nada de "a melhor".
import { act, fireEvent, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ligarFerramentas } from "../../src/ferramentas/cliente";
import { pontoDeEmpate } from "../../src/ferramentas/contas/renda_fixa";
import type { DadosDoBc } from "../../src/ferramentas/dados";
import { formatarNumero } from "../../src/ferramentas/numeros";
import { Ilha } from "../../src/ferramentas/registro";

const ontem = new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
const ano = new Date().getFullYear();
const DADOS: DadosDoBc = {
  gerado_em: `${ontem}T13:40:00-03:00`,
  fonte: "Banco Central do Brasil e Tesouro Nacional",
  cdi: { ao_ano: 0.1365, data: ontem },
  selic_meta: { ao_ano: 0.1375, data: ontem },
  poupanca: { ao_mes: 0.006704, data: ontem },
  focus: {
    ipca: { data: ontem, anos: { [ano]: 0.05, [ano + 1]: 0.043, [ano + 2]: 0.038 } },
    selic: { data: ontem, anos: { [ano]: 0.1325, [ano + 1]: 0.12, [ano + 2]: 0.105 } },
  },
  tesouro: {
    data: ontem,
    titulos: [
      { titulo: "Tesouro IPCA+", vencimento: `${ano + 3}-05-15`, taxa: 0.0666 },
      { titulo: "Tesouro IPCA+", vencimento: `${ano + 9}-05-15`, taxa: 0.0669 },
      { titulo: "Tesouro Prefixado", vencimento: `${ano + 1}-01-01`, taxa: 0.1327 },
      { titulo: "Tesouro Prefixado", vencimento: `${ano + 2}-01-01`, taxa: 0.1261 },
      { titulo: "Tesouro Prefixado", vencimento: `${ano + 5}-01-01`, taxa: 0.1243 },
      { titulo: "Tesouro Selic", vencimento: `${ano + 3}-03-01`, taxa: 0.0005 },
    ],
  },
};

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

async function abrir(busca = "") {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(DADOS))));
  window.history.replaceState(null, "", `/calculadora-de-renda-fixa.html${busca}`);
  document.body.innerHTML = renderToStaticMarkup(<Ilha nome="rendaFixa" />);
  await act(async () => {
    ligarFerramentas(document);
  });
  await screen.findAllByText(/CDB/);
}

const linhas = () => [...document.querySelectorAll(".ferramenta-comparacao tbody th")].map((th) => th.textContent);

describe("renda fixa v2", () => {
  it("o Tesouro Prefixado e o IPCA+ entram com o título que vence mais perto do prazo, na ordem fixa", async () => {
    await abrir();
    expect(linhas()).toEqual([
      "CDB",
      "LCI ou LCA",
      "Tesouro Selic",
      "Poupança",
      `Tesouro Prefixado ${ano + 2}`,
      `Tesouro IPCA+ ${ano + 3}`,
    ]);
    expect([...document.querySelectorAll(".grafico-ferramenta-nome")]).toHaveLength(6);
  });

  it("diz o ponto de empate entre a LCI/LCA e o CDB no prazo", async () => {
    await abrir("?cdi=parado");
    const empate = pontoDeEmpate(10000, 730, [0.1365], 0.9);
    expect(document.body.textContent).toContain(`equivale a um CDB de ${formatarNumero(empate * 100)}% do CDI`);
  });

  it("o CDI seguindo o Focus muda o resultado do CDB e diz que é expectativa do mercado", async () => {
    await abrir("?cdi=parado");
    const parado = document.querySelector(".ferramenta-comparacao tbody tr td:last-child")?.textContent;
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Seguindo a Selic esperada (Focus)"));
    });
    const peloFocus = document.querySelector(".ferramenta-comparacao tbody tr td:last-child")?.textContent;
    expect(peloFocus).not.toBe(parado);
    expect(document.body.textContent).toContain("expectativa do mercado");
  });

  it("antes de 30 dias, a tabela mostra o IOF", async () => {
    await abrir("?prazo=10&unidade=dias");
    const cabecalho = [...document.querySelectorAll(".ferramenta-comparacao thead th")].map((th) => th.textContent);
    expect(cabecalho).toContain("IOF");
  });

  it("o Tesouro diz que a taxa é a de hoje, levando até o fim do prazo", async () => {
    await abrir();
    expect(document.body.textContent).toContain("levando até o fim do prazo");
    expect(document.body.textContent).toContain("Tesouro Nacional");
  });
});
