// O orçamento do ferramentas.js: comprimido (como o navegador baixa), até 110 KB. Cada ferramenta
// nova entra no mesmo script; passou do teto, é hora de dividir por página (import dinâmico) em vez
// de subir o número.
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";

const TETO_EM_KB = 110;
const SCRIPT = new URL("../../../site/ferramentas.js", import.meta.url);

describe("tamanho do ferramentas.js", () => {
  it(`comprimido, fica em até ${TETO_EM_KB} KB`, () => {
    const comprimido = gzipSync(readFileSync(SCRIPT), { level: 9 }).length / 1024;
    expect(comprimido).toBeGreaterThan(10); // o arquivo existe e não está vazio
    expect(comprimido).toBeLessThanOrEqual(TETO_EM_KB);
  });
});
