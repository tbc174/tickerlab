// O conteúdo que vem do Python (scripts/exportar_conteudo.py): o Python é a fonte da verdade.
import marcaJson from "../conteudo/marca.json";
import modulosJson from "../conteudo/modulos.json";
import paginasJson from "../conteudo/paginas.json";
import planosJson from "../conteudo/planos.json";

export interface Funcionalidade {
  nome: string;
  descricao: string;
  pagina_do_app: string | null;
  ticker: string | null;
  disponivel: boolean;
}

export interface Modulo {
  chave: string;
  nome: string;
  objetivo: string;
  frase: string;
  funcionalidades: Funcionalidade[];
}

export interface PaginaDoApp {
  chave: string;
  titulo: string;
  url: string;
  grupo: string;
  descricao: string;
  e_pro: boolean;
  no_menu: boolean;
  somente_admin: boolean;
}

export const marca = marcaJson;
export const modulos: Modulo[] = modulosJson;
export const paginasDoApp: PaginaDoApp[] = paginasJson;
export const planos = planosJson;
