// O que só roda no build (Node): ler arquivos do repositório e a versão no endereço do CSS e do JS.
// Serve ao site (Moldura) e ao app em React (vite.app.config.ts).
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// O build roda dentro de web/ (npm run build): os arquivos do repositório ficam um nível acima.
export const RAIZ_DO_REPOSITORIO = join(process.cwd(), "..");
// LF sempre (o Git no Windows pode tirar o arquivo com CRLF): o mesmo hash em todo lugar
export const lerTexto = (caminho: string) => readFileSync(caminho, "utf8").replace(/\r\n/g, "\n");
export const SOL_JS = lerTexto(join(RAIZ_DO_REPOSITORIO, "static", "tema", "sol.js"));

/** Um pedaço do hash do arquivo, no endereço: a Cloudflare e o navegador guardam o CSS e o JS por
 * horas, e um endereço novo a cada mudança faz todos buscarem a versão nova na hora. */
export function versao(conteudo: string): string {
  return createHash("sha256").update(conteudo, "utf8").digest("hex").slice(0, 12);
}
