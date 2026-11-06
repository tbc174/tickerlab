// As contas das ferramentas em TypeScript pelo mesmo nome que o Python usa nos casos golden e de referência.
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

export type Conta = (...argumentos: never[]) => unknown;

export const CONTAS: Record<string, Conta> = {
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

