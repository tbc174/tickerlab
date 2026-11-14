// @vitest-environment jsdom
// Conectar (linha 832): o endereço, os passos e os comandos vêm da API; a chave é só o exemplo.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConectarV1 } from "../../src/app/tipos";
import { abrirApp, respostaJson } from "./ajudantes";

const DADOS: ConectarV1 = {
  endereco_do_conector: "https://exemplo.test/mcp",
  chave_de_exemplo: "tld_...",
  passos_no_claude: ["Passo Claude 1.", "Passo Claude 2."],
  passos_no_chatgpt: ["Passo ChatGPT 1."],
  cuidado_com_a_chave: "Cuidado com a chave.",
  comandos_da_cli: [{ titulo: "Entrar", comando: "tickerlab login" }],
  perguntas_prontas: ["Pergunta pronta 1."],
  limites: ["Limite 1."],
};
const ENDERECO = "/api/v1/conectar";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("conectar", () => {
  it("mostra endereço, passos, comandos, perguntas e limites vindos da API", async () => {
    abrirApp("/conectar", { rotas: (e) => (e === ENDERECO ? respostaJson(200, DADOS) : undefined) });
    const ligar = await screen.findByRole("region", { name: "Ligar a sua IA" }, { timeout: 5000 });
    expect(within(ligar).getByText("https://exemplo.test/mcp")).toBeTruthy();
    expect(within(ligar).getByText("Passo Claude 2.")).toBeTruthy();
    expect(within(ligar).getByText("Passo ChatGPT 1.")).toBeTruthy();
    expect(within(ligar).getByText("tld_...")).toBeTruthy();
    const cli = screen.getByRole("region", { name: "Usar a CLI" });
    expect(within(cli).getByText("tickerlab login")).toBeTruthy();
    expect(screen.getByText("Pergunta pronta 1.")).toBeTruthy();
    expect(screen.getByText("Limite 1.")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull(); // a tela não pede chave
  });

  it("copiar põe o texto na área de transferência", async () => {
    const escrever = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: escrever } });
    abrirApp("/conectar", { rotas: (e) => (e === ENDERECO ? respostaJson(200, DADOS) : undefined) });
    fireEvent.click(await screen.findByRole("button", { name: "Copiar: endereço do conector" }, { timeout: 5000 }));
    expect(escrever).toHaveBeenCalledWith("https://exemplo.test/mcp");
    expect(await screen.findByText(/Copiado/)).toBeTruthy();
  });

  it("a API fora do ar mostra o erro da tela", async () => {
    abrirApp("/conectar", { rotas: (e) => (e === ENDERECO ? respostaJson(500, { detail: "falhou" }) : undefined) });
    expect(await screen.findByRole("alert", {}, { timeout: 5000 })).toBeTruthy();
  });
});
