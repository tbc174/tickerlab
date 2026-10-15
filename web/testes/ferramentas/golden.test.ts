// As contas das ferramentas em TypeScript dão o mesmo número que as do Python (src/ferramentas/).
// Os casos e os resultados do Python ficam em testes/golden_ferramentas.json, gerado por
// `python -m scripts.gerar_golden_ferramentas`; o pytest confere que o arquivo está em dia.
import { describe, expect, it } from "vitest";
import * as aleatorio from "../../src/ferramentas/contas/aleatorio";
import * as aportes from "../../src/ferramentas/contas/aportes";
import * as custos from "../../src/ferramentas/contas/custos";
import * as darf from "../../src/ferramentas/contas/darf";
import * as inflacao from "../../src/ferramentas/contas/inflacao";
import * as juros from "../../src/ferramentas/contas/juros";
import * as moedas from "../../src/ferramentas/contas/moedas";
import * as rendaFixa from "../../src/ferramentas/contas/renda_fixa";
import * as sorte from "../../src/ferramentas/contas/sorte_em_serie";
import * as taxas from "../../src/ferramentas/contas/taxas";
import * as viverDeRenda from "../../src/ferramentas/contas/viver_de_renda";
import * as precoMedio from "../../src/ferramentas/contas/preco_medio";
import * as financiamento from "../../src/ferramentas/contas/financiamento";
import * as fundos from "../../src/ferramentas/contas/fundos";
import casos from "../golden_ferramentas.json";

type Conta = (...argumentos: never[]) => unknown;

const CONTAS: Record<string, Conta> = {
  "juros.montante": juros.montante,
  "juros.evolucao": juros.evolucao,
  "juros.taxa_equivalente": juros.taxaEquivalente,
  "juros.taxa_por_mes": juros.taxaPorMes,
  "juros.em_reais_de_hoje": juros.emReaisDeHoje,
  "juros.liquido_de_ir": juros.liquidoDeIr,
  "aportes.valor_futuro": aportes.valorFuturo,
  "aportes.aporte_para_meta": aportes.aporteParaMeta,
  "aportes.meses_ate_meta": aportes.mesesAteMeta,
  "aportes.evolucao": aportes.evolucao,
  "aportes.mes_da_virada": aportes.mesDaVirada,
  "custos.custo_da_taxa": custos.custoDaTaxa,
  "custos.evolucao_da_taxa": custos.evolucaoDaTaxa,
  "custos.alta_para_recuperar": custos.altaParaRecuperar,
  "viver_de_renda.patrimonio_necessario": viverDeRenda.patrimonioNecessario,
  "viver_de_renda.duracao_em_meses": viverDeRenda.duracaoEmMeses,
  "viver_de_renda.renda_da_regra_dos_4": viverDeRenda.rendaDaRegraDos4,
  "viver_de_renda.trajetoria": viverDeRenda.trajetoria,
  "aleatorio.sequencia": aleatorio.sequencia,
  "sorte_em_serie.sharpe": sorte.sharpe,
  "sorte_em_serie.simular": sorte.simular,
  "sorte_em_serie.erfc": sorte.erfc,
  "sorte_em_serie.p_valor": sorte.pValor,
  "darf.apurar_mes": darf.apurarMes,
  "darf.apurar_meses": darf.apurarMeses,
  "darf.vencimento": darf.vencimento,
  "preco_medio.calcular": precoMedio.calcular,
  "financiamento.parcela_price": financiamento.parcelaPrice,
  "financiamento.tabela": financiamento.tabela,
  "fundos.simular": fundos.simular,
  "renda_fixa.cdb_que_rende": rendaFixa.cdbQueRende,
  "fundos.aliquota_do_fundo": fundos.aliquotaDoFundo,
  "moedas.converter": moedas.converter,
  "taxas.juro_real": taxas.juroReal,
  "taxas.taxa_nominal": taxas.taxaNominal,
  "inflacao.corrigir": inflacao.corrigir,
  "inflacao.em_12_meses": inflacao.em12Meses,
  "inflacao.evolucao": inflacao.evolucao,
  "inflacao.anos_abaixo": inflacao.anosAbaixo,
  "renda_fixa.comparar": rendaFixa.comparar,
  "renda_fixa.tesouro_prefixado": rendaFixa.tesouroPrefixado,
  "renda_fixa.tesouro_ipca": rendaFixa.tesouroIpca,
  "renda_fixa.cdi_pelo_focus": rendaFixa.cdiPeloFocus,
  "renda_fixa.ponto_de_empate": rendaFixa.pontoDeEmpate,
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
