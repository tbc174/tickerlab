// O cliente da API de leitura (v1): monta o endereço, fala só com /api/v1 e transforma cada erro num
// tipo que a tela sabe mostrar (entrar de novo, entrar pelo app, aceitar os termos, conhecer os
// planos...). Depois do login, quem identifica a pessoa é o cookie da sessão (HttpOnly: o app não o
// vê; o navegador o manda sozinho). O token do Google só vai no pedido que abre a sessão.
import { PREFIXO_DA_API } from "./configuracao";

/** O "token" de quem entrou: a sessão do cookie. Com ele, o pedido não leva Authorization. */
export const SESSAO = "sessao";
// prova à API que o pedido saiu do próprio app: um site de fora não consegue pôr este cabeçalho
// (src/api_v1/sessao.py, proteção contra CSRF)
const CABECALHO_DO_APP = { "X-TickerLab-Pedido": "1" };

export type TipoDeErro =
  | "sessao-vencida" // 401: sem token ou token vencido/inválido → entrar de novo
  | "conta-nova" // 401: a conta ainda não existe → criar pela API (POST /v1/conta)
  | "termos" // 403: termos novos → aceitar na versão clássica
  | "plano" // 403: a página não abre no plano da conta → conhecer os planos (ADR 0062)
  | "nao-encontrado" // 404: ativo sem dados (ou a API desligou)
  | "pedido-invalido" // 422: campo fora dos limites ou período curto demais
  | "limite" // 429: muitos pedidos por minuto
  | "indisponivel" // 5xx: servidor, Google ou Banco Central fora do ar
  | "rede"; // nem chegou ao servidor

export class ErroDaApi extends Error {
  constructor(
    readonly tipo: TipoDeErro,
    mensagem: string,
  ) {
    super(mensagem);
    this.name = "ErroDaApi";
  }
}

export type Parametros = Record<string, string | number | string[] | undefined>;

// só caminhos da v1, sem "..": o token nunca vai para outro endereço (cada pedaço só com letras,
// números, hífen e sublinhado, como em /v1/commodities/cafe/mapa e /v1/operacoes/<id>/checklist/ma_dfs)
const ROTA_DA_V1 = /^\/v1(\/[a-z0-9_-]+)+$/;
const CAMPOS_FORA_DOS_LIMITES = "Algum campo está fora dos limites. Confira os valores e tente de novo.";
const SEM_CORPO = 204;
const SEM_CONEXAO = "Sem conexão com o TickerLab. Confira a internet e tente de novo.";

function consulta(parametros: Parametros): string {
  const busca = new URLSearchParams();
  for (const [nome, valor] of Object.entries(parametros)) {
    if (valor === undefined) continue;
    for (const item of Array.isArray(valor) ? valor : [valor]) busca.append(nome, String(item));
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

function tipoDoErro(status: number, motivo: string | null): TipoDeErro {
  if (status === 401) return motivo === "conta-nova" ? "conta-nova" : "sessao-vencida";
  if (status === 403) {
    if (motivo === "plano") return "plano";
    // a API não reconheceu o pedido como do app (não deveria acontecer): não é caso de aceitar termos
    return motivo === "pedido-de-fora" ? "indisponivel" : "termos";
  }
  if (status === 404) return "nao-encontrado";
  if (status === 422) return "pedido-invalido";
  if (status === 429) return "limite";
  return "indisponivel";
}

async function erroDaResposta(resposta: Response): Promise<ErroDaApi> {
  let detalhe: unknown = null;
  try {
    detalhe = ((await resposta.json()) as { detail?: unknown }).detail;
  } catch {
    // corpo que não é JSON (proxy, página de erro): fica a mensagem padrão
  }
  const tipo = tipoDoErro(resposta.status, resposta.headers.get("X-TickerLab-Motivo"));
  const mensagem =
    typeof detalhe === "string"
      ? detalhe
      : tipo === "pedido-invalido"
        ? CAMPOS_FORA_DOS_LIMITES
        : "O TickerLab não respondeu agora. Tente de novo em instantes.";
  return new ErroDaApi(tipo, mensagem);
}

function cabecalhosPara(token: string): Record<string, string> {
  return token === SESSAO ? { ...CABECALHO_DO_APP } : { ...CABECALHO_DO_APP, Authorization: `Bearer ${token}` };
}

/** Um arquivo de uma rota da v1 (a exportação dos dados, um PDF), com a sessão. Com `corpo`, o
 * pedido é um POST (o CNPJ de uma busca não pode ir no endereço). */
export async function baixar(
  rota: string,
  token: string,
  corpo?: unknown,
  parametros: Parametros = {},
): Promise<Blob> {
  if (!ROTA_DA_V1.test(rota)) throw new Error(`rota fora da API v1: ${rota}`);
  const pedido: RequestInit =
    corpo === undefined
      ? { method: "GET", headers: cabecalhosPara(token), credentials: "same-origin" }
      : {
          method: "POST",
          headers: { ...cabecalhosPara(token), "Content-Type": "application/json" },
          body: JSON.stringify(corpo),
          credentials: "same-origin",
        };
  let resposta: Response;
  try {
    resposta = await fetch(`${PREFIXO_DA_API}${rota.slice("/v1".length)}${consulta(parametros)}`, pedido);
  } catch {
    throw new ErroDaApi("rede", SEM_CONEXAO);
  }
  if (!resposta.ok) throw await erroDaResposta(resposta);
  return resposta.blob();
}

/** GET (ou POST, com `corpo`) numa rota da v1 (`/v1/visao-geral`), com a sessão (`SESSAO`) ou, só
 * para abrir a sessão, com o token do Google. Resposta sem corpo (204) vira `undefined`. */
export async function pedir<T>(
  rota: string,
  token: string,
  parametros: Parametros = {},
  corpo?: unknown,
): Promise<T> {
  if (!ROTA_DA_V1.test(rota)) throw new Error(`rota fora da API v1: ${rota}`);
  const cabecalhos = cabecalhosPara(token);
  const pedido: RequestInit =
    corpo === undefined
      ? { method: "GET", headers: cabecalhos, credentials: "same-origin" }
      : {
          method: "POST",
          headers: { ...cabecalhos, "Content-Type": "application/json" },
          body: JSON.stringify(corpo),
          credentials: "same-origin",
        };
  let resposta: Response;
  try {
    resposta = await fetch(`${PREFIXO_DA_API}${rota.slice("/v1".length)}${consulta(parametros)}`, pedido);
  } catch {
    throw new ErroDaApi("rede", SEM_CONEXAO);
  }
  if (!resposta.ok) throw await erroDaResposta(resposta);
  if (resposta.status === SEM_CORPO) return undefined as T;
  return (await resposta.json()) as T;
}

export type MetodoQueMuda = "POST" | "PATCH" | "DELETE";

/** POST, PATCH ou DELETE numa rota da v1, com a sessão. `corpo` vai como JSON, ou como formulário
 * (o envio de um arquivo: o navegador põe o cabeçalho do multipart). Resposta sem corpo vira `undefined`. */
export async function mudar<T>(
  metodo: MetodoQueMuda,
  rota: string,
  token: string,
  corpo?: unknown,
): Promise<T> {
  if (!ROTA_DA_V1.test(rota)) throw new Error(`rota fora da API v1: ${rota}`);
  const cabecalhos = cabecalhosPara(token);
  const pedido: RequestInit = { method: metodo, credentials: "same-origin", headers: cabecalhos };
  if (corpo instanceof FormData) {
    pedido.body = corpo;
  } else if (corpo !== undefined) {
    pedido.headers = { ...cabecalhos, "Content-Type": "application/json" };
    pedido.body = JSON.stringify(corpo);
  }
  let resposta: Response;
  try {
    resposta = await fetch(`${PREFIXO_DA_API}${rota.slice("/v1".length)}`, pedido);
  } catch {
    throw new ErroDaApi("rede", SEM_CONEXAO);
  }
  if (!resposta.ok) throw await erroDaResposta(resposta);
  if (resposta.status === SEM_CORPO) return undefined as T;
  return (await resposta.json()) as T;
}
