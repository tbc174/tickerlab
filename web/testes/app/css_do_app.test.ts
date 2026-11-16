// O app.css tem as chaves casadas (linha 903, PR 2 das telas). Um bloco sem a chave de fechamento (o
// `.barra-do-setor`, no #1151) faz o navegador aninhar tudo o que vem depois dele: a tela do Perguntar inteira
// perdeu o estilo em produção sem que nenhum teste de tela percebesse (o jsdom não aplica o CSS).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SEM_COMENTARIO = /\/\*[\s\S]*?\*\//g;

describe("app.css", () => {
  it("abre e fecha as mesmas chaves, e nunca fecha uma que não abriu", () => {
    const css = readFileSync(join(process.cwd(), "src", "app", "app.css"), "utf8").replace(SEM_COMENTARIO, "");
    let aberto = 0;
    for (const letra of css) {
      if (letra === "{") aberto += 1;
      if (letra === "}") aberto -= 1;
      expect(aberto).toBeGreaterThanOrEqual(0);
    }
    expect(aberto).toBe(0);
  });
});
