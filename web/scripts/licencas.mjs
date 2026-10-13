// Confere a licença de cada pacote instalado (package-lock.json): só licenças permissivas.
// O TickerLab é comercial e sem licença aberta (ADR 0005): nada de GPL, AGPL ou LGPL (ADR 0048).
// MPL-2.0 só em ferramenta de build ("dev": o lightningcss do Vite), que não vai para o site
// publicado; a obrigação dela vale para quem distribui arquivos dela modificados.
import { readFileSync } from "node:fs";

const PERMITIDAS = new Set([
  "MIT",
  "MIT-0",
  "ISC",
  "0BSD",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "Apache-2.0",
  "BlueOak-1.0.0",
  "CC0-1.0",
  "CC-BY-4.0",
  "Python-2.0",
]);

const SO_NO_BUILD = new Set(["MPL-2.0"]);

const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
const problemas = [];
for (const [caminho, pacote] of Object.entries(lock.packages)) {
  if (caminho === "") continue; // o próprio projeto
  const licenca = pacote.license ?? "(sem licença declarada)";
  const partes = licenca.replace(/[()]/g, "").split(/\s+OR\s+/);
  const aceita = (p) => PERMITIDAS.has(p) || (pacote.dev === true && SO_NO_BUILD.has(p));
  if (!partes.some((p) => aceita(p.trim()))) problemas.push(`${caminho}: ${licenca}`);
}
if (problemas.length) {
  console.error("Licenças fora da lista permitida:\n" + problemas.join("\n"));
  process.exit(1);
}
console.log(`${Object.keys(lock.packages).length - 1} pacotes, todos com licença permitida.`);
