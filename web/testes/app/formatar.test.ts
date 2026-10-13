// A formatação do app novo é a mesma do Streamlit: cada caso vem do Python (src/formatos.py).
import { describe, expect, it } from "vitest";
import casos from "../../conteudo/formatacao.json";
import { formatar } from "../../src/app/formatar";

describe("formatar", () => {
  it.each(casos.map((c) => [c.valor, c.formato, c.texto] as const))(
    "%s em %s → %s",
    (valor, formato, texto) => {
      expect(formatar(valor, formato)).toBe(texto);
    },
  );

  it("os casos incluem um empate exato (o Python arredonda para o par)", () => {
    expect(casos.some((c) => c.valor === 0.12125 && c.texto === "12,12%")).toBe(true);
  });
});
