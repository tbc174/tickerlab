// As contas em TypeScript dão os números de referência (calculados à mão ou por fonte pública), os
// mesmos que o Python confere em tests/test_casos_de_referencia_ferramentas.py. O arquivo de casos
// é um só: tests/arquivos/casos_de_referencia_ferramentas.json, com a origem de cada número.
import { describe, expect, it } from "vitest";
import casos from "../../../tests/arquivos/casos_de_referencia_ferramentas.json";
import { CONTAS } from "./contas_por_nome";

/** Entra no resultado: "" é ele todo; "0.parcela" é o campo `parcela` do item 0. */
function campo(valor: unknown, caminho: string): unknown {
  return caminho
    .split(".")
    .filter(Boolean)
    .reduce<unknown>((atual, parte) => (atual as Record<string, unknown>)[parte], valor);
}

describe("contas das ferramentas dão os números de referência", () => {
  casos.forEach((caso, posicao) => {
    it(`${posicao}: ${caso.conta}(${JSON.stringify(caso.argumentos)}) ${caso.campo}`, () => {
      const conta = CONTAS[caso.conta] as (...argumentos: unknown[]) => unknown;
      const obtido = campo(conta(...caso.argumentos), caso.campo);
      if (typeof caso.esperado === "string") expect(obtido, caso.origem).toBe(caso.esperado);
      else expect(Math.abs((obtido as number) - caso.esperado), `${String(obtido)} ≠ ${caso.esperado}: ${caso.origem}`).toBeLessThanOrEqual(caso.tolerancia + 1e-12);
    });
  });
});
