// As contas das ferramentas em TypeScript dão o mesmo número que as do Python (src/ferramentas/).
// Os casos e os resultados do Python ficam em testes/golden_ferramentas.json, gerado por
// `python -m scripts.gerar_golden_ferramentas`; o pytest confere que o arquivo está em dia.
import { describe, expect, it } from "vitest";
import * as aportes from "../../src/ferramentas/contas/aportes";
import * as custos from "../../src/ferramentas/contas/custos";
import * as juros from "../../src/ferramentas/contas/juros";
import casos from "../golden_ferramentas.json";

type Conta = (...argumentos: never[]) => unknown;

const CONTAS: Record<string, Conta> = {
  "juros.montante": juros.montante,
  "juros.evolucao": juros.evolucao,
  "juros.taxa_equivalente": juros.taxaEquivalente,
  "juros.taxa_por_mes": juros.taxaPorMes,
  "aportes.valor_futuro": aportes.valorFuturo,
  "aportes.aporte_para_meta": aportes.aporteParaMeta,
  "aportes.meses_ate_meta": aportes.mesesAteMeta,
  "aportes.evolucao": aportes.evolucao,
  "custos.custo_da_taxa": custos.custoDaTaxa,
  "custos.evolucao_da_taxa": custos.evolucaoDaTaxa,
  "custos.alta_para_recuperar": custos.altaParaRecuperar,
};

const TOLERANCIA_RELATIVA = 1e-12;

/** Compara número a número, com a tolerância do último dígito; o resto tem de ser igual. */
function comparar(agora: unknown, antes: unknown, onde: string): void {
  if (typeof antes === "number") {
    expect(typeof agora, onde).toBe("number");
    const diferenca = Math.abs((agora as number) - antes);
    expect(diferenca, `${onde}: ${String(agora)} ≠ ${antes}`).toBeLessThanOrEqual(
      Math.max(Math.abs(antes) * TOLERANCIA_RELATIVA, 1e-12),
    );
  } else if (Array.isArray(antes)) {
    expect(Array.isArray(agora), onde).toBe(true);
    expect((agora as unknown[]).length, onde).toBe(antes.length);
    antes.forEach((item, posicao) => comparar((agora as unknown[])[posicao], item, `${onde}[${posicao}]`));
  } else if (antes !== null && typeof antes === "object") {
    const objeto = agora as Record<string, unknown>;
    expect(Object.keys(objeto).sort(), onde).toEqual(Object.keys(antes).sort());
    for (const [chave, valor] of Object.entries(antes)) comparar(objeto[chave], valor, `${onde}.${chave}`);
  } else {
    expect(agora, onde).toEqual(antes);
  }
}

describe("contas das ferramentas iguais às do Python", () => {
  it("toda conta do golden existe em TypeScript", () => {
    const nomes = new Set(casos.map((caso) => caso.conta));
    expect([...nomes].sort()).toEqual(Object.keys(CONTAS).sort());
  });

  casos.forEach((caso, posicao) => {
    it(`${posicao}: ${caso.conta}(${caso.argumentos.join(", ")})`, () => {
      const conta = CONTAS[caso.conta] as (...argumentos: unknown[]) => unknown;
      if ("erro" in caso && caso.erro) {
        expect(() => conta(...caso.argumentos)).toThrow(RangeError);
      } else {
        comparar(conta(...caso.argumentos), (caso as { valor: unknown }).valor, caso.conta);
      }
    });
  });
});
