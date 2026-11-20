// A busca de setor das ferramentas do analista: as atividades do CNAE (a tabela da Receita) achadas pelo nome,
// sem ligar para acento nem para o fim da palavra ("farmácia" acha "farmacêuticos"), ou pelo começo do código.
import { describe, expect, it } from "vitest";
import {
  carregarCnaes,
  cnaeComPontuacao,
  cnaeDigitado,
  rotuloDoSetor,
  sugestoesDeCnae,
} from "../../src/app/buscaDeCnaes";

describe("busca de setor pelo CNAE", () => {
  it("acha pelo nome: farmácia, transporte de carga, hospital e supermercado", async () => {
    const cnaes = await carregarCnaes();
    const codigos = (texto: string) => sugestoesDeCnae(cnaes, texto).map((c) => c.codigo);
    expect(codigos("farmácia")).toEqual(expect.arrayContaining(["4771701", "4771702", "4771703"]));
    expect(codigos("transporte de carga")).toContain("4930202");
    const nomes = sugestoesDeCnae(cnaes, "TRANSPORTE DE CARGA").map((c) => c.nome);
    expect(nomes.every((n) => /transporte/i.test(n) && /carga/i.test(n))).toBe(true);
    expect(codigos("hospital").slice(0, 2)).toContain("8610101"); // "Atividades de atendimento hospitalar" no topo
    expect(codigos("supermercado")).toContain("4711302");
  });

  it("pelo código: o começo dos dígitos, com ou sem pontuação, a partir de 2 dígitos", async () => {
    const cnaes = await carregarCnaes();
    expect(sugestoesDeCnae(cnaes, "4771-7").map((c) => c.codigo)).toEqual(["4771701", "4771702", "4771703", "4771704"]);
    expect(sugestoesDeCnae(cnaes, "4")).toEqual([]);
    expect(sugestoesDeCnae(cnaes, "  ")).toEqual([]);
    expect(sugestoesDeCnae(cnaes, "de")).toEqual([]);
  });

  it("nunca passa do limite de sugestões", async () => {
    const cnaes = await carregarCnaes();
    expect(sugestoesDeCnae(cnaes, "comércio").length).toBe(8);
  });

  it("o código digitado vale com 5 ou 7 dígitos; o resto não", () => {
    expect(cnaeDigitado("4771701")).toBe("4771701");
    expect(cnaeDigitado("4771-7/01")).toBe("4771701");
    expect(cnaeDigitado(" 47.71-7 ")).toBe("47717");
    expect(cnaeDigitado("477")).toBeNull();
    expect(cnaeDigitado("farmácia")).toBeNull();
  });

  it("escreve o código como o IBGE e o rótulo do setor com o nome", () => {
    expect(cnaeComPontuacao("4771701")).toBe("4771-7/01");
    expect(cnaeComPontuacao("47717")).toBe("4771-7");
    expect(rotuloDoSetor("4771701", "Comércio varejista de produtos farmacêuticos.")).toBe(
      "Comércio varejista de produtos farmacêuticos (CNAE 4771-7/01)",
    );
    expect(rotuloDoSetor("47717", null)).toBe("CNAE 4771-7");
  });
});
