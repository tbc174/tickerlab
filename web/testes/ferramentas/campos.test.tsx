// @vitest-environment jsdom
// Os campos rápidos: o deslizante e o texto andam juntos (o texto aceita valores fora da faixa do
// deslizante) e os atalhos põem um valor com um clique.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { CampoComDeslizante } from "../../src/ferramentas/campos";

afterEach(() => {
  document.body.innerHTML = "";
});

function Campo({ inicial, atalhos }: { inicial: string; atalhos?: { rotulo: string; valor: string; dica?: string }[] }) {
  const [valor, setValor] = useState(inicial);
  return (
    <CampoComDeslizante rotulo="Taxa de juros" valor={valor} aoMudar={setValor} min={0} max={30} passo={0.5} atalhos={atalhos} />
  );
}

const texto = () => screen.getByLabelText("Taxa de juros") as HTMLInputElement;
const deslizante = () => screen.getByLabelText("Taxa de juros (deslizante)") as HTMLInputElement;

describe("campo com deslizante", () => {
  it("andar o deslizante escreve o número no campo, com vírgula", async () => {
    render(<Campo inicial="10" />);
    await act(async () => {
      fireEvent.change(deslizante(), { target: { value: "12.5" } });
    });
    expect(texto().value).toBe("12,5");
  });

  it("escrever no campo move o deslizante", async () => {
    render(<Campo inicial="10" />);
    await act(async () => {
      fireEvent.change(texto(), { target: { value: "7,5" } });
    });
    expect(deslizante().value).toBe("7.5");
  });

  it("valor fora da faixa vale no texto e o deslizante fica na ponta", async () => {
    render(<Campo inicial="10" />);
    await act(async () => {
      fireEvent.change(texto(), { target: { value: "45" } });
    });
    expect(texto().value).toBe("45");
    expect(deslizante().value).toBe("30");
  });

  it("o atalho põe o valor com um clique e mostra a data na dica", async () => {
    render(<Campo inicial="10" atalhos={[{ rotulo: "Selic hoje", valor: "15", dica: "meta de 13/10/2026" }]} />);
    const atalho = screen.getByRole("button", { name: /Selic hoje/ });
    expect(atalho.getAttribute("title")).toBe("meta de 13/10/2026");
    await act(async () => {
      fireEvent.click(atalho);
    });
    expect(texto().value).toBe("15");
  });

  it("sem atalhos, nenhum botão aparece", () => {
    render(<Campo inicial="10" />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
