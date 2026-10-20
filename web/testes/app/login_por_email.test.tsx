// @vitest-environment jsdom
// Entrar com o e-mail e um código de 6 dígitos: pede o código, digita de volta e a sessão abre pelo
// cookie (o app não guarda nada). A tela não diz se o e-mail tem conta.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ANA, abrirApp, respostaJson } from "./ajudantes";

const AVISO = "Se o e-mail estiver certo, o código chega em instantes.";

function abrir(confirmar?: () => Response) {
  return abrirApp("/", {
    entraSozinho: false,
    confirmar,
    rotas: (endereco) =>
      endereco === "/api/v1/entrada/codigo" ? respostaJson(202, { mensagem: AVISO }) : undefined,
  });
}

async function pedirOCodigo() {
  fireEvent.change(await screen.findByLabelText("E-mail"), { target: { value: "ana@exemplo.com" } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar código" }));
  return screen.findByLabelText(/Código de 6 dígitos/);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("login por e-mail", () => {
  it("pede o código, confirma e entra pela sessão, sem token", async () => {
    const { buscar } = abrir();
    const campo = await pedirOCodigo();
    expect(await screen.findByText(AVISO)).toBeTruthy();
    expect(campo.getAttribute("autocomplete")).toBe("one-time-code");
    expect(campo.getAttribute("inputmode")).toBe("numeric");
    fireEvent.change(campo, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText(/Ana · Gratuito/)).toBeTruthy();
    const pedido = buscar.mock.calls.find(([e]) => e === "/api/v1/entrada/confirmar")?.[1];
    expect(JSON.parse(String(pedido?.body))).toEqual({ email: "ana@exemplo.com", codigo: "123456" });
    expect(JSON.stringify(pedido?.headers)).not.toContain("Authorization");
  });

  it("código errado mostra o motivo e deixa tentar de novo", async () => {
    abrir(() => respostaJson(401, { detail: "Código inválido ou vencido." }, { "X-TickerLab-Motivo": "codigo" }));
    const campo = await pedirOCodigo();
    fireEvent.change(campo, { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Código inválido ou vencido.");
    expect(screen.queryByText(/Ana · Gratuito/)).toBeNull();
    expect(screen.getByLabelText(/Código de 6 dígitos/)).toBeTruthy();
  });

  it("só deixa mandar de novo depois da espera", async () => {
    abrir();
    await pedirOCodigo();
    const outra = screen.getByRole("button", { name: /Mandar de novo/ }) as HTMLButtonElement;
    expect(outra.disabled).toBe(true);
    expect(outra.textContent).toContain("60 s");
  });

  it("o botão de entrar só liga com os 6 dígitos", async () => {
    abrir();
    const campo = await pedirOCodigo();
    const entrar = screen.getByRole("button", { name: "Entrar" }) as HTMLButtonElement;
    expect(entrar.disabled).toBe(true);
    fireEvent.change(campo, { target: { value: "123456" } });
    await waitFor(() => expect(entrar.disabled).toBe(false));
    expect(ANA.nome).toBe("Ana");
  });
});
