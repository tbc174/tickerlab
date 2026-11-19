// A busca de setor das ferramentas do analista: as atividades do CNAE (a tabela `Cnaes` da Receita, exportada
// em web/conteudo/cnaes.json por scripts/exportar_conteudo.py), achadas pelo nome ou pelo código enquanto a
// pessoa digita. O JSON tem ~150 KB, então vem num pedaço à parte do pacote, pedido só quando o campo aparece
// (como o catálogo dos ativos). Quem já sabe o código continua podendo digitá-lo: 5 ou 7 dígitos valem como
// estão, mesmo sem nome na lista.
import { semAcento } from "./buscaDeAtivos";

/** Uma subclasse do CNAE: o código de 7 dígitos (só números) e o nome como a Receita escreve. */
export interface AtividadeDoCnae {
  codigo: string;
  nome: string;
}

const LIMITE_DE_SUGESTOES = 8;
const CNAE_DIGITADO = /^(\d{5}|\d{7})$/;
const MINIMO_DE_DIGITOS = 2; // "47" já lista o comércio varejista; um dígito só lista quase tudo
// palavras que não ajudam a achar a atividade ("transporte de carga": a busca olha "transporte" e "carga")
const PALAVRAS_VAZIAS = new Set(["a", "as", "o", "os", "de", "da", "das", "do", "dos", "e", "em", "para", "com", "por"]);
// a busca compara o começo das palavras: "farmácia" acha "farmacêuticos" e "hospital" acha "hospitalar".
// A raiz é ~70% da palavra digitada (no mínimo 4 letras); palavra curta ("gás") vale inteira, como começo
const PARTE_DA_RAIZ = 0.7;
const MINIMO_DA_RAIZ = 4;
// quanto menor, mais acima: código que começa com os dígitos, nome que começa com a 1ª palavra buscada
// ("transporte de carga" põe "Transporte rodoviário de carga" antes de "Fabricação de... transporte... cargas"),
// nome com todas as palavras em qualquer lugar
const COMECO_DO_CODIGO = 0;
const COMECO_DO_NOME = 1;
const TODAS_AS_PALAVRAS = 2;
const MAIOR_POSICAO = 99; // o desempate pela posição da palavra fica dentro da faixa (nunca chega à seguinte)

let pedido: Promise<AtividadeDoCnae[]> | null = null;

/** As atividades do CNAE, pedidas uma vez só por página. */
export function carregarCnaes(): Promise<AtividadeDoCnae[]> {
  pedido ??= import("../../conteudo/cnaes.json").then((m) => m.default as AtividadeDoCnae[]);
  return pedido;
}

/** "4771701" → "4771-7/01" e "47717" → "4771-7", a escrita do IBGE; o resto volta como veio. */
export function cnaeComPontuacao(codigo: string): string {
  if (/^\d{7}$/.test(codigo)) return `${codigo.slice(0, 4)}-${codigo.slice(4, 5)}/${codigo.slice(5)}`;
  if (/^\d{5}$/.test(codigo)) return `${codigo.slice(0, 4)}-${codigo.slice(4)}`;
  return codigo;
}

/** Só os dígitos do que foi digitado ("47.71-7/01" → "4771701"), ou null se há letra no meio. */
export function digitosDoCnae(texto: string): string | null {
  const limpo = texto.trim();
  if (limpo === "" || /[^\d.\-/\s]/.test(limpo)) return null;
  return limpo.replace(/\D/g, "");
}

/** O código que o texto digitado já é (5 ou 7 dígitos, com ou sem pontuação), ou null. */
export function cnaeDigitado(texto: string): string | null {
  const digitos = digitosDoCnae(texto);
  return digitos !== null && CNAE_DIGITADO.test(digitos) ? digitos : null;
}

const raiz = (palavra: string) =>
  palavra.length <= MINIMO_DA_RAIZ ? palavra : palavra.slice(0, Math.max(MINIMO_DA_RAIZ, Math.ceil(palavra.length * PARTE_DA_RAIZ)));

const palavrasDe = (texto: string) => semAcento(texto).split(/[^a-z0-9]+/).filter((p) => p !== "");

function relevancia(atividade: AtividadeDoCnae, raizes: string[], digitos: string | null): number | null {
  if (digitos !== null) return atividade.codigo.startsWith(digitos) ? COMECO_DO_CODIGO : null;
  const palavras = palavrasDe(atividade.nome);
  const posicoes = raizes.map((r) => palavras.findIndex((p) => p.startsWith(r)));
  if (posicoes.some((i) => i < 0)) return null;
  const faixa = palavras[0]?.startsWith(raizes[0]) ? COMECO_DO_NOME : TODAS_AS_PALAVRAS;
  // dentro da faixa, sobe o nome em que as palavras buscadas aparecem mais cedo: "hospital" põe "Atividades de
  // atendimento hospitalar" antes de "Fabricação de artefatos ... para uso odonto-médico-hospitalar"
  return faixa + Math.min(Math.max(...posicoes), MAIOR_POSICAO) / (MAIOR_POSICAO + 1);
}

/** As atividades para o que foi digitado: pelo código (a partir de 2 dígitos) ou por todas as palavras do nome,
 * sem ligar para acento nem para o fim da palavra; empate fica na ordem da tabela (a do CNAE). */
export function sugestoesDeCnae(
  atividades: AtividadeDoCnae[],
  texto: string,
  limite = LIMITE_DE_SUGESTOES,
): AtividadeDoCnae[] {
  const digitos = digitosDoCnae(texto);
  if (digitos !== null && digitos.length < MINIMO_DE_DIGITOS) return [];
  const raizes = palavrasDe(texto)
    .filter((p) => !PALAVRAS_VAZIAS.has(p))
    .map(raiz);
  if (digitos === null && raizes.length === 0) return [];
  return atividades
    .map((atividade, posicao) => ({ atividade, posicao, nota: relevancia(atividade, raizes, digitos) }))
    .filter((s): s is { atividade: AtividadeDoCnae; posicao: number; nota: number } => s.nota !== null)
    .sort((a, b) => a.nota - b.nota || a.posicao - b.posicao)
    .slice(0, limite)
    .map((s) => s.atividade);
}

/** O nome da atividade de um código de 7 dígitos, ou null (código de 5 dígitos é uma classe: não tem nome na
 * tabela das subclasses). */
export const nomeDoCnae = (atividades: AtividadeDoCnae[] | null, codigo: string): string | null =>
  atividades?.find((a) => a.codigo === codigo)?.nome ?? null;

/** "Comércio varejista de produtos farmacêuticos... (CNAE 4771-7/01)", ou só "CNAE 4771-7" sem nome. */
export function rotuloDoSetor(codigo: string, nome: string | null): string {
  const cnae = `CNAE ${cnaeComPontuacao(codigo)}`;
  return nome ? `${nome.replace(/\.$/, "")} (${cnae})` : cnae;
}
