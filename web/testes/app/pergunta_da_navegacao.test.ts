// A pergunta que uma tela manda ao Perguntar pelo estado da navegação (linha 903, PR 2 das telas): só texto,
// aparado, e qualquer outra coisa que esteja no histórico do navegador é ignorada.
import { describe, expect, it } from "vitest";
import { comAPergunta, perguntaDoEstado, URL_DO_PERGUNTAR } from "../../src/app/perguntaDaNavegacao";

describe("pergunta da navegação", () => {
  it("ida e volta: o que uma tela manda é o que o Perguntar lê", () => {
    expect(perguntaDoEstado(comAPergunta("  Uma pergunta?  "))).toBe("Uma pergunta?");
  });

  it.each([null, undefined, "texto solto", 42, {}, { pergunta: 7 }, { cnpj: "11222333000181" }])(
    "estado sem pergunta (%j) vira vazio",
    (estado) => {
      expect(perguntaDoEstado(estado)).toBe("");
    },
  );

  it("o endereço do Perguntar vem do mapa de páginas", () => {
    expect(URL_DO_PERGUNTAR).toBe("perguntar");
  });
});
