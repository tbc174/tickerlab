// @vitest-environment jsdom
// A ficha "Foi sorte?" embaixo do backtest no app novo, com a resposta de exemplo do Python: o veredito,
// as cinco checagens, as tentativas e a nota têm de sair com os mesmos textos da tela do Streamlit
// (exemplos/ficha.json, gravado por tests/test_app_novo_mesmos_numeros.py).
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { abrirApp, respostaJson } from "./ajudantes";
import exemplo from "./exemplos/ficha.json";

function abrir(resposta: unknown = exemplo.resposta) {
  return abrirApp("/backtest", {
    rotas: (endereco) => (endereco === "/api/v1/backtest" ? respostaJson(200, resposta) : undefined),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ficha Foi sorte?", () => {
  it("o veredito e as cinco checagens com os textos do Streamlit", async () => {
    abrir();
    const ficha = await screen.findByRole("region", { name: "Foi sorte?" });
    const { na_tela } = exemplo;
    expect(within(ficha).getByRole("heading", { name: na_tela.titulo })).toBeTruthy();
    expect(within(ficha).getByText(na_tela.texto)).toBeTruthy();
    const itens = within(ficha).getAllByRole("listitem");
    expect(itens).toHaveLength(5);
    na_tela.checagens.forEach((checagem, i) => {
      const item = within(itens[i]);
      expect(item.getByText(checagem.pergunta)).toBeTruthy();
      expect(item.getByText(`(${checagem.situacao})`)).toBeTruthy();
      expect(item.getByText(checagem.explicacao)).toBeTruthy();
    });
    expect(within(ficha).getByText(na_tela.texto_das_tentativas)).toBeTruthy();
    expect(within(ficha).getByText(na_tela.nota)).toBeTruthy();
  });

  it("explica a ficha e tem o ? do glossário", async () => {
    abrir();
    const ficha = await screen.findByRole("region", { name: "Foi sorte?" });
    expect(within(ficha).getByText(/A ficha confere, em cinco perguntas/)).toBeTruthy();
    expect(within(ficha).getByLabelText("O que significa Foi sorte?")).toBeTruthy();
  });

  it("sem a ficha, mostra o motivo e o backtest continua", async () => {
    abrir({ ...exemplo.resposta, ficha: null, motivo_sem_ficha: "Não deu para contar as suas tentativas agora." });
    await screen.findByRole("region", { name: "Resultado do backtest" });
    const ficha = screen.getByRole("region", { name: "Foi sorte?" });
    expect(within(ficha).getByText("Não deu para contar as suas tentativas agora.")).toBeTruthy();
    expect(within(ficha).queryAllByRole("listitem")).toHaveLength(0);
  });

  it("o veredito não usa verde nem vermelho: o ícone e o texto dizem o resultado", async () => {
    abrir();
    const ficha = await screen.findByRole("region", { name: "Foi sorte?" });
    expect(ficha.innerHTML).not.toMatch(/--(alta|queda|verde|vermelho)/);
  });
});
