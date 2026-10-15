// @vitest-environment jsdom
// A simulação no endereço: só as chaves conhecidas, só números onde o exemplo é número e só as
// opções da lista onde é escolha; o resto cai no exemplo. Mudar um campo troca o endereço sem
// criar uma entrada no "voltar". E os botões de copiar.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Compartilhar } from "../../src/ferramentas/Compartilhar";
import { lerDoEndereco, useCamposNoEndereco } from "../../src/ferramentas/endereco";

const EXEMPLO = { capital: "10.000", taxa: "10", tipo: "composto" };
const OPCOES = { tipo: ["composto", "simples"] } as const;

beforeEach(() => {
  window.history.replaceState(null, "", "/calculadora.html");
});
afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("ler a simulação do endereço", () => {
  it("aceita números e opções da lista; ignora chave desconhecida e lixo", () => {
    expect(lerDoEndereco("?capital=5000&taxa=abc&x=1&tipo=simples", EXEMPLO, OPCOES)).toEqual({
      capital: "5000",
      taxa: "10",
      tipo: "simples",
    });
  });

  it("texto que não é número nem opção não entra (nada vira HTML)", () => {
    const lido = lerDoEndereco("?taxa=%3Cscript%3Ealert(1)%3C%2Fscript%3E&tipo=hack", EXEMPLO, OPCOES);
    expect(lido).toEqual(EXEMPLO);
  });

  it("aceita o número como as pessoas escrevem (1.000,50) e recusa texto comprido", () => {
    expect(lerDoEndereco("?capital=1.000%2C50", EXEMPLO, OPCOES).capital).toBe("1.000,50");
    expect(lerDoEndereco(`?capital=${"9".repeat(40)}`, EXEMPLO, OPCOES).capital).toBe("10.000");
  });

  it("campo de exemplo vazio é de número: aceita número e recusa texto", () => {
    const exemplo = { q5: "", t5: "compra" };
    expect(lerDoEndereco("?q5=40", exemplo)).toEqual({ q5: "40", t5: "compra" });
    expect(lerDoEndereco("?q5=abc", exemplo)).toEqual(exemplo);
  });

  it("campo de número que a pessoa apagou volta vazio, não com o exemplo", () => {
    expect(lerDoEndereco("?capital=&tipo=simples", EXEMPLO, OPCOES).capital).toBe("");
    expect(lerDoEndereco("?tipo=", EXEMPLO, OPCOES).tipo).toBe("composto"); // escolha vazia não vale
  });

  it("com prefixo, duas ferramentas na mesma página não se misturam", () => {
    expect(lerDoEndereco("?a.taxa=5&taxa=7", { taxa: "1" }, {}, "a.")).toEqual({ taxa: "5" });
  });
});

function Ferramenta() {
  const [campos, mudar] = useCamposNoEndereco(EXEMPLO, OPCOES);
  return (
    <label>
      Capital
      <input value={campos.capital} onChange={(e) => mudar("capital")(e.target.value)} />
    </label>
  );
}

describe("o gancho da simulação no endereço", () => {
  it("abre com o que está no endereço", async () => {
    window.history.replaceState(null, "", "/calculadora.html?capital=5000");
    await act(async () => {
      render(<Ferramenta />);
    });
    expect((screen.getByLabelText("Capital") as HTMLInputElement).value).toBe("5000");
  });

  it("mudar um campo troca o endereço sem criar entrada no voltar", async () => {
    const empurrar = vi.spyOn(window.history, "pushState");
    await act(async () => {
      render(<Ferramenta />);
    });
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Capital"), { target: { value: "2.500" } });
    });
    expect(new URLSearchParams(window.location.search).get("capital")).toBe("2.500");
    expect(window.location.pathname).toBe("/calculadora.html");
    expect(empurrar).not.toHaveBeenCalled();
  });

  it("sem mexer em nada, o endereço continua limpo", async () => {
    await act(async () => {
      render(<Ferramenta />);
    });
    expect(window.location.search).toBe("");
  });
});

describe("copiar", () => {
  it("copiar resultado leva o texto e o link", async () => {
    const escrever = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: escrever }, configurable: true });
    window.history.replaceState(null, "", "/calculadora.html?capital=5000");
    render(<Compartilhar resultado="R$ 5.000 viram R$ 12.968,71" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copiar resultado" }));
    });
    expect(escrever).toHaveBeenCalledWith(`R$ 5.000 viram R$ 12.968,71 — ${window.location.href}`);
    expect(screen.getByRole("status").textContent).toContain("Copiado");
  });

  it("sem a área de transferência, mostra o link para copiar à mão", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    render(<Compartilhar resultado="x" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copiar link" }));
    });
    expect((screen.getByLabelText("Link desta simulação") as HTMLInputElement).value).toBe(window.location.href);
  });
});
