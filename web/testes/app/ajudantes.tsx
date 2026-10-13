// Ajudantes dos testes do app novo: respostas da API, um Google de mentira e abrir o app num endereço.
import { act, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { App } from "../../src/app/App";

export const TOKEN = "eyJ0b2tlbi1kby1nb29nbGUifQ.token-de-teste.assinatura";
export const ANA = {
  nome: "Ana",
  plano: "gratuito",
  administrador: false,
  limites: { simulacoes: 5, favoritos: 3, ativos_na_carteira: 4, relatorios_por_dia: 3, recursos: [] },
};

export function respostaJson(status: number, corpo: unknown, cabecalhos: Record<string, string> = {}) {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { "content-type": "application/json", ...cabecalhos },
  });
}

type Callback = (resposta: { credential: string }) => void;

/** Um `google.accounts.id` de mentira. Com `entraSozinho`, o `prompt()` entrega o token na hora
 * (como o Google faz com quem já autorizou: auto_select). */
export function googleDeMentira(entraSozinho: boolean) {
  let callback: Callback = () => {};
  const id = {
    initialize: vi.fn((opcoes: { callback: Callback }) => {
      callback = opcoes.callback;
    }),
    renderButton: vi.fn(),
    prompt: vi.fn(() => {
      if (entraSozinho) callback({ credential: TOKEN });
    }),
    disableAutoSelect: vi.fn(),
  };
  return {
    id,
    entregarToken: () => act(() => callback({ credential: TOKEN })),
  };
}

interface Opcoes {
  configuracao?: Response;
  eu?: () => Response;
  // as outras rotas da API (as telas): endereço → resposta
  rotas?: (endereco: string, pedido?: RequestInit) => Response | undefined;
  entraSozinho?: boolean;
}

/** Abre o app em `caminho` com a API e o Google de mentira; devolve o `fetch` espiado e o Google. */
export function abrirApp(caminho: string, opcoes: Opcoes = {}) {
  const {
    configuracao = respostaJson(200, { google_client_id: "id-de-teste" }),
    eu = () => respostaJson(200, ANA),
    rotas = () => undefined,
    entraSozinho = true,
  } = opcoes;
  const buscar = vi.fn(async (endereco: string, pedido?: RequestInit) => {
    if (endereco === "/api/v1/configuracao") return configuracao;
    if (endereco === "/api/v1/eu") return eu();
    return rotas(endereco, pedido) ?? respostaJson(404, { detail: "Rota sem resposta no teste." });
  });
  const google = googleDeMentira(entraSozinho);
  vi.stubGlobal("fetch", buscar);
  vi.stubGlobal("google", { accounts: { id: google.id } });
  render(
    <MemoryRouter initialEntries={[caminho]}>
      <App />
    </MemoryRouter>,
  );
  return { buscar, google };
}
