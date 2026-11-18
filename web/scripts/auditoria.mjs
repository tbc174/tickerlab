// Confere as vulnerabilidades altas e críticas dos pacotes (npm audit), com exceções escritas e com prazo.
// Exceção só entra quando não há versão corrigida e o pacote não vai para o site publicado (só build ou
// teste); cada uma diz o porquê e vence numa data: vencida, o CI falha e alguém decide de novo.
import { execFileSync } from "node:child_process";

const EXCECOES = {
  // picomatch <= 4.0.7 (a última): ReDoS com extglob repetido. Sem versão corrigida em 17/11/2026. Vem só
  // do vite e do vitest (build e teste); os padrões que ele recebe são os da nossa configuração, nunca
  // texto de usuário, e nada dele vai para o site (npm audit --omit=dev: 0 vulnerabilidades).
  "GHSA-fc5q-39xc-vjpf": { vence: "2026-12-17" },
};
const GRAVES = new Set(["high", "critical"]);

function rodarAudit() {
  try {
    return execFileSync("npm", ["audit", "--json"], { encoding: "utf8", shell: process.platform === "win32" });
  } catch (erro) {
    return erro.stdout; // o npm audit sai com código 1 quando acha algo; o JSON vem mesmo assim
  }
}

const relatorio = JSON.parse(rodarAudit());
const hoje = new Date().toISOString().slice(0, 10);
const problemas = [];
const usadas = new Set();
for (const vulneravel of Object.values(relatorio.vulnerabilities ?? {})) {
  for (const aviso of vulneravel.via) {
    if (typeof aviso === "string" || !GRAVES.has(aviso.severity)) continue; // texto = herdado de outro pacote
    const id = aviso.url.split("/").pop();
    const excecao = EXCECOES[id];
    if (!excecao) problemas.push(`${aviso.name} (${aviso.severity}): ${aviso.title} ${aviso.url}`);
    else if (excecao.vence < hoje) problemas.push(`exceção ${id} venceu em ${excecao.vence}: decida de novo`);
    else usadas.add(id);
  }
}
for (const id of Object.keys(EXCECOES)) {
  if (!usadas.has(id)) console.log(`aviso: a exceção ${id} não é mais usada; tire-a de scripts/auditoria.mjs`);
}
if (problemas.length) {
  console.error("Vulnerabilidades altas ou críticas sem exceção:\n" + problemas.join("\n"));
  process.exit(1);
}
console.log(`Sem vulnerabilidade alta ou crítica fora das exceções (${[...usadas].join(", ") || "nenhuma"}).`);
