// @vitest-environment jsdom
// O login com o Google no app novo: o token fica só na memória e vai só para a API.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ANA, TOKEN, abrirApp, respostaJson } from "./ajudantes";

function abrir(eu: () => Response) {
  const aberto = abrirApp("/", { eu, entraSozinho: false });
  google = aberto.google;
  return aberto.buscar;
}

let google: ReturnType<typeof abrirApp>["google"];

// como na vida real, o token só chega depois de o Google ser inicializado (o botão vem depois)
async function googlePronto() {
  await screen.findByText(/Entre com o Google/);
  await waitFor(() => expect(google.id.initialize).toHaveBeenCalled());
}

async function entrar() {
  await googlePronto();
  google.entregarToken();
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("login", () => {
  it("sem login, pede para entrar e não chama a API com token", async () => {
    const buscar = abrir(() => respostaJson(200, ANA));
    await googlePronto();
    expect(google.id.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ client_id: "id-de-teste" }),
    );
    expect(buscar).toHaveBeenCalledTimes(1); // só a configuração
  });

  it("com o token do Google, busca a conta e mostra o nome e o plano", async () => {
    const buscar = abrir(() => respostaJson(200, ANA));
    await entrar();
    expect(await screen.findByText(/Ana · Gratuito/)).toBeTruthy();
    expect(buscar).toHaveBeenCalledWith("/api/v1/eu", {
      method: "GET",
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
  });

  it("o token não fica guardado no navegador", async () => {
    abrir(() => respostaJson(200, ANA));
    await entrar();
    await screen.findByText(/Ana · Gratuito/);
    const guardado = [
      ...Object.values({ ...localStorage }),
      ...Object.values({ ...sessionStorage }),
      document.cookie,
    ].join(" ");
    expect(guardado).not.toContain(TOKEN);
  });

  it("sair esquece o token e desliga a entrada automática", async () => {
    abrir(() => respostaJson(200, ANA));
    await entrar();
    fireEvent.click(await screen.findByRole("button", { name: "Sair" }));
    expect(await screen.findByText(/Entre com o Google/)).toBeTruthy();
    expect(google.id.disableAutoSelect).toHaveBeenCalled();
  });
});

describe("conta recusada pela API", () => {
  it("token vencido: pede para entrar de novo", async () => {
    abrir(() =>
      respostaJson(401, { detail: "Token vencido." }, { "X-TickerLab-Motivo": "token-invalido" }),
    );
    await entrar();
    expect(await screen.findByText(/Sua sessão terminou/)).toBeTruthy();
    expect(screen.getByText(/Entre com o Google/)).toBeTruthy();
  });

  it("conta que nunca entrou pelo app: leva ao app atual para criar a conta", async () => {
    abrir(() =>
      respostaJson(401, { detail: "Conta não encontrada." }, { "X-TickerLab-Motivo": "conta-nova" }),
    );
    await entrar();
    const link = await screen.findByRole("link", { name: /Criar a conta no app/ });
    expect(link.getAttribute("href")).toBe("https://app.tickerlab.com.br/");
  });

  it("termos novos: leva ao app atual para aceitar", async () => {
    abrir(() => respostaJson(403, { detail: "Aceite os termos." }, { "X-TickerLab-Motivo": "termos" }));
    await entrar();
    expect(await screen.findByRole("link", { name: /Aceitar os termos no app/ })).toBeTruthy();
  });
});
