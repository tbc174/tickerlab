// As áreas do app (ADR 0096; linha 822): Início, Empresas, Companhias abertas, Mais, Conta e Ajuda. Toda tela
// é de uma área: é dela o olho do cabeçalho e a seção na lista "Todas as telas". O menu de sete itens é outra
// coisa (menu.ts). Vêm de src/paginas.py (AREAS e paginas_da_area) pelo app.json: o TypeScript não repete a
// ordem nem o mapa.
import { type AreaDoApp, type PaginaDoApp, conteudoDoApp, paginasDoApp } from "../conteudo";
import { temTelaPronta } from "./rotas";

export const AREAS: AreaDoApp[] = conteudoDoApp.areas;

export interface ItemDaArea {
  pagina: PaginaDoApp;
  pronta: boolean; // já tem tela em React; as outras só existem na versão clássica e não vão à lista
}

const PAGINA_DA_CHAVE = new Map(paginasDoApp.map((p) => [p.chave, p]));

/** As telas de uma área, na ordem do menu, sem as que não vão ao menu (Termos e Privacidade). */
export function itensDaArea(area: string): ItemDaArea[] {
  const paginas = AREAS.find((a) => a.chave === area)?.paginas ?? [];
  return paginas.flatMap((chave) => {
    const pagina = PAGINA_DA_CHAVE.get(chave);
    return pagina?.no_menu ? [{ pagina, pronta: temTelaPronta(chave) }] : [];
  });
}

/** A área de um endereço do app ("/risco" → "ativo"); o início é a área Início; desconhecido, null. */
export function areaDoEndereco(caminho: string): string | null {
  const url = caminho.replace(/^\/+|\/+$/g, "");
  if (url === "") return "inicio";
  return paginasDoApp.find((p) => p.url === url)?.area ?? null;
}

/** As telas de uma área que já abrem no app novo: é o que a lista mostra (linha que não abre confunde). */
export function telasProntasDaArea(area: string): PaginaDoApp[] {
  return itensDaArea(area)
    .filter((item) => item.pronta)
    .map((item) => item.pagina);
}
