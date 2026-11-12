// @vitest-environment jsdom
// O estado da navegação vale uma vez (linha 822, P2 do #999): a tela lê o que veio e o apaga da entrada do
// histórico, para um "Sair" e outra conta na mesma aba não abrirem de novo a ficha da conta anterior.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { useEstadoDaNavegacaoUmaVez } from "../../src/app/estadoDaNavegacao";

afterEach(cleanup);

function Sonda() {
  const lido = useEstadoDaNavegacaoUmaVez() as { cnpj?: string } | null;
  const noHistorico = useLocation().state as unknown;
  return (
    <>
      <p data-testid="lido">{lido?.cnpj ?? "nada"}</p>
      <p data-testid="historico">{noHistorico === null ? "limpo" : "com estado"}</p>
    </>
  );
}

describe("estado da navegação uma vez só", () => {
  it("a tela lê o que veio e a entrada do histórico fica sem estado", async () => {
    render(
      <MemoryRouter initialEntries={[{ pathname: "/ficha-da-empresa", state: { cnpj: "11111111000191" } }]}>
        <Sonda />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("lido").textContent).toBe("11111111000191");
    await waitFor(() => expect(screen.getByTestId("historico").textContent).toBe("limpo"));
    expect(screen.getByTestId("lido").textContent).toBe("11111111000191"); // a tela não perde o que já leu
  });

  it("sem estado, não muda nada", () => {
    render(
      <MemoryRouter initialEntries={["/ficha-da-empresa"]}>
        <Sonda />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("lido").textContent).toBe("nada");
    expect(screen.getByTestId("historico").textContent).toBe("limpo");
  });
});
