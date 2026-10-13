// O cliente da API de leitura (v1): monta o endereço, manda o token só para /api/v1 e transforma
// cada erro num tipo que a tela sabe mostrar (entrar de novo, entrar pelo app, aceitar os termos...).
import { PREFIXO_DA_API } from "./configuracao";

export type TipoDeErro =
  | "sessao-vencida" // 401: sem token ou token vencido/inválido → entrar de novo
  | "conta-nova" // 401: a conta nunca entrou pelo app → criar a conta no app atual
  | "termos" // 403: termos novos → aceitar no app atual
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

// só caminhos da v1, sem "..": o token nunca vai para outro endereço
const ROTA_DA_V1 = /^\/v1\/[a-z0-9-]+$/;
const CAMPOS_FORA_DOS_LIMITES = "Algum campo está fora dos limites. Confira os valores e tente de novo.";
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
  if (status === 403) return "termos";
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

/** GET (ou POST, com `corpo`) numa rota da v1 (`/v1/visao-geral`), com o token do Google. */
export async function pedir<T>(
  rota: string,
  token: string,
  parametros: Parametros = {},
  corpo?: unknown,
): Promise<T> {
  if (!ROTA_DA_V1.test(rota)) throw new Error(`rota fora da API v1: ${rota}`);
  const cabecalhos: Record<string, string> = { Authorization: `Bearer ${token}` };
  const pedido: RequestInit =
    corpo === undefined
      ? { method: "GET", headers: cabecalhos }
      : {
          method: "POST",
          headers: { ...cabecalhos, "Content-Type": "application/json" },
          body: JSON.stringify(corpo),
        };
  let resposta: Response;
  try {
    resposta = await fetch(`${PREFIXO_DA_API}${rota.slice("/v1".length)}${consulta(parametros)}`, pedido);
  } catch {
    throw new ErroDaApi("rede", SEM_CONEXAO);
  }
  if (!resposta.ok) throw await erroDaResposta(resposta);
  return (await resposta.json()) as T;
}
