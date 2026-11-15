// Uma pergunta que sai de uma tela e abre o Perguntar já na caixa (linha 903, PR 2 das telas): os atalhos do
// Início e as perguntas prontas do Conectar. O texto vai pelo estado da navegação, nunca pelo endereço (um
// endereço fica no histórico e em quem recebe o link), e o Perguntar só o põe na caixa: quem envia é a pessoa.
import { paginasDoApp } from "../conteudo";

/** O que o estado da navegação leva ao Perguntar. */
export interface PerguntaDaNavegacao {
  pergunta: string;
}

/** O endereço do Perguntar (sem a barra inicial), do mapa de páginas; vazio se a página não existir. */
export const URL_DO_PERGUNTAR = paginasDoApp.find((pagina) => pagina.chave === "perguntar")?.url ?? "";

/** O estado da navegação que abre o Perguntar com `pergunta` na caixa. */
export const comAPergunta = (pergunta: string): PerguntaDaNavegacao => ({ pergunta });

/** A pergunta que veio no estado da navegação; vazio se não veio nada, ou se veio algo que não é uma pergunta
 * (o estado do histórico não tem tipo garantido). */
export function perguntaDoEstado(estado: unknown): string {
  if (typeof estado !== "object" || estado === null) return "";
  const { pergunta } = estado as Partial<PerguntaDaNavegacao>;
  return typeof pergunta === "string" ? pergunta.trim() : "";
}
