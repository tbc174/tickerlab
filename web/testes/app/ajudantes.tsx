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
  // o POST /v1/conta (com o token do Google): cria a conta na primeira vez e abre a sessão
  conta?: () => Response;
  // o POST /v1/entrada/confirmar (e-mail e código): se der certo, abre a sessão
  confirmar?: () => Response;
  // as outras rotas da API (as telas): endereço → resposta
  rotas?: (endereco: string, pedido?: RequestInit) => Response | undefined;
  entraSozinho?: boolean;
  // a pessoa já tem a sessão (o cookie de um login anterior): o app entra sem o Google
  comSessao?: boolean;
}

// os cabeçalhos que todo pedido do app manda (a prova de que saiu do próprio app, contra CSRF)
export const DO_APP = { "X-TickerLab-Pedido": "1" };

const SEM_SESSAO = () => respostaJson(401, { detail: "Entre para continuar." }, { "X-TickerLab-Motivo": "sem-token" });

function temAutorizacao(pedido?: RequestInit): boolean {
  return "Authorization" in ((pedido?.headers as Record<string, string> | undefined) ?? {});
}

/** Abre o app em `caminho` com a API e o Google de mentira; devolve o `fetch` espiado e o Google.
 * A API de mentira guarda a sessão como o navegador guardaria o cookie: o `POST /v1/conta` que dá
 * certo abre, o `/v1/sair` fecha, e `/v1/eu` sem sessão (nem token) responde 401. */
export function abrirApp(caminho: string, opcoes: Opcoes = {}) {
  const {
    configuracao = respostaJson(200, { google_client_id: "id-de-teste" }),
    eu = () => respostaJson(200, ANA),
    rotas = () => undefined,
    conta = () => respostaJson(200, { ...ANA, primeira_vez: false }),
    confirmar = () => respostaJson(200, { ...ANA, primeira_vez: false }),
    entraSozinho = true,
    comSessao = false,
  } = opcoes;
  let sessao = comSessao;
  const buscar = vi.fn(async (endereco: string, pedido?: RequestInit) => {
    if (endereco === "/api/v1/configuracao") return configuracao;
    if (endereco === "/api/v1/eu") return sessao || temAutorizacao(pedido) ? eu() : SEM_SESSAO();
    if (endereco === "/api/v1/sair") {
      sessao = false;
      return new Response(null, { status: 204 });
    }
    if (endereco === "/api/v1/sair-de-todos") {
      sessao = false;
      return respostaJson(200, { encerradas: 2 });
    }
    if (endereco === "/api/v1/entrada/confirmar") {
      const resposta = confirmar();
      if (resposta.ok) sessao = true;
      return resposta;
    }
    if (endereco === "/api/v1/conta") {
      const resposta = conta();
      if (resposta.ok) sessao = true;
      return resposta;
    }
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
