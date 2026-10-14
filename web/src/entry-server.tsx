// Monta o HTML pronto de cada página no build (sem navegador): é o que a busca do Google lê. O site
// é estático: nada de React no navegador; o site.js cuida do tema, da busca e da vitrine, e o
// movimento.js das animações.
import { renderToStaticMarkup } from "react-dom/server";
import { css } from "./estilo";
import { ROTAS, rotaDoArquivo } from "./rotas";
import { expandirBruto } from "./site/Bruto";
import { Documento, MOVIMENTO_JS, SITE_JS } from "./site/Moldura";
import { URL_DO_SITE } from "./site/textos";

export const arquivos = ROTAS.map((r) => r.arquivo);

export function renderizar(arquivo: string): string {
  const rota = rotaDoArquivo(arquivo);
  const html = renderToStaticMarkup(<Documento {...rota.dados}>{rota.conteudo()}</Documento>);
  return `<!doctype html>\n${expandirBruto(html)}\n`;
}

/** Os arquivos que acompanham as páginas: CSS, JavaScript, robots.txt e o mapa do site. */
export function arquivosFixos(): Record<string, string> {
  return {
    "estilo.css": css(),
    "site.js": SITE_JS,
    "movimento.js": MOVIMENTO_JS,
    "robots.txt": `User-agent: *\nAllow: /\nSitemap: ${URL_DO_SITE}/sitemap.xml\n`,
    "sitemap.xml": mapaDoSite(),
  };
}

/** Todas as páginas menos a 404, na ordem das rotas. */
function mapaDoSite(): string {
  const enderecos = arquivos
    .filter((a) => a !== "404.html")
    .map((a) => `  <url><loc>${URL_DO_SITE}/${a === "index.html" ? "" : a}</loc></url>\n`);
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    enderecos.join("") +
    "</urlset>\n"
  );
}
