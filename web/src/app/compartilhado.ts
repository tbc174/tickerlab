// O link compartilhado (onda 4 da ADR 0046): lê o código depois do "#" e fala com as duas rotas
// públicas da API (src/api_v1/compartilhados.py). Sem token: quem abre não tem conta.
// O código vai no corpo de um POST, nunca no endereço (não fica em log nem em Referer).
import { PREFIXO_DA_API } from "./configuracao";

const FORMATO_DO_CODIGO = /^[A-Za-z0-9_-]{43}$/; // o mesmo de src/compartilhamentos.py
export const NAO_VALE = "Este link não existe ou não vale mais.";
const FORA_DO_AR = "Não consegui falar com o TickerLab agora. Tente de novo em instantes.";
const MUITOS_PEDIDOS = "Muitos pedidos seguidos: espere um minuto e tente de novo.";

export interface ChecagemV1 {
  pergunta: string;
  situacao: string;
  explicacao: string;
}

export interface FichaCompartilhadaV1 {
  ticker: string; // o símbolo dos dados (^BVSP)
  codigo: string; // o que a página mostra (IBOV, PETR4)
  estrategia: string;
  parametros: Record<string, number | string | boolean>;
  protecoes: Record<string, number>;
  custo_por_operacao: number;
  inicio: string;
  fim: string;
  checagens: ChecagemV1[];
  tentativas: number;
  resultado: string;
  titulo_do_veredito: string;
  texto_do_veredito: string;
  texto_das_tentativas: string;
  fonte: string;
  calculada_em: string;
}

export interface PdfCompartilhadoV1 {
  nome_do_arquivo: string;
  tamanho: number;
  sha256: string;
  gerado_em: string;
}

export interface LinkCompartilhadoV1 {
  tipo: "ficha" | "pdf";
  titulo: string;
  criado_em: string;
  expira_em: string;
  ficha: FichaCompartilhadaV1 | null;
  pdf: PdfCompartilhadoV1 | null;
  aviso: string;
}

/** O código do link, se o "#" do endereço tiver um no formato certo; senão, null. */
export function codigoDoEndereco(hash: string): string | null {
  const codigo = hash.replace(/^#/, "");
  return FORMATO_DO_CODIGO.test(codigo) ? codigo : null;
}

async function postar(rota: "abrir" | "pdf", codigo: string): Promise<Response> {
  let resposta: Response;
  try {
    resposta = await fetch(`${PREFIXO_DA_API}/compartilhados/${rota}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo }),
    });
  } catch {
    throw new Error(FORA_DO_AR);
  }
  if (resposta.ok) return resposta;
  if (resposta.status === 404) throw new Error(NAO_VALE);
  if (resposta.status === 429) throw new Error(MUITOS_PEDIDOS);
  throw new Error(FORA_DO_AR);
}

export async function abrirLink(codigo: string): Promise<LinkCompartilhadoV1> {
  return (await (await postar("abrir", codigo)).json()) as LinkCompartilhadoV1;
}

export async function baixarPdf(codigo: string): Promise<Blob> {
  return (await postar("pdf", codigo)).blob();
}
