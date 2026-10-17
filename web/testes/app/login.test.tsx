// @vitest-environment jsdom
// O login com o Google no app novo: o token fica só na memória e vai só para a API.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { conteudoDoApp } from "../../src/conteudo";
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

  it("primeiro login: cria a conta pela API e entra (sem passar pelo app atual)", async () => {
    let criada = false;
    const aberto = abrirApp("/", {
      entraSozinho: false,
      eu: () =>
        criada
          ? respostaJson(200, ANA)
          : respostaJson(401, { detail: "Conta não encontrada." }, { "X-TickerLab-Motivo": "conta-nova" }),
      rotas: (endereco) => {
        if (endereco !== "/api/v1/conta") return undefined;
        criada = true;
        return respostaJson(200, { ...ANA, primeira_vez: true });
      },
    });
    google = aberto.google;
    await entrar();
    expect(await screen.findByText(/Ana · Gratuito/)).toBeTruthy();
    expect(aberto.buscar).toHaveBeenCalledWith("/api/v1/conta", {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: "{}",
    });
  });

  it("se não der para criar a conta, explica e deixa tentar de novo", async () => {
    const aberto = abrirApp("/", {
      entraSozinho: false,
      eu: () => respostaJson(401, { detail: "Conta não encontrada." }, { "X-TickerLab-Motivo": "conta-nova" }),
      rotas: (endereco) =>
        endereco === "/api/v1/conta" ? respostaJson(503, { detail: "Fora do ar." }) : undefined,
    });
    google = aberto.google;
    await entrar();
    expect(await screen.findByText(/Fora do ar/)).toBeTruthy();
    expect(screen.getByText(/Entre com o Google/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Criar a conta no app/ })).toBeNull();
  });

  it("a tela de entrada diz o que a conta guarda", async () => {
    abrir(() => respostaJson(200, ANA));
    await googlePronto();
    expect(screen.getByText(/Usamos só o seu nome, e-mail e foto para criar a sua conta/)).toBeTruthy();
  });

  it("termos novos: aceita aqui mesmo e entra", async () => {
    let aceitou = false;
    const aberto = abrirApp("/", {
      entraSozinho: false,
      eu: () =>
        aceitou
          ? respostaJson(200, ANA)
          : respostaJson(403, { detail: "Aceite os termos." }, { "X-TickerLab-Motivo": "termos" }),
      rotas: (endereco) => {
        if (endereco !== "/api/v1/aceite-dos-termos") return undefined;
        aceitou = true;
        return respostaJson(200, ANA);
      },
    });
    google = aberto.google;
    await entrar();
    expect(await screen.findByRole("heading", { name: "Antes de começar" })).toBeTruthy();
    expect(screen.getByText(/nada aqui é recomendação de investimento/)).toBeTruthy();
    // o texto inteiro, para abrir e ler na página do site (noutra aba)
    expect(screen.getByRole("link", { name: "Termos de uso" }).getAttribute("href")).toBe(
      "https://tickerlab.com.br/termos.html",
    );
    expect(screen.getByRole("link", { name: "Política de privacidade" }).getAttribute("href")).toBe(
      "https://tickerlab.com.br/privacidade.html",
    );
    const continuar = screen.getByRole("button", { name: "Continuar" }) as HTMLButtonElement;
    expect(continuar.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Li e aceito os Termos de uso/));
    expect(continuar.disabled).toBe(false);
    fireEvent.click(continuar);
    expect(await screen.findByText(/Ana · Gratuito/)).toBeTruthy();
    const aceite = aberto.buscar.mock.calls.find(([e]) => e === "/api/v1/aceite-dos-termos");
    expect(JSON.parse(String(aceite?.[1]?.body))).toEqual({
      versao: conteudoDoApp.aceite.versao,
      novidades: false, // a caixa das Novidades começa desmarcada e não é condição para entrar
      versao_das_novidades: conteudoDoApp.aceite.novidades.versao,
    });
  });

  it("as Novidades por e-mail só com a caixa opcional marcada", async () => {
    const aberto = abrirApp("/", {
      entraSozinho: false,
      eu: () => respostaJson(403, { detail: "Aceite os termos." }, { "X-TickerLab-Motivo": "termos" }),
      rotas: (endereco) => (endereco === "/api/v1/aceite-dos-termos" ? respostaJson(200, ANA) : undefined),
    });
    google = aberto.google;
    await entrar();
    const novidades = (await screen.findByLabelText(/Opcional: Quero receber por e-mail/)) as HTMLInputElement;
    expect(novidades.checked).toBe(false);
    fireEvent.click(novidades);
    fireEvent.click(screen.getByLabelText(/Li e aceito os Termos de uso/));
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    await screen.findByText(/Ana · Gratuito/);
    const aceite = aberto.buscar.mock.calls.find(([e]) => e === "/api/v1/aceite-dos-termos");
    expect(JSON.parse(String(aceite?.[1]?.body))).toMatchObject({ novidades: true });
  });

  it("termos novos sem aceite: ainda baixa os dados e acha onde apagar a conta (LGPD)", async () => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:dados"), revokeObjectURL: vi.fn() }));
    const aberto = abrirApp("/", {
      entraSozinho: false,
      eu: () => respostaJson(403, { detail: "Aceite os termos." }, { "X-TickerLab-Motivo": "termos" }),
      rotas: (endereco) =>
        endereco === "/api/v1/meus-dados" ? respostaJson(200, { perfil: { email: "ana@exemplo.com" } }) : undefined,
    });
    google = aberto.google;
    await entrar();
    expect(await screen.findByText(conteudoDoApp.aceite.sem_o_aceite.titulo)).toBeTruthy();
    expect(screen.getByText(conteudoDoApp.aceite.sem_o_aceite.explicacao)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Baixar meus dados (JSON)" }));
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    expect(aberto.buscar).toHaveBeenCalledWith("/api/v1/meus-dados", {
      method: "GET",
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
    const apagar = screen.getByRole("link", { name: /Apagar a conta/ });
    expect(apagar.getAttribute("href")).toBe("https://app.tickerlab.com.br/meus-dados");
  });

  it("termos que mudaram com a página aberta: explica e não entra", async () => {
    const aberto = abrirApp("/", {
      entraSozinho: false,
      eu: () => respostaJson(403, { detail: "Aceite os termos." }, { "X-TickerLab-Motivo": "termos" }),
      rotas: (endereco) =>
        endereco === "/api/v1/aceite-dos-termos"
          ? respostaJson(409, { detail: "Os termos mudaram enquanto a página estava aberta." })
          : undefined,
    });
    google = aberto.google;
    await entrar();
    fireEvent.click(await screen.findByLabelText(/Li e aceito os Termos de uso/));
    fireEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByText(/Os termos mudaram enquanto a página estava aberta/)).toBeTruthy();
    expect(screen.queryByText(/Ana · Gratuito/)).toBeNull();
  });

  it("na tela de aceite dá para sair", async () => {
    abrir(() => respostaJson(403, { detail: "Aceite os termos." }, { "X-TickerLab-Motivo": "termos" }));
    await entrar();
    fireEvent.click(await screen.findByRole("button", { name: "Sair" }));
    expect(await screen.findByText(/Entre com o Google/)).toBeTruthy();
  });
});
