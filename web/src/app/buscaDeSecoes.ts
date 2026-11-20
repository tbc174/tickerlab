// O setor de "Encontrar empresas": a busca filtra pela seção do CNAE (a letra do IBGE), mas quem procura pensa na
// atividade ("farmácia", "hospital"). A caixa sugere as seções pelo nome delas e, depois, as seções das atividades
// cujo nome bate com o que foi digitado, dizendo por qual atividade a seção apareceu. Campo vazio lista todas.
import { type AtividadeDoCnae, nomeCombina, sugestoesDeCnae } from "./buscaDeCnaes";
import { secaoDoCnae } from "./secaoDoCnae";

/** Uma seção do CNAE como a busca a oferece: a letra e o nome. */
export interface SecaoDaBusca {
  codigo: string;
  nome: string;
}

/** A seção sugerida e, se ela veio de uma atividade, o nome dessa atividade. */
export interface SugestaoDeSecao {
  secao: SecaoDaBusca;
  pelaAtividade: string | null;
}

const LIMITE_DE_SUGESTOES = 8;
// as atividades olhadas para achar seções: o bastante para que uma palavra comum ("comércio") traga mais de uma
const ATIVIDADES_OLHADAS = 40;

/** As seções para o que foi digitado, sem as já escolhidas: primeiro as que têm as palavras no nome, depois as das
 * atividades que têm. Campo vazio: todas, na ordem do IBGE. */
export function sugestoesDeSecao(
  secoes: SecaoDaBusca[],
  atividades: AtividadeDoCnae[] | null,
  texto: string,
  escolhidas: string[],
): SugestaoDeSecao[] {
  const livres = secoes.filter((s) => !escolhidas.includes(s.codigo));
  if (texto.trim() === "") return livres.map((secao) => ({ secao, pelaAtividade: null }));
  const peloNome = livres.filter((s) => nomeCombina(s.nome, texto)).map((secao) => ({ secao, pelaAtividade: null }));
  const vistas = new Set(peloNome.map((s) => s.secao.codigo));
  const pelaAtividade: SugestaoDeSecao[] = [];
  for (const atividade of atividades ? sugestoesDeCnae(atividades, texto, ATIVIDADES_OLHADAS) : []) {
    const secao = livres.find((s) => s.codigo === secaoDoCnae(atividade.codigo));
    if (secao === undefined || vistas.has(secao.codigo)) continue;
    vistas.add(secao.codigo);
    pelaAtividade.push({ secao, pelaAtividade: atividade.nome });
  }
  return [...peloNome, ...pelaAtividade].slice(0, LIMITE_DE_SUGESTOES);
}
