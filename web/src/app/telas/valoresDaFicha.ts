// Os textos de um campo da ficha (linha 798): o nome na tela, a situação cadastral, a data e o CNPJ com
// pontuação. Fica à parte da tela para o Resumo e as abas usarem sem importar uma da outra.
import { formatarData } from "../formatar";
import type { CampoComFonteV1 } from "../tipos";

export const SEM_VALOR = "—";

// o nome de cada campo na tela; campo novo sem nome aparece com a chave, nunca some
const NOMES_DOS_CAMPOS: Record<string, string> = {
  razao_social: "Razão social",
  situacao_cadastral: "Situação cadastral",
  data_situacao_cadastral: "Data da situação",
  motivo_situacao: "Motivo da situação (código da Receita)",
  natureza_juridica: "Natureza jurídica (código da Receita)",
  matriz: "Matriz",
  optante_simples: "Optante pelo Simples",
  data_opcao_simples: "Entrou no Simples em",
  data_exclusao_simples: "Saiu do Simples em",
  mes_do_retrato: "Mês do cadastro",
  mes_do_retrato_do_cadastro: "Mês do retrato do cadastro",
  documento: "Documento",
  referencia: "Referência",
  prazo: "Prazo",
  primeira_entrega: "Primeira entrega",
  dias_uteis_de_atraso: "Dias úteis de atraso",
  situacao_da_entrega: "Situação da entrega",
};

// os cinco códigos do dicionário de dados do CNPJ (base/receita_codigos.py)
const SITUACOES_CADASTRAIS: Record<string, string> = {
  "01": "Nula",
  "02": "Ativa",
  "03": "Suspensa",
  "04": "Inapta",
  "08": "Baixada",
};

// a regra do TickerLab sobre o índice da CVM (src/api_externa/conjuntos/ficha.py)
const SITUACOES_DA_ENTREGA: Record<string, string> = {
  on_time: "No prazo",
  late: "Atrasou",
  gray_zone: "Atraso curto (um feriado local pode explicar)",
  severely_late: "Atraso grave",
  not_filed: "Não entregue",
};

const DATA_ISO = /^\d{4}-\d{2}-\d{2}$/;
const MES_ISO = /^(\d{4})-(\d{2})$/;
const CNPJ_SO_DIGITOS = /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/;

/** "02429144000193" → "02.429.144/0001-93", como o analista digita; outro formato sai como veio. */
export const cnpjComPontuacao = (cnpj: string) => cnpj.replace(CNPJ_SO_DIGITOS, "$1.$2.$3/$4-$5");

export const nomeDoCampo = (chave: string) => NOMES_DOS_CAMPOS[chave] ?? chave;

export function textoDoValor(chave: string, valor: CampoComFonteV1["valor"]): string {
  if (valor === null) return SEM_VALOR;
  if (typeof valor === "boolean") return valor ? "Sim" : "Não";
  const texto = String(valor);
  if (chave === "situacao_cadastral") return SITUACOES_CADASTRAIS[texto.padStart(2, "0")] ?? `código ${texto}`;
  if (chave === "situacao_da_entrega") return SITUACOES_DA_ENTREGA[texto] ?? texto;
  if (DATA_ISO.test(texto)) return formatarData(texto);
  return texto.replace(MES_ISO, "$2/$1"); // "2026-09" → "09/2026" (o mês do cadastro)
}
