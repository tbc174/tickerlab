// A seção do CNAE pela divisão: o Setor abre a busca de empresas já no setor certo (linha 903, PR 3).
import { describe, expect, it } from "vitest";
import { secaoDoCnae } from "../../src/app/secaoDoCnae";

describe("seção do CNAE", () => {
  it.each([
    ["6201501", "J"],
    ["62015", "J"],
    ["4120400", "F"],
    ["0111301", "A"],
    ["1011201", "C"],
    ["3500000", "D"],
    ["9609299", "S"],
    ["8411600", "O"],
  ])("%s é da seção %s", (cnae, secao) => {
    expect(secaoDoCnae(cnae)).toBe(secao);
  });

  it.each([["0400000"], ["3400000"], ["9800000"], ["62"], ["620150"], ["62015012"], ["62.01-5"], [""]])(
    "%s não é de uma divisão do CNAE: sem seção",
    (cnae) => {
      expect(secaoDoCnae(cnae)).toBeNull();
    },
  );
});
