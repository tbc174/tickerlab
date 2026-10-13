// Escreve o site pronto em dist/: o HTML de cada página (index.html, produto.html...), o CSS e o
// JavaScript. Roda depois do `vite build --ssr` (que monta o renderizador em dist-servidor/).
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const raiz = process.cwd(); // o npm roda os scripts dentro de web/
const destino = join(raiz, "dist");
const servidor = await import(pathToFileURL(join(raiz, "dist-servidor", "entry-server.js")).href);

rmSync(destino, { recursive: true, force: true });
mkdirSync(destino, { recursive: true });
for (const arquivo of servidor.arquivos) {
  writeFileSync(join(destino, arquivo), servidor.renderizar(arquivo), "utf8");
  console.log(`dist/${arquivo}`);
}
for (const [nome, conteudo] of Object.entries(servidor.arquivosFixos())) {
  writeFileSync(join(destino, nome), conteudo, "utf8");
  console.log(`dist/${nome}`);
}
rmSync(join(raiz, "dist-servidor"), { recursive: true, force: true });
