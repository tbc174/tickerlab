// DARF de ações: cópia em TypeScript de src/ferramentas/darf.py (a referência). As regras, com a
// fonte oficial, vêm de src/regras_de_imposto.py pelo conteudo/regras_de_imposto.json.
// Mudou aqui? Mude lá também; o testes/ferramentas/golden.test.ts compara as duas.
import { regrasDeImposto } from "../../conteudo";

function regra(chave: string): number | string {
  const achada = regrasDeImposto.regras.find((r) => r.chave === chave);
  if (!achada) throw new Error(`Regra de imposto desconhecida: ${chave}`);
  return achada.valor;
}

export const ALIQUOTA_COMUM = Number(regra("aliquota_comum"));
export const ALIQUOTA_DAY_TRADE = Number(regra("aliquota_day_trade"));
export const ISENCAO_VENDAS_NO_MES = Number(regra("isencao_vendas_no_mes"));
export const DARF_MINIMO = Number(regra("darf_minimo"));
export const CODIGO_DO_DARF = String(regra("codigo_do_darf"));
const MESES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

/** As operações de um mês, já com os custos descontados do resultado (lucro + ou prejuízo −). */
export interface Mes {
  vendas_comuns: number; // total vendido em ações no mês, sem contar o day trade
  resultado_comum: number;
  resultado_day_trade: number;
  irrf_comum: number;
  irrf_day_trade: number;
}

/** O que vem dos meses anteriores (e o que passa para o seguinte). */
export interface Saldos {
  prejuizo_comum: number;
  prejuizo_day_trade: number;
  irrf_a_compensar: number;
  imposto_abaixo_do_minimo: number;
}

export interface Apuracao {
  isento: boolean;
  base_comum: number;
  base_day_trade: number;
  imposto_comum: number;
  imposto_day_trade: number;
  irrf_usado: number;
  darf: number; // a pagar neste mês (0 se isento, sem imposto ou abaixo de R$ 10)
  saldos_seguintes: Saldos;
}

const MES_VAZIO: Mes = {
  vendas_comuns: 0,
  resultado_comum: 0,
  resultado_day_trade: 0,
  irrf_comum: 0,
  irrf_day_trade: 0,
};
export const SALDOS_ZERADOS: Saldos = {
  prejuizo_comum: 0,
  prejuizo_day_trade: 0,
  irrf_a_compensar: 0,
  imposto_abaixo_do_minimo: 0,
};

function conferir(mes: Mes, saldos: Saldos): void {
  if (mes.vendas_comuns < 0) throw new RangeError("O total de vendas não pode ser negativo.");
  if (mes.irrf_comum < 0 || mes.irrf_day_trade < 0 || saldos.irrf_a_compensar < 0) {
    throw new RangeError("O imposto retido não pode ser negativo.");
  }
  if (saldos.prejuizo_comum < 0 || saldos.prejuizo_day_trade < 0) {
    throw new RangeError("Informe o prejuízo a compensar como um valor positivo.");
  }
  if (!(saldos.imposto_abaixo_do_minimo >= 0 && saldos.imposto_abaixo_do_minimo < DARF_MINIMO)) {
    throw new RangeError(`O imposto acumulado abaixo de R$ ${DARF_MINIMO} fica entre 0 e 10.`);
  }
}

/** [base tributável, prejuízo que sobra] de um resultado com o prejuízo acumulado. */
function compensar(resultado: number, prejuizo: number): [number, number] {
  if (resultado < 0) return [0, prejuizo - resultado];
  const usado = Math.min(prejuizo, resultado);
  return [resultado - usado, prejuizo - usado];
}

/** O imposto do mês e os saldos que passam para o mês seguinte (o que faltar fica em zero). */
export function apurarMes(parcial: Partial<Mes>, saldosParciais: Partial<Saldos>): Apuracao {
  const mes = { ...MES_VAZIO, ...parcial };
  const saldos = { ...SALDOS_ZERADOS, ...saldosParciais };
  conferir(mes, saldos);
  const isento = mes.vendas_comuns <= ISENCAO_VENDAS_NO_MES && mes.resultado_comum > 0;
  // o lucro isento não gasta o prejuízo acumulado
  const [baseComum, prejuizoComum] = isento
    ? [0, saldos.prejuizo_comum]
    : compensar(mes.resultado_comum, saldos.prejuizo_comum);
  const [baseDt, prejuizoDt] = compensar(mes.resultado_day_trade, saldos.prejuizo_day_trade);
  const impostoComum = baseComum * ALIQUOTA_COMUM;
  const impostoDt = baseDt * ALIQUOTA_DAY_TRADE;
  const irrf = saldos.irrf_a_compensar + mes.irrf_comum + mes.irrf_day_trade;
  const irrfUsado = Math.min(impostoComum + impostoDt, irrf);
  const devido = impostoComum + impostoDt - irrfUsado + saldos.imposto_abaixo_do_minimo;
  const paga = devido >= DARF_MINIMO;
  return {
    isento,
    base_comum: baseComum,
    base_day_trade: baseDt,
    imposto_comum: impostoComum,
    imposto_day_trade: impostoDt,
    irrf_usado: irrfUsado,
    darf: paga ? devido : 0,
    saldos_seguintes: {
      prejuizo_comum: prejuizoComum,
      prejuizo_day_trade: prejuizoDt,
      irrf_a_compensar: irrf - irrfUsado,
      imposto_abaixo_do_minimo: paga ? 0 : devido,
    },
  };
}

/** Mês a mês, levando os saldos de um para o outro. */
export function apurarMeses(meses: Partial<Mes>[], saldos: Partial<Saldos>): Apuracao[] {
  const apuracoes: Apuracao[] = [];
  let atuais = saldos;
  for (const mes of meses) {
    apuracoes.push(apurarMes(mes, atuais));
    atuais = apuracoes[apuracoes.length - 1].saldos_seguintes;
  }
  return apuracoes;
}

/** O prazo do DARF das operações de `mes`/`ano`: o último dia útil do mês seguinte. */
export function vencimento(ano: number, mes: number): string {
  const [anoSeguinte, mesSeguinte] = mes === 12 ? [ano + 1, 1] : [ano, mes + 1];
  return `último dia útil de ${MESES[mesSeguinte - 1]} de ${anoSeguinte}`;
}
