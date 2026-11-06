// @vitest-environment jsdom
// Juros e inflação e Linha do tempo no app novo, com as respostas de exemplo geradas pelo Python
// (tests/test_app_novo_mesmos_numeros.py).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LinhaDoTempoDoAtivoV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";
import juros from "./exemplos/juros_e_inflacao.json";
import linha from "./exemplos/linha_do_tempo.json";

function abrirCom(caminho: string, rota: string, resposta: () => Response) {
  return abrirApp(caminho, {
    rotas: (endereco) => (endereco.startsWith(`/api/v1/${rota}`) ? resposta() : undefined),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("juros e inflação", () => {
  const abrir = (resposta = () => respostaJson(200, juros.resposta)) =>
    abrirCom("/juros-e-inflacao", "juros-e-inflacao", resposta);

  it("mostra cada número como o Streamlit, com a referência e a fonte", async () => {
    abrir();
    const painel = await screen.findByRole("region", { name: "Juros e inflação agora" });
    for (const [nome, valor] of Object.entries(juros.na_tela)) {
      const numero = within(painel).getByText(nome, { exact: true }).closest(".numero-do-painel");
      expect(numero, nome).not.toBeNull();
      expect(within(numero as HTMLElement).getByText(valor, { exact: true }), nome).toBeTruthy();
    }
    for (const n of juros.resposta.numeros) expect(screen.getAllByText(n.legenda).length).toBeGreaterThan(0);
  });

  it("os avisos, o Focus (mediana com vírgula) e a nota de que não é previsão", async () => {
    abrir();
    expect(await screen.findByText(juros.resposta.avisos[0])).toBeTruthy();
    const tabela = screen.getByRole("table", { name: /Focus/ });
    expect(within(tabela).getByText("4,80")).toBeTruthy();
    expect(screen.getByText(/Pesquisa de 09\/10\/2026 · Banco Central, boletim Focus \(mediana\)\. É a mediana/)).toBeTruthy();
  });

  it("o gráfico mês a mês com as duas séries e a legenda", async () => {
    abrir();
    const grafico = await screen.findByRole("img", { name: /Meta da Selic e IPCA em 12 meses/ });
    expect(grafico.querySelectorAll("path.grafico-linha")).toHaveLength(2);
    expect(screen.getByRole("list", { name: "Legenda" }).textContent).toContain("IPCA em 12 meses");
  });

  it("séries ainda não coletadas: a mensagem da API", async () => {
    abrir(() => respostaJson(503, { detail: "As séries do Banco Central ainda não foram coletadas neste servidor." }));
    expect(await screen.findByText(/ainda não foram coletadas/)).toBeTruthy();
  });
});

describe("linha do tempo", () => {
  const abrir = (caminho = "/linha-do-tempo", resposta = () => respostaJson(200, linha.resposta)) =>
    abrirCom(caminho, "linha-do-tempo", resposta);

  it("pede a relevância padrão e mostra a curva com um ponto por documento", async () => {
    const { buscar } = abrir();
    const grafico = await screen.findByRole("img", { name: /^PETR4 em base 100/ });
    expect(grafico.querySelectorAll("circle.grafico-marco")).toHaveLength(linha.resposta.linha_do_tempo.marcos.length);
    expect(buscar.mock.calls.map(([e]) => String(e))).toContain(
      "/api/v1/linha-do-tempo?ticker=PETR4.SA&periodo=2y&materialidade_minima=50",
    );
  });

  it("o fato relevante mostra o assunto que o leitor achou (e só ele)", async () => {
    abrir();
    const tabela = await screen.findByRole("table", { name: "Acontecimentos do período" });
    const selos = tabela.querySelectorAll(".selo-do-assunto");
    expect([...selos].map((s) => s.textContent)).toEqual(["Aquisição"]);
    expect(selos[0].closest("tr")?.textContent).toContain("Aquisição da Refinaria Exemplo");
  });

  it("a relevância é escolhida pelo nome, como no app atual", async () => {
    const { buscar } = abrir();
    await screen.findByRole("img", { name: /em base 100/ });
    fireEvent.change(screen.getByLabelText(/Quais acontecimentos mostrar/), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    await waitFor(() =>
      expect(buscar.mock.calls.map(([e]) => String(e))).toContain(
        "/api/v1/linha-do-tempo?ticker=PETR4.SA&periodo=2y&materialidade_minima=0",
      ),
    );
  });

  it("a tabela só tem link para documento http(s); o resto fica sem link", async () => {
    const adulterada = structuredClone(linha.resposta);
    adulterada.linha_do_tempo.marcos[1].link = "javascript:alert(1)"; // como se a API falhasse
    abrir("/linha-do-tempo", () => respostaJson(200, adulterada));
    const tabela = await screen.findByRole("table", { name: "Acontecimentos do período" });
    const links = within(tabela).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["https://www.rad.cvm.gov.br/exemplo-1"]);
    expect(tabela.innerHTML).not.toContain("javascript:");
  });

  it("o aviso de causa e o texto dos documentos que ficaram de fora", async () => {
    abrir();
    expect(await screen.findByText(linha.resposta.linha_do_tempo.aviso)).toBeTruthy();
    expect(screen.getByText(linha.resposta.linha_do_tempo.texto_fora_do_grafico as string)).toBeTruthy();
  });

  it("sem acontecimentos: o texto da API no lugar da tabela", async () => {
    const vazia: LinhaDoTempoDoAtivoV1 = structuredClone(linha.resposta);
    vazia.linha_do_tempo.marcos = [];
    vazia.linha_do_tempo.sem_acontecimentos = "Nenhum acontecimento deste ativo no período.";
    abrir("/linha-do-tempo", () => respostaJson(200, vazia));
    expect(await screen.findByText("Nenhum acontecimento deste ativo no período.")).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Acontecimentos do período" })).toBeNull();
  });
});
