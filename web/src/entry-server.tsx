// Monta o HTML pronto de cada página no build (sem navegador): é o que a busca do Google lê. O site
// é estático: nada de React no navegador; o site.js cuida do tema, da busca e da vitrine.
import { renderToStaticMarkup } from "react-dom/server";
import { css } from "./estilo";
import { ROTAS, rotaDoArquivo } from "./rotas";
import { expandirBruto } from "./site/Bruto";
import { Documento, SITE_JS } from "./site/Moldura";

export const arquivos = ROTAS.map((r) => r.arquivo);

export function renderizar(arquivo: string): string {
  const rota = rotaDoArquivo(arquivo);
  const html = renderToStaticMarkup(<Documento {...rota.dados}>{rota.conteudo()}</Documento>);
  return `<!doctype html>\n${expandirBruto(html)}\n`;
}

/** Os arquivos que acompanham as páginas: o CSS e o JavaScript do site. */
export function arquivosFixos(): Record<string, string> {
  return { "estilo.css": css(), "site.js": SITE_JS };
}
