// O botão "Entrar com o Google" (Google Identity Services). O script do Google só é carregado no
// app novo, quando a API está ligada; ele devolve o ID token, que a API confere (src/api_v1/acesso.py).

export interface RespostaDoGoogle {
  credential: string; // o ID token (JWT assinado pelo Google)
}

export interface GoogleId {
  initialize(opcoes: {
    client_id: string;
    callback: (resposta: RespostaDoGoogle) => void;
    auto_select: boolean;
    use_fedcm_for_prompt: boolean;
  }): void;
  renderButton(onde: HTMLElement, opcoes: Record<string, string | number>): void;
  prompt(): void;
  disableAutoSelect(): void;
}

const SCRIPT_DO_GOOGLE = "https://accounts.google.com/gsi/client";

function jaCarregado(): GoogleId | null {
  const google = (globalThis as { google?: { accounts?: { id?: GoogleId } } }).google;
  return google?.accounts?.id ?? null;
}

let carregando: Promise<GoogleId> | null = null;

/** O `google.accounts.id`, carregando o script do Google uma vez só. */
export function carregarGoogle(): Promise<GoogleId> {
  const pronto = jaCarregado();
  if (pronto) return Promise.resolve(pronto);
  carregando ??= new Promise((resolver, recusar) => {
    const script = document.createElement("script");
    script.src = SCRIPT_DO_GOOGLE;
    script.async = true;
    script.onload = () => {
      const google = jaCarregado();
      if (google) resolver(google);
      else recusar(new Error("o script do Google não trouxe o login"));
    };
    script.onerror = () => {
      carregando = null;
      recusar(new Error("não deu para carregar o login do Google"));
    };
    document.head.append(script);
  });
  return carregando;
}
