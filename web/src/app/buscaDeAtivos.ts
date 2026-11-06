// A busca do campo Ativo: o catálogo de src/catalogo.py (exportado em web/conteudo/ativos.json, o mesmo
// do Streamlit), filtrado pelo código ou pelo nome enquanto a pessoa digita. O JSON tem ~300 KB, então
// vem num pedaço à parte do pacote, pedido só quando o campo aparece.
//
// Regra SEARCH-03 (docstring de src/catalogo.py): nunca trocar o ativo em silêncio. O que é escolhido na
// lista vale como está; o que é digitado só vira um ativo do catálogo quando bate exatamente com um código
// (ou símbolo) dele. O resto vai como foi digitado, e a API arruma (normalizar_ticker) ou avisa.

/** Uma linha do catálogo; o rótulo vem pronto do Python ("PETR4 · Petroleo Brasileiro... · B3 · Ação"). */
export interface Ativo {
  simbolo: string; // o do Yahoo, que a API recebe (PETR4.SA, ^BVSP)
  codigo: string; // o que a pessoa conhece (PETR4, IBOV)
  nome: string;
  tipo: string; // Ação, Unit, Índice, BDR, ETF, Fundo (FII e outros)...
  rotulo: string;
}

const LIMITE_DE_SUGESTOES = 8;
// quanto menor, mais acima na lista: código exato, começo do código, palavra inteira do nome ("itau" no
// Itau Unibanco), começo de uma palavra (na Itausa), pedaço do código e, por último, pedaço do nome
const CODIGO_EXATO = 0;
const COMECO_DO_CODIGO = 1;
const PALAVRA_INTEIRA = 2;
const COMECO_DE_PALAVRA = 3;
const PEDACO_DO_CODIGO = 4;
const PEDACO_DO_NOME = 5;
// dentro de cada faixa (código, palavra do nome, pedaço), o que se negocia como empresa vem antes: "itau"
// mostra o Itaú Unibanco e a Itaúsa antes das dezenas de fundos "Itaú ..." (o catálogo não está em ordem
// de importância)
// o último nível de cada faixa; o código exato é uma faixa só dele (sempre o primeiro, seja do tipo que for)
const FAIXAS = [CODIGO_EXATO, COMECO_DO_CODIGO, COMECO_DE_PALAVRA, PEDACO_DO_NOME];
const TIPOS_DEPOIS = new Set(["Fundo (FII e outros)", "BDR", "ETF"]);
const faixa = (nota: number) => FAIXAS.findIndex((limite) => nota <= limite);

let pedido: Promise<Ativo[]> | null = null;

/** O catálogo, pedido uma vez só por página. */
export function carregarAtivos(): Promise<Ativo[]> {
  pedido ??= import("../../conteudo/ativos.json").then((m) => m.default as Ativo[]);
  return pedido;
}

/** "Petrorecôncavo" → "petroreconcavo": a busca não liga para maiúsculas nem acentos. */
export const semAcento = (texto: string) =>
  texto.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();

function relevancia(ativo: Ativo, busca: string): number | null {
  const codigos = [ativo.codigo, ativo.simbolo].map(semAcento);
  const nome = semAcento(ativo.nome);
  if (codigos.includes(busca)) return CODIGO_EXATO;
  if (codigos.some((c) => c.startsWith(busca))) return COMECO_DO_CODIGO;
  if (` ${nome} `.includes(` ${busca} `)) return PALAVRA_INTEIRA;
  if (nome.startsWith(busca) || nome.includes(` ${busca}`)) return COMECO_DE_PALAVRA;
  if (codigos.some((c) => c.includes(busca))) return PEDACO_DO_CODIGO;
  return nome.includes(busca) ? PEDACO_DO_NOME : null;
}

/** As sugestões para o que foi digitado, as mais parecidas primeiro (empate: a ordem do catálogo). */
export function sugestoes(ativos: Ativo[], texto: string, limite = LIMITE_DE_SUGESTOES): Ativo[] {
  const busca = semAcento(texto);
  if (busca === "") return [];
  return ativos
    .map((ativo, posicao) => ({ ativo, posicao, nota: relevancia(ativo, busca) }))
    .filter((s): s is { ativo: Ativo; posicao: number; nota: number } => s.nota !== null)
    .map((s) => ({ ...s, faixa: faixa(s.nota), depois: TIPOS_DEPOIS.has(s.ativo.tipo) ? 1 : 0 }))
    .sort((a, b) => a.faixa - b.faixa || a.depois - b.depois || a.nota - b.nota || a.posicao - b.posicao)
    .slice(0, limite)
    .map((s) => s.ativo);
}

/** O ativo do catálogo cujo código ou símbolo é exatamente o texto (sem ligar para maiúsculas). */
export function ativoExato(ativos: Ativo[], texto: string): Ativo | undefined {
  const alvo = texto.trim().toUpperCase();
  if (alvo === "") return undefined;
  return ativos.find((a) => a.codigo.toUpperCase() === alvo || a.simbolo.toUpperCase() === alvo);
}

/** O que vai para a API: o símbolo do catálogo quando o código bate exatamente; senão, o texto em maiúsculas. */
export const resolverAtivo = (ativos: Ativo[], texto: string): string =>
  ativoExato(ativos, texto)?.simbolo ?? texto.trim().toUpperCase();
