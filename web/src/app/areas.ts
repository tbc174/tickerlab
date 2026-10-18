// As áreas do menu do app novo (ADR 0096): Início, Ativo, Estratégias, Acompanhar, Conta e Ajuda. Vêm de
// src/paginas.py (AREAS e paginas_da_area) pelo app.json: o TypeScript não repete a ordem nem o mapa.
import { type AreaDoApp, type PaginaDoApp, conteudoDoApp, paginasDoApp } from "../conteudo";
import { temTelaPronta } from "./rotas";

export const AREAS: AreaDoApp[] = conteudoDoApp.areas;
/** As áreas com seção no menu lateral e aba no celular. O Início é um link só; a Conta fica no menu da
 * pessoa, no topo; a Ajuda ainda não tem tela no app novo. */
export const AREAS_DO_MENU = ["ativo", "estrategias", "acompanhar"];

export interface ItemDoMenu {
  pagina: PaginaDoApp;
  pronta: boolean; // já tem tela em React; as outras aparecem "em breve", sem link
}

const PAGINA_DA_CHAVE = new Map(paginasDoApp.map((p) => [p.chave, p]));

/** As telas de uma área, na ordem do menu, sem as que não vão ao menu (Termos e Privacidade). */
export function itensDaArea(area: string): ItemDoMenu[] {
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

/** A tela que a aba de uma área abre no celular: a primeira pronta dela. */
export function primeiraPronta(area: string): PaginaDoApp | undefined {
  return itensDaArea(area).find((item) => item.pronta)?.pagina;
}
