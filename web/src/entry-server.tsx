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

// security.txt (RFC 9116): a data de validade é fixa de propósito, para o build sair igual toda vez;
// renove-a (1 ano) antes de vencer: tests/test_site.py falha 30 dias antes da data.
export const SECURITY_TXT_EXPIRA = "2027-10-17T00:00:00.000Z";

function securityTxt(): string {
  return (
    "Contact: mailto:contato@tickerlab.com.br\n" +
    `Expires: ${SECURITY_TXT_EXPIRA}\n` +
    "Preferred-Languages: pt-BR, en\n" +
    `Canonical: ${URL_DO_SITE}/.well-known/security.txt\n`
  );
}

/** Os arquivos que acompanham as páginas: CSS, JavaScript, robots.txt, mapa do site e security.txt. */
export function arquivosFixos(): Record<string, string> {
  return {
    "estilo.css": css(),
    "site.js": SITE_JS,
    "movimento.js": MOVIMENTO_JS,
    "robots.txt": `User-agent: *\nAllow: /\nSitemap: ${URL_DO_SITE}/sitemap.xml\n`,
    "sitemap.xml": mapaDoSite(),
    ".well-known/security.txt": securityTxt(),
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
