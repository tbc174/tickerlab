// Escreve o HTML pronto de cada página em dist/, com o nome de hoje (index.html, produto.html...).
// Roda depois do `vite build` (JavaScript do navegador) e do `vite build --ssr` (o renderizador).
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const raiz = join(dirname(fileURLToPath(import.meta.url)), "..");
const manifesto = JSON.parse(readFileSync(join(raiz, "dist", ".vite", "manifest.json"), "utf8"));
const script = "/" + manifesto["src/entry-client.tsx"].file;
const servidor = await import(pathToFileURL(join(raiz, "dist-servidor", "entry-server.js")).href);

for (const arquivo of servidor.arquivos) {
  writeFileSync(join(raiz, "dist", arquivo), servidor.renderizar(arquivo, script), "utf8");
  console.log(`dist/${arquivo}`);
}
rmSync(join(raiz, "dist-servidor"), { recursive: true, force: true });
