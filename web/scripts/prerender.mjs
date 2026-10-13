// Escreve o site pronto: o HTML de cada página (index.html, produto.html...), o CSS, o JavaScript,
// o robots.txt e o sitemap.xml. Roda depois do `vite build --ssr` (o renderizador em dist-servidor/).
//   node scripts/prerender.mjs          → web/dist/ (CI e testes)
//   node scripts/prerender.mjs ../site  → a pasta site/ do repositório (o que o nginx serve)
// Os outros arquivos de site/ (fontes, marca, relatório de exemplo, catálogo) vêm do Python
// (scripts/gerar_site.py) e não são tocados aqui.
import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const raiz = process.cwd(); // o npm roda os scripts dentro de web/
const destino = resolve(raiz, process.argv[2] ?? "dist");
const servidor = await import(pathToFileURL(join(raiz, "dist-servidor", "entry-server.js")).href);

if (destino === join(raiz, "dist")) rmSync(destino, { recursive: true, force: true });
mkdirSync(destino, { recursive: true });
// página que saiu do React não pode ficar esquecida na pasta
for (const nome of existsSync(destino) ? readdirSync(destino) : []) {
  if (nome.endsWith(".html") && !servidor.arquivos.includes(nome)) rmSync(join(destino, nome));
}
const saida = {
  ...Object.fromEntries(servidor.arquivos.map((a) => [a, servidor.renderizar(a)])),
  ...servidor.arquivosFixos(),
};
for (const [nome, conteudo] of Object.entries(saida)) {
  writeFileSync(join(destino, nome), conteudo, "utf8");
}
console.log(`${Object.keys(saida).length} arquivos em ${destino}`);
rmSync(join(raiz, "dist-servidor"), { recursive: true, force: true });
