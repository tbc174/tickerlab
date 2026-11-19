// O menu do app (linha 903): sete itens fixos, na ordem de src/paginas.py (MENU_DO_APP), que chegam pelo
// app.json. Um item junta as telas de um assunto (Empresas: encontrar, ficha e comparar) e só aparece quando
// tem uma tela que abre: "Perguntar" e "Monitorar" entram sozinhos no dia em que a tela deles ficar pronta.
// As áreas (areas.ts) continuam classificando toda tela: é delas a lista "Todas as telas".
import { type ItemDoMenuDoApp, type PaginaDoApp, conteudoDoApp, paginasDoApp } from "../conteudo";
import { temTelaPronta } from "./rotas";

const ITEM_DO_INICIO = "inicio";
/** Quantos itens do menu cabem nas abas do celular, antes do botão "Mais". */
const ITENS_NAS_ABAS = 4;

export interface ItemDoMenu extends ItemDoMenuDoApp {
  /** O endereço que o item abre: o início ou a primeira tela pronta dele. */
  destino: string;
  /** Os endereços das telas do item: em qualquer um deles o item fica marcado. */
  enderecos: string[];
}

const PAGINA_DA_CHAVE = new Map(paginasDoApp.map((p) => [p.chave, p]));

function prontasDoItem(item: ItemDoMenuDoApp): PaginaDoApp[] {
  return item.paginas.flatMap((chave) => {
    const pagina = PAGINA_DA_CHAVE.get(chave);
    return pagina && temTelaPronta(chave) ? [pagina] : [];
  });
}

function itemVisivel(item: ItemDoMenuDoApp): ItemDoMenu[] {
  if (item.chave === ITEM_DO_INICIO) return [{ ...item, destino: "/", enderecos: ["/"] }];
  const enderecos = prontasDoItem(item).map((pagina) => `/${pagina.url}`);
  return enderecos.length > 0 ? [{ ...item, destino: enderecos[0], enderecos }] : [];
}

/** Os itens que o menu mostra hoje, na ordem; o que ainda não tem tela fica de fora (linha que não abre confunde). */
export const ITENS_DO_MENU: ItemDoMenu[] = conteudoDoApp.menu.flatMap(itemVisivel);
/** Os itens com aba no celular: os primeiros do caminho principal. O resto fica atrás do botão "Mais". */
export const ITENS_COM_ABA: ItemDoMenu[] = ITENS_DO_MENU.filter((item) => !item.secundario).slice(0, ITENS_NAS_ABAS);

const semBarraNoFim = (caminho: string) => caminho.replace(/\/+$/, "") || "/";

/** O item do menu de um endereço ("/ficha-da-empresa" → "empresas"); tela fora do menu, null. */
export function itemDoEndereco(caminho: string): string | null {
  const endereco = semBarraNoFim(caminho);
  return ITENS_DO_MENU.find((item) => item.enderecos.includes(endereco))?.chave ?? null;
}

/** O item está aberto nesta tela? "page" na tela que ele abre, "true" nas outras telas dele. */
export function marcaDoItem(item: ItemDoMenu, caminho: string): "page" | "true" | undefined {
  const endereco = semBarraNoFim(caminho);
  if (!item.enderecos.includes(endereco)) return undefined;
  return endereco === item.destino ? "page" : "true";
}
